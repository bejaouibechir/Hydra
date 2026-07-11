"""
api/routers/terminal.py — Terminal interactif via WebSocket.

WS /api/terminal/ws?shell=powershell|bash

Le client envoie du texte (stdin) et reçoit du texte (stdout+stderr).
Le processus tourne jusqu'à la fermeture du WebSocket.
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

router = APIRouter()


def _get_shell_args(shell: str) -> list[str]:
    if shell == "powershell":
        if sys.platform != "win32":
            raise RuntimeError("PowerShell uniquement disponible sur Windows")
        return ["powershell.exe", "-NoLogo", "-NoExit", "-Command", "-"]
    elif shell == "bash":
        if sys.platform == "win32":
            raise RuntimeError("Bash non disponible sur Windows")
        return ["bash", "--login", "-i"]
    else:
        raise ValueError(f"Shell inconnu : {shell}")


@router.websocket("/ws")
async def terminal_ws(
    websocket: WebSocket,
    shell: str = Query("powershell"),
):
    await websocket.accept()

    try:
        args = _get_shell_args(shell)
    except (RuntimeError, ValueError) as e:
        await websocket.send_text(f"\r\n\033[31mErreur : {e}\033[0m\r\n")
        await websocket.close()
        return

    # Spawner le processus shell
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,  # fusionner stderr dans stdout
        env={**os.environ, "TERM": "xterm-256color"},
    )

    async def read_output():
        """Lit stdout du process et envoie au WebSocket."""
        assert proc.stdout
        try:
            while True:
                chunk = await proc.stdout.read(1024)
                if not chunk:
                    break
                await websocket.send_bytes(chunk)
        except Exception:
            pass

    async def write_input():
        """Reçoit du WebSocket et écrit dans stdin du process."""
        assert proc.stdin
        try:
            while True:
                data = await websocket.receive_bytes()
                proc.stdin.write(data)
                await proc.stdin.drain()
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    read_task  = asyncio.create_task(read_output())
    write_task = asyncio.create_task(write_input())

    try:
        await asyncio.wait(
            [read_task, write_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        read_task.cancel()
        write_task.cancel()
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
