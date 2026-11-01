"""Pages 1-10 d'origine + pages 11-fin régénérées (2.3, 2.4, 3, 4)."""
import sys, importlib
sys.path.insert(0, "/home/claude/wb")
from gen import build, render
from pypdf import PdfReader, PdfWriter
SRC = "/mnt/user-data/uploads/d/"
jobs = [("content2_en", SRC + "Hydra_DSL_v_1.0_White_book.pdf"),
        ("content2_fr", SRC + "Hydra_DSL_v_1.0_Livre_blanc.pdf")]
KEEP = 10
for mod, src in jobs:
    m = importlib.import_module(mod)
    tail = f"/home/claude/wb/{mod}_tail.pdf"
    build(tail, render(m.SPEC), m.HEADER, m.FOOTER, KEEP + 1)
    w = PdfWriter()
    for p in PdfReader(src).pages[:KEEP]:
        w.add_page(p)
    for p in PdfReader(tail).pages:
        w.add_page(p)
    w.add_metadata({"/Title": "Hydra DSL v1.0"})
    out = "/mnt/user-data/outputs/" + src.rsplit("/", 1)[1]
    with open(out, "wb") as f:
        w.write(f)
    print(out, len(w.pages))
