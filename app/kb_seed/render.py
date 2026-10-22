"""Render branded policy PDFs from the seed content.

Design follows the Emids brand system: dark canvas cover with the teal
accent band, warm-white typography, mono technical labels; light content
pages with a teal running header, hairline tables and a mono footer with
classification + page numbers (PAGE 2 OF 9, resolved via the numbered-canvas
two-pass trick).

Fonts: Inter / JetBrains Mono are used when TTFs are dropped in
app/kb_seed/fonts/ (Inter-Regular.ttf, Inter-Bold.ttf, JetBrainsMono-
Regular.ttf, JetBrainsMono-Bold.ttf). Without them the renderer falls back
to Helvetica / Courier so the seed never depends on environment specifics.

Public API:
    render_document(doc, logo_path=None) -> (pdf_bytes, page_count)
"""
from __future__ import annotations

import html
import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# ---- brand tokens ----------------------------------------------------------
CANVAS = colors.HexColor("#0E0E0E")
SURFACE2 = colors.HexColor("#262626")
WARM = colors.HexColor("#F2F2F0")
TEAL = colors.HexColor("#47a2b0")
TEAL_DEEP = colors.HexColor("#2a7682")
TEAL_LIGHT = colors.HexColor("#ABC7CA")
INK = colors.HexColor("#1F2424")
INK_SOFT = colors.HexColor("#5A6565")
HAIRLINE = colors.HexColor("#C9CFCE")
NOTE_BG = colors.HexColor("#EDF4F5")
ZEBRA = colors.HexColor("#EEF2F2")

PAGE_W, PAGE_H = A4
MARGIN = 56
USABLE_W = PAGE_W - 2 * MARGIN

FONT_DIR = Path(__file__).parent / "fonts"

_fonts: dict[str, str] = {"sans": "Helvetica", "sans-bold": "Helvetica-Bold", "mono": "Courier-Bold"}


def _has_font(name: str) -> bool:
    try:
        pdfmetrics.getFont(name)
        return True
    except Exception:
        return False


def _try_register():
    files = [
        ("Inter-Regular.ttf", "Inter"),
        ("Inter-Bold.ttf", "Inter-Bold"),
        ("JetBrainsMono-Regular.ttf", "JBMono"),
        ("JetBrainsMono-Bold.ttf", "JBMono-Bold"),
    ]
    for path, name in files:
        full = FONT_DIR / path
        if full.exists():
            try:
                pdfmetrics.registerFont(TTFont(name, str(full)))
            except Exception:
                pass
    if _has_font("Inter"):
        _fonts["sans"] = "Inter"
    if _has_font("Inter-Bold"):
        _fonts["sans-bold"] = "Inter-Bold"
    if _has_font("JBMono"):
        _fonts["mono"] = "JBMono"
    elif _has_font("JBMono-Bold"):
        _fonts["mono"] = "JBMono-Bold"


_try_register()


def _esc(text) -> str:
    return html.escape(str(text))


def _tracked_width(text: str, font: str, size: float, space: float) -> float:
    return pdfmetrics.stringWidth(text, font, size) + space * max(len(text) - 1, 0)


def _tracked_left(canv, x, y, text, font, size, space, color):
    to = canv.beginText(x, y)
    to.setFont(font, size)
    to.setCharSpace(space)
    to.setFillColor(color)
    to.textOut(text)
    canv.drawText(to)


def _tracked_right(canv, x_right, y, text, font, size, space, color):
    x = x_right - _tracked_width(text, font, size, space)
    _tracked_left(canv, x, y, text, font, size, space, color)


# ---- paragraph styles ------------------------------------------------------
def _styles():
    sans, bold, mono = _fonts["sans"], _fonts["sans-bold"], _fonts["mono"]
    return {
        "h1": ParagraphStyle("h1", fontName=bold, fontSize=12.5, leading=15,
                             textColor=TEAL_DEEP, spaceBefore=16, spaceAfter=7),
        "h2": ParagraphStyle("h2", fontName=bold, fontSize=10.5, leading=13.5,
                             textColor=INK, spaceBefore=11, spaceAfter=5),
        "p": ParagraphStyle("p", fontName=sans, fontSize=9.7, leading=14.6,
                            textColor=INK, spaceAfter=7),
        "li": ParagraphStyle("li", fontName=sans, fontSize=9.7, leading=14.2,
                             textColor=INK, leftIndent=16, bulletIndent=4,
                             spaceAfter=3.5),
        "note": ParagraphStyle("note", fontName=sans, fontSize=9.3, leading=13.5,
                               textColor=TEAL_DEEP),
        "tcell": ParagraphStyle("tcell", fontName=sans, fontSize=8.8, leading=11.8,
                                textColor=INK),
        "thead": ParagraphStyle("thead", fontName=bold, fontSize=8.6, leading=11,
                                textColor=WARM),
    }


