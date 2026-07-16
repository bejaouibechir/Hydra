"""
api/routers/terminal.py — Terminal interactif via WebSocket, basé sur un PTY.

WS /api/terminal/ws?shell=powershell|bash

Un vrai pseudo-terminal (PTY) est utilisé pour que le shell se comporte comme
dans une console : invite, écho des frappes, édition de ligne, couleurs.
  - Windows : ConPTY via pywinpty (pip install pywinpty)
  - Unix    : module standard pty

Le client (xterm.js) envoie les frappes en binaire et reçoit la sortie en binaire.
"""
from __future__ import annotations

import asyncio
import os
import sys

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

router = APIRouter()


def _argv(shell: str) -> list[str]:
    if shell == "powershell":
        if sys.platform != "win32":
            raise RuntimeError("PowerShell disponible uniquement sur Windows")
        return ["powershell.exe", "-NoLogo"]
    if shell == "cmd":
        if sys.platform != "win32":
            raise RuntimeError("cmd disponible uniquement sur Windows")
        return ["cmd.exe"]
    if shell == "bash":
        if sys.platform == "win32":
            raise RuntimeError("Bash non disponible sur Windows")
        return ["bash", "-i"]
    raise ValueError(f"Shell inconnu : {shell}")


@router.websocket("/ws")
async def terminal_ws(websocket: WebSocket, shell: str = Query("powershell")) -> None:
    await websocket.accept()
    try:
        argv = _argv(shell)
    except (RuntimeError, ValueError) as e:
        await websocket.send_text(f"\r\n\x1b[31mErreur : {e}\x1b[0m\r\n")
        await websocket.close()
        return

    if sys.platform == "win32":
        await _run_windows(websocket, argv)
    else:
        await _run_unix(websocket, argv)


async def _run_unix(websocket: WebSocket, argv: list[str]) -> None:
    import fcntl
    import pty
    import struct
    import termios

    master, slave = pty.openpty()
    try:
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    except Exception:
        pass

    env = {**os.environ, "TERM": "xterm-256color"}
    proc = await asyncio.create_subprocess_exec(
        *argv, stdin=slave, stdout=slave, stderr=slave,
        start_new_session=True, env=env,
    )
    os.close(slave)

    loop = asyncio.get_event_loop()

    def _on_read() -> None:
        try:
            data = os.read(master, 4096)
        except OSError:
            data = b""
        if data:
            asyncio.ensure_future(websocket.send_bytes(data))
        else:
            try:
                loop.remove_reader(master)
            except Exception:
                pass

    loop.add_reader(master, _on_read)

    try:
        while True:
            data = await websocket.receive_bytes()
            os.write(master, data)
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        try:
            loop.remove_reader(master)
        except Exception:
            pass
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            os.close(master)
        except Exception:
            pass


async def _run_windows(websocket: WebSocket, argv: list[str]) -> None:
    try:
        from winpty import PtyProcess  # type: ignore
    except ImportError:
        await websocket.send_text(
            "\r\n\x1b[31mTerminal indisponible : installez pywinpty "
            "(pip install pywinpty) puis redemarrez l'API.\x1b[0m\r\n"
        )
        await websocket.close()
        return

    loop = asyncio.get_event_loop()
    proc = await loop.run_in_executor(None, lambda: PtyProcess.spawn(argv))
    alive = True

    async def _reader() -> None:
        while alive:
            try:
                data = await loop.run_in_executor(None, proc.read, 4096)
            except EOFError:
                break
            if data:
                await websocket.send_bytes(
                    data.encode("utf-8", "replace") if isinstance(data, str) else data
                )
            else:
                if not proc.isalive():
                    break
                await asyncio.sleep(0.02)

    rtask = asyncio.create_task(_reader())
    try:
        while True:
            data = await websocket.receive_bytes()
            text = data.decode("utf-8", "replace")
            await loop.run_in_executor(None, proc.write, text)
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        alive = False
        rtask.cancel()
        try:
            proc.terminate(force=True)
        except Exception:
            pass
