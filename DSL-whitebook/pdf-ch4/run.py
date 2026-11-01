import sys, importlib
sys.path.insert(0, "/home/claude/wb")
from gen import build, render
from pypdf import PdfReader, PdfWriter
U = "/root/.claude/uploads/726f5677-52ad-5c9c-ad45-68d8648f5a54/"
jobs = [("content_en", U + "14f1ea74-Hydra_DSL_v_1.0_White_book.pdf", "Hydra_DSL_v_1.0_White_book.pdf"),
        ("content_fr", U + "0dd83e32-Hydra_DSL_v_1.0_Livre_blanc.pdf", "Hydra_DSL_v_1.0_Livre_blanc.pdf")]
for mod, src, name in jobs:
    m = importlib.import_module(mod)
    ch4 = f"/home/claude/wb/{mod}_ch4.pdf"
    build(ch4, render(m.SPEC), m.HEADER, m.FOOTER, 16)
    w = PdfWriter()
    r = PdfReader(src)
    for p in r.pages[:15]:
        w.add_page(p)
    for p in PdfReader(ch4).pages:
        w.add_page(p)
    w.add_metadata({"/Title": "Hydra DSL v1.0"})
    out = "/mnt/user-data/outputs/" + name
    with open(out, "wb") as f:
        w.write(f)
    print(name, len(w.pages))