# ---- story -----------------------------------------------------------------
def _build_story(doc: dict, styles: dict):
    story: list = []
    blocks = doc["blocks"]
    i = 0
    while i < len(blocks):
        kind, *payload = blocks[i]
        if kind == "h":
            head = Paragraph(_esc(payload[0]), styles["h1"])
            nxt = blocks[i + 1] if i + 1 < len(blocks) else None
            if nxt and nxt[0] == "p":
                story.append(KeepTogether([head, Paragraph(_esc(nxt[1]), styles["p"])]))
                i += 2
                continue
            if nxt and nxt[0] == "bullets":
                first, *rest = nxt[1]
                story.append(KeepTogether(
                    [head, Paragraph(_esc(first), styles["li"], bulletText="–")]
                ))
                for item in rest:
                    story.append(Paragraph(_esc(item), styles["li"], bulletText="–"))
                story.append(Spacer(1, 4))
                i += 2
                continue
            story.append(head)
        elif kind == "h2":
            story.append(Paragraph(_esc(payload[0]), styles["h2"]))
        elif kind == "p":
            story.append(Paragraph(_esc(payload[0]), styles["p"]))
        elif kind == "bullets":
            items = payload[0]
            for item in items:
                story.append(Paragraph(_esc(item), styles["li"], bulletText="–"))
            story.append(Spacer(1, 4))
        elif kind == "table":
            head, rows = payload
            story.append(_table(head, rows, styles))
            story.append(Spacer(1, 6))
        elif kind == "note":
            inner = Paragraph(_esc(payload[0]), styles["note"])
            box = Table([[inner]], colWidths=[USABLE_W], hAlign="CENTER")
            box.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), NOTE_BG),
                ("LINEBEFORE", (0, 0), (0, -1), 2.4, TEAL),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]))
            story.append(KeepTogether([box, Spacer(1, 8)]))
        i += 1
    story.append(Spacer(1, 2))
    return story


def _col_weights(head, rows, ncols):
    lens = [0] * ncols
    for row in [head, *rows]:
        for c in range(ncols):
            lens[c] += len(str(row[c])) if c < len(row) else 0
    lens = [max(l, 8) for l in lens]
    total = sum(lens)
    return [max(USABLE_W * l / total, USABLE_W * 0.10) for l in lens]


