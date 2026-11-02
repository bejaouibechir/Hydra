"""Pages 1-2 d'origine (couverture, sommaire) + pages 3-fin régénérées (ch. 1 à 4)."""
import sys, importlib, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gen import build, render
from pypdf import PdfReader, PdfWriter
SRC, OUT = sys.argv[1], sys.argv[2]          # dossier des PDF d'origine, dossier de sortie
KEEP = 2
for mod, name in [("content1_en", "Hydra_DSL_v_1.0_White_book.pdf"),
                  ("content1_fr", "Hydra_DSL_v_1.0_Livre_blanc.pdf")]:
    m = importlib.import_module(mod)
    tail = os.path.join(OUT, mod + "_tail.pdf")
    build(tail, render(m.SPEC), m.HEADER, m.FOOTER, KEEP + 1)
    w = PdfWriter()
    for p in PdfReader(os.path.join(SRC, name)).pages[:KEEP]:
        w.add_page(p)
    for p in PdfReader(tail).pages:
        w.add_page(p)
    w.add_metadata({"/Title": "Hydra DSL v1.0"})
    with open(os.path.join(OUT, name), "wb") as f:
        w.write(f)
    os.remove(tail)
    print(name, len(w.pages))
