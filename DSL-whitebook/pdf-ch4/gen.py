"""Régénère le chapitre 4 du livre blanc (style identique) et le recolle."""
import re, sys
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer,
                                Flowable, KeepTogether, CondPageBreak, PageBreak)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from xml.sax.saxutils import escape

F = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("DV", F + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DVB", F + "DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("DVM", F + "DejaVuSansMono.ttf"))

INK = HexColor(0x142137); GREY = HexColor(0x57667a); RULE = HexColor(0xdce3eb)
DARK = HexColor(0x111d2a); RED = HexColor(0xe51924); ALT = HexColor(0xf4f7fa)
C_KEY = HexColor(0x88c9f9); C_PUN = HexColor(0xdeecf6); C_TXT = HexColor(0xe8edf2)
C_STR = HexColor(0xb6e3a2); C_COM = HexColor(0x91a6b5)
W, H = A4
X0, X1 = 56.0, 539.2756
CW = X1 - X0

sH1 = ParagraphStyle("h1", fontName="DVB", fontSize=21, leading=25, textColor=INK, spaceAfter=0)
sH2 = ParagraphStyle("h2", fontName="DVB", fontSize=13.5, leading=17, textColor=INK, spaceBefore=26, spaceAfter=10)
sH3 = ParagraphStyle("h3", fontName="DVB", fontSize=9.8, leading=13, textColor=INK, spaceBefore=12, spaceAfter=9)
sBody = ParagraphStyle("b", fontName="DV", fontSize=8.9, leading=13.5, textColor=INK, spaceBefore=2, spaceAfter=6)
sRole = ParagraphStyle("r", fontName="DV", fontSize=8.4, leading=13.5, textColor=GREY, spaceBefore=7, spaceAfter=4)
sCell = ParagraphStyle("c", fontName="DV", fontSize=8.0, leading=12, textColor=GREY)
sHead = ParagraphStyle("hc", fontName="DV", fontSize=8.0, leading=12, textColor=HexColor(0x8a9bb0))


def _split_comment(line):
    q = None
    for i, ch in enumerate(line):
        if ch in "\"'" and (q is None or q == ch):
            q = None if q else ch
        elif ch == "#" and q is None and (i == 0 or line[i - 1] in " \t"):
            return line[:i], line[i:]
    return line, ""


def tokens(line):
    code, com = _split_comment(line)
    out = []
    m = re.match(r"^(\s*(?:-\s+)?)([A-Za-z_$][\w.$<>\-]*)(:)(\s|$)", code)
    if m and not code.lstrip().startswith(("hdrctl", "sops", "age")):
        out += [(m.group(1), C_TXT), (m.group(2), C_KEY), (":", C_PUN)]
        code = code[m.end(3):]
    for part in re.split(r'("[^"]*")', code):
        if part:
            out.append((part, C_STR if part.startswith('"') and part.endswith('"') and len(part) > 1 else C_TXT))
    if com:
        out.append((com, C_COM))
    return out


class Code(Flowable):
    def __init__(self, text):
        super().__init__()
        self.lines = text.strip("\n").split("\n")
        self.height = 17 + (len(self.lines) - 1) * 12.8 + 18.8

    def wrap(self, aw, ah):
        return CW, self.height

    def draw(self):
        c = self.canv
        h = self.height
        c.setFillColor(RED); c.roundRect(0, h - 12, CW, 12, 6, stroke=0, fill=1)
        c.setFillColor(DARK); c.roundRect(0, 0, CW, h - 5, 6, stroke=0, fill=1)
        c.rect(0, h - 12, CW, 7, stroke=0, fill=1)
        y = h - 17
        for ln in self.lines:
            x = 13
            for txt, col in tokens(ln):
                c.setFillColor(col); c.setFont("DVM", 7.4)
                c.drawString(x, y, txt)
                x += pdfmetrics.stringWidth(txt, "DVM", 7.4)
            y -= 12.8


