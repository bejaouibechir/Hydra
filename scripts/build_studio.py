# -*- coding: utf-8 -*-
"""
build_studio.py — Construit le Studio et le depose dans le paquet Python.

    python scripts/build_studio.py

Construit le Studio avec `npm run build` dans studio/, et copie le resultat
dans hydra_etl/studio_dist/, d'ou l'API le sert.

A lancer AVANT `python -m build`. En release, c'est la CI qui l'execute : le
wheel publie sur PyPI contient donc le Studio, et l'utilisateur final n'a besoin
ni de Node ni du depot (Regle 3.4 : un tag declenche toute la chaine).

Comportement de l'installation des dependances :

    node_modules/ present   -> rien a faire, on construit directement
    node_modules/ absent    -> npm install
    --ci                    -> npm ci (repartir du lockfile ; pour la CI)
    --install               -> forcer npm install malgre node_modules/

`npm ci` supprime node_modules avant de reinstaller. Sous Windows, cette
suppression echoue si un processus tient un binaire natif (un `npm run dev`
encore ouvert, ou l'antivirus) : d'ou le fait qu'il ne soit pas le defaut.

Options :
    --skip-install   n'installe rien, meme si node_modules/ manque
    --check          verifie seulement qu'un bundle valide est en place

Exemples :
    python scripts/build_studio.py                 usage courant
    python scripts/build_studio.py --skip-install  apres un echec EPERM
    python scripts/build_studio.py --ci            en integration continue
    python scripts/build_studio.py --check         controle avant `python -m build`
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO_SRC = ROOT / "studio"
STUDIO_BUILD = STUDIO_SRC / "dist"
TARGET = ROOT / "hydra_etl" / "studio_dist"

# Fichiers indispensables cote paquet : sans eux, l'API n'a rien a servir.
REQUIRED = ["index.html"]


_LOCKED_HINT = """
  Un fichier de node_modules est verrouille par un autre processus.
  Causes habituelles, dans l'ordre :

    1. un `npm run dev` encore ouvert   ->  fermez-le, ou : taskkill /F /IM node.exe
    2. l'antivirus qui scanne un .node  ->  reessayez dans quelques secondes
    3. l'explorateur ouvert dans node_modules

  Le plus simple : node_modules est deja en place, construisez sans reinstaller

    python scripts/build_studio.py --skip-install
"""


def modules_look_complete() -> bool:
    """Verifie qu'un node_modules exploitable est en place.

    Un `npm ci` interrompu laisse un arbre a moitie supprime : le dossier
    existe encore, mais les binaires ont disparu. Sans ce controle, le build
    echoue plus loin sur un `'tsc' n'est pas reconnu` incomprehensible.
    """
    modules = STUDIO_SRC / "node_modules"
    if not modules.is_dir():
        return False
    # Paquets sans lesquels `npm run build` ne peut pas aboutir.
    for name in ("vite", "typescript", "react"):
        if not (modules / name).is_dir():
            return False
    return True


def describe_modules() -> str:
    modules = STUDIO_SRC / "node_modules"
    if not modules.is_dir():
        return "node_modules absent"
    count = sum(1 for _ in modules.iterdir())
    missing = [n for n in ("vite", "typescript", "react")
               if not (modules / n).is_dir()]
    return f"{count} entrees, manquants : {', '.join(missing) or 'aucun'}"


_BROKEN_HINT = """
  node_modules est incomplet — c'est l'etat que laisse un `npm ci` interrompu :
  il supprime l'arbre avant de reinstaller, et l'interruption fige la moitie
  du travail.

  Reconstruire proprement, sous Windows :

    taskkill /F /IM node.exe
    cd studio
    rmdir /s /q node_modules
    cd ..
    python scripts/build_studio.py --install

  Si rmdir bute sur un fichier verrouille, renommez le dossier :
  `ren node_modules node_modules_old`, puis relancez.
"""


def run(cmd: list[str], cwd: Path) -> None:
    printable = " ".join(cmd)
    print(f"  $ {printable}", flush=True)
    # shell=True sous Windows : npm y est un .cmd, introuvable autrement.
    completed = subprocess.run(
        cmd, cwd=str(cwd), shell=(sys.platform == "win32")
    )
    if completed.returncode != 0:
        # EPERM/EBUSY : npm rend un code non nul apres avoir affiche sa trace.
        # On ajoute la sortie de secours plutot que de laisser l'utilisateur
        # devant un code d'erreur brut.
        if "ci" in cmd or "install" in cmd:
            print(_LOCKED_HINT)
        raise SystemExit(f"echec : {printable} (code {completed.returncode})")


def check() -> int:
    index = TARGET / "index.html"
    if not index.is_file():
        print(f"  MANQUANT   {index}")
        print("  Lancez : python scripts/build_studio.py")
        return 1
    files = [p for p in TARGET.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    print(f"  ok   bundle present — {len(files)} fichiers, {total/1048576:.1f} Mo")
    print(f"       {TARGET}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-install", action="store_true",
                    help="n'installe rien, meme si node_modules manque")
    ap.add_argument("--install", action="store_true",
                    help="force npm install malgre node_modules present")
    ap.add_argument("--ci", action="store_true",
                    help="npm ci — repart du lockfile (pour la CI)")
    ap.add_argument("--check", action="store_true",
                    help="verifie seulement la presence du bundle")
    args = ap.parse_args()

    if args.check:
        return check()

    if not STUDIO_SRC.is_dir():
        raise SystemExit(f"dossier introuvable : {STUDIO_SRC}")

    print(f"Construction du Studio depuis {STUDIO_SRC}", flush=True)

    complete = modules_look_complete()
    if args.skip_install:
        if not complete:
            print(f"  dependances : {describe_modules()}")
            print(_BROKEN_HINT)
            raise SystemExit("--skip-install refuse : node_modules inutilisable")
        print("  dependances : node_modules complet, installation ignoree", flush=True)
    elif args.ci:
        run(["npm", "ci"], STUDIO_SRC)
    elif args.install or not complete:
        if not complete:
            print(f"  dependances : {describe_modules()} — installation necessaire",
                  flush=True)
        run(["npm", "install"], STUDIO_SRC)
    else:
        print("  dependances : node_modules complet, installation ignoree", flush=True)
        print("                (--install pour rafraichir, --ci pour repartir du lockfile)")

    # Dernier filet : ne pas lancer un build voue a l'echec.
    if not modules_look_complete():
        print(f"  dependances : {describe_modules()}")
        print(_BROKEN_HINT)
        raise SystemExit("build annule : node_modules inutilisable")

    run(["npm", "run", "build"], STUDIO_SRC)

    if not (STUDIO_BUILD / "index.html").is_file():
        raise SystemExit(f"build introuvable : {STUDIO_BUILD}/index.html")

    print(f"Copie vers {TARGET}", flush=True)
    if TARGET.exists():
        shutil.rmtree(TARGET)
    shutil.copytree(STUDIO_BUILD, TARGET)

    missing = [n for n in REQUIRED if not (TARGET / n).is_file()]
    if missing:
        raise SystemExit(f"fichiers manquants apres copie : {missing}")

    print()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
