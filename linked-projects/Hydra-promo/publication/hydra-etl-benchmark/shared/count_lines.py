"""Compte fichiers et lignes utiles (sans lignes vides, commentaires ni docstrings)."""
import ast, io, sys, tokenize
from pathlib import Path


def py_lines(text: str) -> int:
    tree = ast.parse(text)
    doc = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) \
                    and isinstance(first.value.value, str):
                doc.update(range(first.lineno, first.end_lineno + 1))
    code = set()
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                            tokenize.DEDENT, tokenize.ENDMARKER):
            code.update(range(tok.start[0], tok.end[0] + 1))
    return len(code - doc)


def other_lines(text: str, comment: str) -> int:
    n = 0
    for ln in text.splitlines():
        s = ln.strip()
        if s and not s.startswith(comment):
            n += 1
    return n


def count(paths):
    total, rows = 0, []
    for p in paths:
        t = Path(p).read_text()
        n = py_lines(t) if p.endswith(".py") else other_lines(t, "--" if p.endswith(".sql") else "#")
        rows.append((p, n)); total += n
    return rows, total


if __name__ == "__main__":
    rows, total = count(sys.argv[1:])
    for p, n in rows:
        print(f"{n:4d}  {p}")
    print(f"{total:4d}  TOTAL ({len(rows)} files)")
