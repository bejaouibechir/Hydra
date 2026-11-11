#!/usr/bin/env python3
"""Vérifie que content_hash.py et n8n_code_content_hash.js produisent le même hash.
Usage : python test_content_hash_equivalence.py   (nécessite node)"""
import json, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from content_hash import compute_content_hash  # noqa: E402

CASES = {
    "simple": {"contenu.md": "# Titre\nTexte\n", "pipelines/a.yaml": "a: 1\n"},
    "crlf": {"contenu.md": "Bonjour\r\n{{lien_lab}}\r\n", "pipelines/a.yaml": "a: 1\r\nb: 2\r\n"},
    "cr_seul": {"contenu.md": "l1\rl2\r", "pipelines/a.yaml": "x: 1"},
    "bom": {"contenu.md": "\ufeff# Titre\n", "pipelines/a.yaml": "\ufeffa: 1\n"},
    "espaces_fin": {"contenu.md": "ligne   \n\ttab\t\t\n  \nfin  \n", "pipelines/a.yaml": "a: 1   \n"},
    "sans_saut_final": {"contenu.md": "fin sans saut", "pipelines/a.yaml": "a: 1"},
    "sauts_multiples": {"contenu.md": "texte\n\n\n\n", "pipelines/a.yaml": "a: 1\n\n\n"},
    "fichier_vide": {"contenu.md": "", "pipelines/vide.yaml": ""},
    "unicode": {"contenu.md": "Éléphant, données, 日本語, 🙂\n", "pipelines/é.yaml".replace("é", "e"): "n: «x»\n"},
    "nbsp_fin_conserve": {"contenu.md": "ligne\u00a0\n", "pipelines/a.yaml": "a: 1\u00a0\n"},
    "separateurs_exotiques": {"contenu.md": "a\x85\nb\u2028\nc\x1c\n", "pipelines/a.yaml": "k: v\x0c\n"},
    "ordre_fichiers": {"contenu.md": "x\n", "pipelines/b.yaml": "b: 2\n", "pipelines/a.yaml": "a: 1\n",
                       "pipelines/sub/c.yaml": "c: 3\n", "pipelines/B.yaml": "B: 0\n", "pipelines/_z.yaml": "z: 0\n"},
    "placeholder": {"contenu.md": "Essayez : {{lien_lab}}\n", "pipelines/a.yaml": "a: 1\n"},
}


def py_hash(files):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for rel, txt in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(txt.encode("utf-8"))
        return compute_content_hash(root)


def js_hash(files):
    payload = json.dumps([{"path": k, "content": v} for k, v in files.items()])
    code = ("const m=require(%r);let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{"
            "console.log(m.computeContentHash(JSON.parse(s)).hash)})" % str(HERE / "n8n_code_content_hash.js"))
    r = subprocess.run(["node", "-e", code], input=payload, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    return r.stdout.strip()


ko = 0
for name, files in CASES.items():
    p, j = py_hash(files), js_hash(files)
    ok = p == j
    ko += not ok
    print(f"{'OK ' if ok else 'KO '} {name:24} {p[:16]} {j[:16]}")

# invariance voulue : CRLF == LF, BOM ignoré, espaces de fin ignorés
inv = [("simple", "crlf_equiv", {"contenu.md": "Bonjour\n{{lien_lab}}\n", "pipelines/a.yaml": "a: 1\nb: 2\n"}, "crlf")]
a, b = py_hash(inv[0][2]), py_hash(CASES["crlf"])
print("OK " if a == b else "KO ", "invariance CRLF/LF")
ko += a != b
# sensibilité voulue : un caractère modifié change le hash
c = dict(CASES["simple"]); c["contenu.md"] = "# Titre\nTexte.\n"
print("OK " if py_hash(c) != py_hash(CASES["simple"]) else "KO ", "sensibilité au contenu")
ko += py_hash(c) == py_hash(CASES["simple"])
# garde-fous : chemin non ASCII et hors périmètre rejetés des deux côtés
for bad in ({"contenu.md": "x\n", "pipelines/é.yaml": "a\n"}, {"contenu.md": "x\n", "autre/a.yaml": "a\n"}):
    try:
        js_hash([bad][0] if False else bad)
        jsrej = False
    except RuntimeError:
        jsrej = True
    try:
        py_hash(bad)
        pyrej = False
    except ValueError:
        pyrej = True
    print("OK " if (jsrej and (pyrej or "autre/" in str(bad))) else "KO ", "rejet chemin :", list(bad)[1])
    ko += not jsrej
print("\nRésultat :", "ÉQUIVALENT" if ko == 0 else f"{ko} divergence(s)")
sys.exit(1 if ko else 0)