"""content_hash : implémentation de référence (Python). À copier dans benchmarks/tools/.
Spécification : voir 00_bloc_commun.md. Doit rester strictement équivalente à n8n_code_content_hash.js."""
import hashlib
import re
from pathlib import Path

PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def normalize_text(raw: bytes) -> bytes:
    s = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(line.rstrip(" \t") for line in s.split("\n")).rstrip("\n") + "\n"
    return s.encode("utf-8")


def compute_content_hash(root: Path) -> str:
    files = []
    md = root / "contenu.md"
    if md.is_file():
        files.append(md)
    pip = root / "pipelines"
    if pip.is_dir():
        files += [p for p in pip.rglob("*") if p.is_file()]
    h = hashlib.sha256()
    for p in sorted(files, key=lambda x: x.relative_to(root).as_posix()):
        rel = p.relative_to(root).as_posix()
        if not PATH_RE.match(rel):
            raise ValueError(f"chemin non autorisé (ASCII [A-Za-z0-9._/-] uniquement) : {rel}")
        h.update(f"\n--FILE:{rel}--\n".encode("utf-8"))
        h.update(normalize_text(p.read_bytes()))
    return h.hexdigest()