def _table(head, rows, styles):
    ncols = len(head)
    data = [[Paragraph(_esc(h), styles["thead"]) for h in head]]
    for row in rows:
        data.append([Paragraph(_esc(v), styles["tcell"]) for v in row])
    t = Table(data, colWidths=_col_weights(head, rows, ncols), repeatRows=1, hAlign="CENTER")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TEAL_DEEP),
        ("TEXTCOLOR", (0, 0), (-1, 0), WARM),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEBRA]),
        ("GRID", (0, 0), (-1, -1), 0.4, HAIRLINE),
        ("BOX", (0, 0), (-1, -1), 0.4, HAIRLINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


# ---- page painters ---------------------------------------------------------
def _cover_painter(doc: dict, logo_path: str | None):
    classification = {
        "employee": "INTERNAL / ALL EMPLOYEES",
        "hr": "CONFIDENTIAL / HR INTERNAL",
    }[doc["audience"]]

    def paint(canv: rl_canvas.Canvas, _docobj):
        canv.saveState()
        canv.setFillColor(CANVAS)
        canv.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
        canv.setFillColor(TEAL)
        canv.rect(0, PAGE_H - 10, PAGE_W, 10, stroke=0, fill=1)
        canv.setFillColor(TEAL_LIGHT)
        canv.rect(0, PAGE_H - 12, PAGE_W / 3.0, 2, stroke=0, fill=1)

        if logo_path and Path(logo_path).exists():
            try:
                canv.drawImage(logo_path, MARGIN, PAGE_H - 118, width=128, height=55,
                               mask="auto")
            except Exception:
                pass

        y = PAGE_H - 190
        _tracked_left(canv, MARGIN, y, "EMIDS TECHNOLOGIES / KNOWLEDGE BASE",
                      _fonts["mono"], 8, 2.4, TEAL_LIGHT)

        y -= 10
        canv.setFillColor(TEAL)
        canv.rect(MARGIN, y, 46, 3, stroke=0, fill=1)

        y -= 52
        canv.setFillColor(WARM)
        canv.setFont(_fonts["sans-bold"], 27)
        for line in simpleSplit(doc["title"], _fonts["sans-bold"], 27, USABLE_W):
            canv.drawString(MARGIN, y, line)
            y -= 33

        y -= 6
        canv.setFillColor(colors.HexColor("#A9B2B1"))
        canv.setFont(_fonts["sans"], 10.2)
        for line in simpleSplit(doc["summary"], _fonts["sans"], 10.2, USABLE_W * 0.88):
            canv.drawString(MARGIN, y, line)
            y -= 15.5

        meta = [
            ("REF", str(doc["ref"])),
            ("VERSION", doc["version"]),
            ("EFFECTIVE", doc["effective_date"].strftime("%d %b %Y")),
            ("FOR", "ALL EMPLOYEES" if doc["audience"] == "employee" else "HR TEAM ONLY"),
            ("CLASSIFICATION", classification),
        ]
        canv.setStrokeColor(SURFACE2)
        canv.setLineWidth(0.7)
        canv.line(MARGIN, 168, PAGE_W - MARGIN, 168)
        yy = 142
        for label, value in meta:
            _tracked_left(canv, MARGIN, yy, label, _fonts["mono"], 7.6, 1.8, TEAL)
            canv.setFillColor(colors.HexColor("#9AA4A3"))
            canv.setFont(_fonts["mono"], 7.6)
            canv.drawString(MARGIN + 112, yy, value.upper())
            yy -= 16.5

        canv.setStrokeColor(SURFACE2)
        canv.line(MARGIN, 52, PAGE_W - MARGIN, 52)
        _tracked_left(canv, MARGIN, 38, "HR DESK / INTERNAL POLICY LIBRARY",
                      _fonts["mono"], 7.0, 1.6, colors.HexColor("#6E7877"))
        _tracked_right(canv, PAGE_W - MARGIN, 38, classification,
                       _fonts["mono"], 7.0, 1.6, colors.HexColor("#6E7877"))
        canv.restoreState()

    return paint


def _body_page(doc: dict):
    """Running header (category / ref + teal rule) and the static footer."""

    def paint(canv: rl_canvas.Canvas, _docobj):
        canv.saveState()
        # header
        _tracked_left(canv, MARGIN, PAGE_H - 34, doc["category"].upper(),
                      _fonts["mono"], 6.8, 1.6, INK_SOFT)
        _tracked_right(canv, PAGE_W - MARGIN, PAGE_H - 34, doc["ref"],
                       _fonts["mono"], 6.8, 1.6, INK_SOFT)
        canv.setStrokeColor(TEAL)
        canv.setLineWidth(1.6)
        canv.line(MARGIN, PAGE_H - 42, PAGE_W - MARGIN, PAGE_H - 42)
        # footer (left half; PAGE X OF Y is drawn by _NumberedCanvas)
        canv.setStrokeColor(HAIRLINE)
        canv.setLineWidth(0.5)
        canv.line(MARGIN, 40, PAGE_W - MARGIN, 40)
        _tracked_left(canv, MARGIN, 27, "EMIDS TECHNOLOGIES / INTERNAL POLICY",
                      _fonts["mono"], 6.4, 1.2, INK_SOFT)
        canv.restoreState()

    return paint


class _NumberedCanvas(rl_canvas.Canvas):
    """Draws `PAGE X OF Y` in a second pass once the total is known."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_states: list[dict] = []

    def showPage(self):
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            self.setFillColor(INK_SOFT)
            self.setFont(_fonts["mono"], 6.4)
            self.drawRightString(PAGE_W - MARGIN, 27, f"PAGE {self._pageNumber} OF {total}")
            super().showPage()
        super().save()


def render_document(doc: dict, logo_path: str | None = None) -> tuple[bytes, int]:
    """Render one document. Returns (pdf bytes, page count)."""
    styles = _styles()
    cover_tpl = PageTemplate(
        id="cover",
        frames=[Frame(MARGIN, MARGIN, USABLE_W, PAGE_H - 2 * MARGIN, id="cover-frame")],
        onPage=_cover_painter(doc, logo_path),
    )
    body_tpl = PageTemplate(
        id="body",
        frames=[Frame(MARGIN, 56, USABLE_W, PAGE_H - 56 - 64, id="body-frame")],
        onPage=_body_page(doc),
    )

    story = [NextPageTemplate("body"), PageBreak(), *_build_story(doc, styles)]

    sink = io.BytesIO()
    template = BaseDocTemplate("kb.pdf", pagesize=A4, pageTemplates=[cover_tpl, body_tpl])
    template.build(story, sink, canvasmaker=_NumberedCanvas)
    return sink.getvalue(), template.page