class Table(Flowable):
    def __init__(self, rows, cols):
        super().__init__()
        self.rows, self.cols = rows, cols   # cols: x offsets relative to X0 (cell text start)
        self.TW = 551.2756 - X0

    def _cells(self, row, style):
        out = []
        for i, txt in enumerate(row):
            w = (self.cols[i + 1] if i + 1 < len(self.cols) else self.TW) - self.cols[i] - 10
            p = Paragraph(txt, style); p.wrap(w, 1000); out.append(p)
        return out

    def wrap(self, aw, ah):
        self.layout = []
        for k, row in enumerate(self.rows):
            cells = self._cells(row, sHead if k == 0 else sCell)
            hh = max(p.height for p in cells)
            self.layout.append((cells, max(28, hh + 16)))
        self.height = sum(h for _, h in self.layout)
        return self.TW, self.height

    def draw(self):
        c = self.canv
        y = self.height
        for k, (cells, rh) in enumerate(self.layout):
            y -= rh
            c.setFillColor(DARK if k == 0 else (ALT if k % 2 == 0 else HexColor(0xffffff)))
            c.rect(0, y, self.TW, rh, stroke=0, fill=1)
            for i, p in enumerate(cells):
                p.drawOn(c, self.cols[i], y + rh - 10 - p.height + 2)
        c.setStrokeColor(RULE); c.setLineWidth(0.5); c.line(0, 0, self.TW, 0)


class H1(Flowable):
    def __init__(self, text):
        super().__init__(); self.p = Paragraph(text, sH1)

    def wrap(self, aw, ah):
        self.p.wrap(CW, 100); self.height = 37 + 14; return CW, self.height

    def draw(self):
        self.p.drawOn(self.canv, 0, self.height - 25)
        self.canv.setStrokeColor(RED); self.canv.setLineWidth(2)
        self.canv.line(0, self.height - 37, CW, self.height - 37)


def build(out, content, header_right, footer, first_page):
    def deco(c, doc):
        c.saveState()
        c.setStrokeColor(RULE); c.setLineWidth(1)
        c.line(48, H - 43, 547.2756, H - 43); c.line(48, H - 798.89, 547.2756, H - 798.89)
        c.setFont("DVB", 8); c.setFillColor(INK); c.drawString(48, H - 32, "HYDRA  /  DSL 1.0")
        c.setFont("DV", 7.5); c.setFillColor(GREY)
        c.drawRightString(547.2756, H - 32, header_right)
        c.drawString(48, H - 813, footer)
        c.drawRightString(547.2756, H - 813, f"{first_page + doc.page - 1:02d}")
        c.restoreState()
    doc = BaseDocTemplate(out, pagesize=A4, leftMargin=X0, rightMargin=W - X1,
                          topMargin=66, bottomMargin=H - 785)
    doc.addPageTemplates([PageTemplate("p", [Frame(X0, H - 785, CW, 785 - 66, 0, 0, 0, 0)], onPage=deco)])
    doc.build(content)


def render(spec):
    """Titres (h2, h3) toujours gardés avec le bloc qui suit."""
    out, pending = [], []
    for kind, val in spec:
        if kind == "h1":
            out.append(H1(escape(val))); continue
        if kind == "h2":
            pending.append(Paragraph(escape(val), sH2)); continue
        if kind == "h2top":                       # h2 en haut de page (sans espace avant)
            pending.append(Paragraph(escape(val), ParagraphStyle("h2t", parent=sH2, spaceBefore=0))); continue
        if kind == "pagebreak":
            out.append(PageBreak()); continue
        if kind == "h3":
            pending.append(Paragraph(escape(val), sH3)); continue
        if kind == "code":
            el = [Code(val)]
        elif kind == "role":
            el = [Paragraph(val, sRole)]
        elif kind == "p":
            el = [Paragraph(val, sBody)]
        elif kind == "table":
            rows, cols = val
            el = [Spacer(1, 4), Table(rows, cols), Spacer(1, 6)]
        out.append(KeepTogether(pending + el) if pending else (el[0] if len(el) == 1 else KeepTogether(el)))
        pending = []
    return out
