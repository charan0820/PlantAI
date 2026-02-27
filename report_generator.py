"""
report_generator.py
===================
Drop this file into your PlantAI project root.

Usage (in your Flask app.py):
    from report_generator import generate_enhanced_report
    pdf_bytes = generate_enhanced_report(
        plant="Strawberry",
        condition="Leaf scorch",
        confidence=97.77,
        image_path="path/to/uploaded/leaf.jpg",   # optional
        generated_on="February 27, 2026 at 19:31" # optional
    )
    # Then stream it as a download:
    from flask import send_file
    import io
    return send_file(io.BytesIO(pdf_bytes),
                     mimetype='application/pdf',
                     as_attachment=True,
                     download_name='PlantCare_Report.pdf')
"""

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    Flowable, HRFlowable, Image, PageBreak, Paragraph,
    SimpleDocTemplate, Spacer, Table, TableStyle,
)

# ─────────────────────────────────────────────────────────────
# Colour palette  (matches your existing PlantCare green brand)
# ─────────────────────────────────────────────────────────────
DARK_GREEN    = colors.HexColor("#1B4332")
MID_GREEN     = colors.HexColor("#2D6A4F")
ACCENT_GREEN  = colors.HexColor("#52B788")
LIGHT_GREEN   = colors.HexColor("#D8F3DC")
DANGER_RED    = colors.HexColor("#C0392B")
WARN_ORANGE   = colors.HexColor("#E67E22")
LIGHT_GRAY    = colors.HexColor("#F8F9FA")
MID_GRAY      = colors.HexColor("#6C757D")
DARK_GRAY     = colors.HexColor("#343A40")
WHITE         = colors.white

PAGE_W, PAGE_H = A4

# ─────────────────────────────────────────────────────────────
# Disease knowledge base
# Add more diseases here as your model supports them.
# ─────────────────────────────────────────────────────────────
DISEASE_DATA = {
    "strawberry___leaf_scorch": {
        "pathogen":   "Diplocarpon earlianum (Ellis & Everh.) F.A. Wolf",
        "taxonomy": [
            ("Kingdom",     "Fungi"),
            ("Phylum",      "Ascomycota"),
            ("Class",       "Leotiomycetes"),
            ("Order",       "Helotiales"),
            ("Family",      "Dermateaceae"),
            ("Genus",       "Diplocarpon"),
            ("Species",     "D. earlianum"),
            ("Common Name", "Strawberry Leaf Scorch"),
        ],
        "overview": (
            "Strawberry Leaf Scorch is caused by the ascomycete fungus "
            "<i>Diplocarpon earlianum</i>. The pathogen overwinters in infected "
            "leaf debris as apothecia and initiates primary infections in spring "
            "when ascospores are released during rain. Asexual conidia produced "
            "in acervuli drive rapid secondary spread. Optimal conditions are "
            "18–24°C with leaf wetness periods of 6+ hours."
        ),
        "symptoms": [
            ("Stage 1 — Early Infection (Days 1–7)",
             "Tiny (1–3 mm) irregular purple-red spots appear on the upper leaf "
             "surface. Spots are scattered and commonly mistaken for insect damage."),
            ("Stage 2 — Lesion Expansion (Days 7–14)",
             "Spots enlarge to 3–6 mm with dark-purple margins and tan/grey necrotic "
             "centres. Lesions coalesce along leaf veins, giving a scorched appearance."),
            ("Stage 3 — Advanced Necrosis (Days 14–21)",
             "Large irregular blotches cover significant leaf area. Leaf edges curl "
             "upward, turn brown, and dry out. Severe defoliation may begin."),
            ("Stage 4 — Secondary Spread (Day 21+)",
             "Acervuli (black spore-bearing structures) visible under magnification. "
             "Rain-splashed conidia infect neighbouring plants. Yield significantly reduced."),
        ],
        "organic_treatments": [
            ("Copper hydroxide 77% WP",   "2.5 g / litre water",       "Every 7–10 days during wet seasons"),
            ("Neem oil (3,000 ppm azadirachtin)", "5 ml / litre + surfactant", "Every 10–14 days; avoid midday"),
            ("Potassium bicarbonate",      "5 g / litre water",          "Preventative; every 7 days"),
            ("Bacillus subtilis (Serenade)", "Per label rate",           "Every 5–7 days; compatible with copper"),
        ],
        "chemical_treatments": [
            ("Myclobutanil",   "Rally 40WSP",   "0.34–0.57 g/L",  "Every 10–14 days; max 4 apps/season"),
            ("Captan",         "Captan 50WP",   "2.0–3.0 g/L",    "Every 7–10 days; do not mix with oils"),
            ("Tebuconazole",   "Elite 45DF",    "0.28 g/L",       "Every 14 days; FRAC Group 3"),
            ("Pyraclostrobin", "Cabrio EG",     "0.56 g/L",       "Max 2 consecutive apps; rotate groups"),
            ("Azoxystrobin",   "Quadris SC",    "0.77 ml/L",      "FRAC Group 11; rotate to avoid resistance"),
        ],
        "risks": [
            ("Infection Risk",     "HIGH",     DANGER_RED,
             "Spreads rapidly via rain-splash conidia. Early isolation is critical."),
            ("Yield Impact",       "HIGH",     DANGER_RED,
             "Severe infections reduce marketable yield by 30–70% via premature defoliation."),
            ("Spread Mechanism",   "MODERATE", WARN_ORANGE,
             "Primary: rain splash and overhead irrigation. Secondary: tools, footwear, transplants."),
            ("Environmental Risk", "MODERATE", WARN_ORANGE,
             "Peak risk at 18–24°C with >6 h leaf wetness — typical of spring/autumn rainy periods."),
            ("Resistance Risk",    "LOW",      ACCENT_GREEN,
             "Resistance possible with FRAC Groups 3 and 11. Rotate chemical classes."),
        ],
        "prevention": [
            "Use certified disease-free transplants from reputable nurseries.",
            "Select resistant cultivars (e.g., Allstar, Delite, Lateglow).",
            "Implement drip irrigation — avoid overhead watering to keep foliage dry.",
            "Maintain plant spacing ≥ 30 cm to promote airflow and reduce canopy humidity.",
            "Remove and destroy infected debris promptly; do not compost diseased material.",
            "Apply a preventative fungicide programme before disease establishment.",
            "Sanitise tools, boots, and equipment between rows and between fields.",
            "Scout weekly from early spring; act at first sign of lesions.",
            "Apply balanced fertilisation; avoid excess nitrogen which increases susceptibility.",
            "Rotate strawberry planting sites every 2–3 years.",
        ],
    },
    # ── Template for additional diseases ──────────────────────────────────
    # "tomato___early_blight": { ... }
}

# ─────────────────────────────────────────────────────────────
# Custom flowables
# ─────────────────────────────────────────────────────────────

class SectionHeader(Flowable):
    """Green section header bar with left accent stripe."""
    def __init__(self, text, width):
        super().__init__()
        self._text = text
        self.width = width
        self.height = 28

    def draw(self):
        c = self.canv
        c.setFillColor(LIGHT_GREEN)
        c.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        c.setFillColor(MID_GREEN)
        c.rect(0, 0, 5, self.height, fill=1, stroke=0)
        c.setFillColor(DARK_GREEN)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(14, 8, self._text)

    def wrap(self, *_):
        return self.width, self.height


class StageBlock(Flowable):
    """Coloured stage label bar for symptom progression."""
    def __init__(self, text, width):
        super().__init__()
        self._text = text
        self.width = width
        self.height = 22

    def draw(self):
        c = self.canv
        c.setFillColor(MID_GREEN)
        c.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(10, 6, self._text)

    def wrap(self, *_):
        return self.width, self.height


# ─────────────────────────────────────────────────────────────
# Style factory
# ─────────────────────────────────────────────────────────────

def _styles():
    def S(name, **kw):
        kw.setdefault("fontName", "Helvetica")
        kw.setdefault("fontSize", 10)
        kw.setdefault("leading", 14)
        kw.setdefault("textColor", DARK_GRAY)
        return ParagraphStyle(name, **kw)

    return {
        "title":     S("title",  fontName="Helvetica-Bold", fontSize=22,
                        textColor=WHITE, leading=28, alignment=TA_CENTER),
        "subtitle":  S("sub",    fontSize=11, textColor=LIGHT_GREEN, alignment=TA_CENTER),
        "body":      S("body",   fontSize=10, leading=15, alignment=TA_JUSTIFY),
        "bold":      S("bold",   fontName="Helvetica-Bold", fontSize=10, leading=15),
        "small":     S("sm",     fontSize=8,  textColor=MID_GRAY, leading=12),
        "sm_bold":   S("smb",   fontName="Helvetica-Bold", fontSize=8,
                        textColor=MID_GRAY, leading=12),
        "bullet":    S("bul",   fontSize=10, leading=15,
                        leftIndent=16, bulletIndent=4),
        "th":        S("th",    fontName="Helvetica-Bold", fontSize=9,
                        textColor=WHITE, alignment=TA_CENTER, leading=13),
        "td":        S("td",    fontSize=9,  leading=13, alignment=TA_LEFT),
        "stage_desc":S("sdesc", fontSize=10, leading=14, alignment=TA_JUSTIFY,
                        leftIndent=10, spaceAfter=6, textColor=DARK_GRAY),
        "disc":      S("disc",  fontSize=8,  textColor=MID_GRAY, leading=11,
                        alignment=TA_JUSTIFY),
    }


# ─────────────────────────────────────────────────────────────
# Table helper
# ─────────────────────────────────────────────────────────────

def _make_table(rows, col_widths, header_bg=DARK_GREEN,
                row_colors=(WHITE, LIGHT_GREEN), grid_color=ACCENT_GREEN):
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  header_bg),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), row_colors),
        ("GRID",          (0, 0), (-1, -1), 0.3, grid_color),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 7),
    ]))
    return t


# ─────────────────────────────────────────────────────────────
# Main public function
# ─────────────────────────────────────────────────────────────

def generate_enhanced_report(
    plant: str,
    condition: str,
    confidence: float,
    image_path: str = None,
    generated_on: str = None,
    report_id: str = None,
) -> bytes:
    """
    Build and return the enhanced PDF as raw bytes.

    Parameters
    ----------
    plant        : e.g. "Strawberry"
    condition    : e.g. "Leaf scorch"
    confidence   : float, e.g. 97.77
    image_path   : absolute path to the analysed leaf image (optional)
    generated_on : human-readable datetime string (defaults to now)
    report_id    : custom report ID string (auto-generated if omitted)
    """

    generated_on = generated_on or datetime.now().strftime("%B %d, %Y at %H:%M")
    report_id    = report_id    or datetime.now().strftime("PC-%Y-%m%d-%H%M")

    # Look up disease data -------------------------------------------------
    key = f"{plant}___{condition}".lower().replace(" ", "_").replace("___", "___")
    # Try a few normalisation attempts
    data = (
        DISEASE_DATA.get(key) or
        DISEASE_DATA.get(f"{plant.lower()}___{condition.lower().replace(' ','_')}") or
        DISEASE_DATA.get(f"{plant.lower()}___{'_'.join(condition.lower().split())}")
    )
    if not data:
        raise ValueError(
            f"No disease data found for '{plant} – {condition}'. "
            f"Add an entry to DISEASE_DATA in report_generator.py."
        )

    S   = _styles()
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=1.5*cm, bottomMargin=2*cm,
        title="PlantCare AI — Enhanced Diagnosis Report",
        author="PlantCare AI",
    )
    W     = doc.width
    story = []

    # ── Header banner ──────────────────────────────────────────────────────
    hdr = Table(
        [[Paragraph("PlantCare AI", S["title"])]],
        colWidths=[W],
    )
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), DARK_GREEN),
        ("TOPPADDING",    (0,0),(-1,-1), 18),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
    ]))
    story.append(hdr)

    sub = Table(
        [[Paragraph("Enhanced Plant Disease Diagnosis Report", S["subtitle"])]],
        colWidths=[W],
    )
    sub.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), MID_GREEN),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 14),
    ]))
    story.append(sub)
    story.append(Spacer(1, 12))

    # ── Summary card ───────────────────────────────────────────────────────
    summary = [
        [Paragraph(h, S["th"]) for h in
         ["Plant Type", "Condition Detected", "AI Confidence", "Report ID"]],
        [
            Paragraph(plant, S["td"]),
            Paragraph(f'<font color="#C0392B"><b>{condition}</b></font>', S["td"]),
            Paragraph(f"<b>{confidence:.2f}%</b>", S["td"]),
            Paragraph(report_id, S["small"]),
        ],
    ]
    story.append(_make_table(summary, [W*0.28, W*0.24, W*0.20, W*0.28]))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        f"Generated on {generated_on}  ·  Model: MobileNetV2 (Transfer Learning) "
        f"— PlantVillage Dataset", S["small"]))
    story.append(Spacer(1, 16))

    # ── Analysed image (if provided) ────────────────────────────────────────
    if image_path:
        try:
            img = Image(image_path, width=7*cm, height=5*cm, kind='proportional')
            img_table = Table([[img]], colWidths=[W])
            img_table.setStyle(TableStyle([
                ("ALIGN",         (0,0),(-1,-1), "CENTER"),
                ("BACKGROUND",    (0,0),(-1,-1), LIGHT_GRAY),
                ("TOPPADDING",    (0,0),(-1,-1), 8),
                ("BOTTOMPADDING", (0,0),(-1,-1), 8),
            ]))
            story.append(Paragraph("<b>Analysed Leaf Image</b>", S["bold"]))
            story.append(Spacer(1, 4))
            story.append(img_table)
            story.append(Spacer(1, 14))
        except Exception:
            pass  # skip image silently if path is bad

    # ══════════════════════════════════════════════════════════════════════
    # Section 1 — Scientific Overview
    # ══════════════════════════════════════════════════════════════════════
    story.append(SectionHeader("1.  Scientific Overview & Pathogen Information", W))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"<b>Causal Pathogen:</b>  {data['pathogen']}", S["bold"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(data["overview"], S["body"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("<b>Taxonomic Classification</b>", S["bold"]))
    story.append(Spacer(1, 5))
    tax_rows = [[Paragraph("<b>Rank</b>", S["th"]),
                 Paragraph("<b>Classification</b>", S["th"])]]
    for rank, val in data["taxonomy"]:
        disp = f"<i>{val}</i>" if rank in ("Species", "Genus") else val
        tax_rows.append([Paragraph(rank, S["sm_bold"]), Paragraph(disp, S["td"])])
    story.append(_make_table(tax_rows, [W*0.30, W*0.70]))
    story.append(Spacer(1, 18))

    # ══════════════════════════════════════════════════════════════════════
    # Section 2 — Symptom Progression
    # ══════════════════════════════════════════════════════════════════════
    story.append(SectionHeader("2.  Symptom Progression", W))
    story.append(Spacer(1, 10))
    for stage, desc in data["symptoms"]:
        story.append(StageBlock(stage, W))
        story.append(Paragraph(desc, S["stage_desc"]))
        story.append(Spacer(1, 5))
    story.append(Spacer(1, 10))

    # ══════════════════════════════════════════════════════════════════════
    # Section 3a — Organic Treatments
    # ══════════════════════════════════════════════════════════════════════
    story.append(SectionHeader("3.  Treatment Protocols", W))
    story.append(Spacer(1, 10))

    story.append(Paragraph("<b>3a.  Organic / Biological Treatments</b>", S["bold"]))
    story.append(Spacer(1, 5))
    org_rows = [[Paragraph(h, S["th"]) for h in
                 ["Product / Treatment", "Dosage", "Application Frequency"]]]
    for row in data["organic_treatments"]:
        org_rows.append([Paragraph(c, S["td"]) for c in row])
    story.append(_make_table(org_rows, [W*0.38, W*0.28, W*0.34]))
    story.append(Spacer(1, 12))

    # ── Section 3b — Chemical Treatments ──────────────────────────────────
    story.append(Paragraph("<b>3b.  Chemical Fungicide Treatments</b>", S["bold"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Always follow label directions. Rotate between FRAC groups to prevent "
        "resistance. Strictly observe pre-harvest intervals (PHI).", S["small"]))
    story.append(Spacer(1, 5))
    chem_rows = [[Paragraph(h, S["th"]) for h in
                  ["Active Ingredient", "Trade Name", "Dosage", "Application Notes"]]]
    for row in data["chemical_treatments"]:
        chem_rows.append([Paragraph(c, S["td"]) for c in row])
    story.append(_make_table(
        chem_rows, [W*0.22, W*0.18, W*0.18, W*0.42],
        header_bg=colors.HexColor("#6B2737"),
        row_colors=(WHITE, colors.HexColor("#FFF5F5")),
        grid_color=colors.HexColor("#FFBDBD"),
    ))
    story.append(Spacer(1, 18))

    # ══════════════════════════════════════════════════════════════════════
    # Section 4 — Risk Assessment
    # ══════════════════════════════════════════════════════════════════════
    story.append(SectionHeader("4.  Risk Assessment & Spread Patterns", W))
    story.append(Spacer(1, 10))
    for label, level, lvl_color, desc in data["risks"]:
        risk_row = [[
            Paragraph(f"<b>{label}</b>", S["bold"]),
            Paragraph(f"<b>{level}</b>", ParagraphStyle(
                "lvl", fontName="Helvetica-Bold", fontSize=10,
                textColor=lvl_color, alignment=TA_CENTER, leading=14)),
            Paragraph(desc, S["body"]),
        ]]
        rt = Table(risk_row, colWidths=[W*0.24, W*0.14, W*0.62])
        rt.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), LIGHT_GRAY),
            ("BACKGROUND",    (1,0),(1,0),   colors.HexColor("#FFF8E1")),
            ("GRID",          (0,0),(-1,-1), 0.3, colors.HexColor("#DEE2E6")),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
            ("TOPPADDING",    (0,0),(-1,-1), 8),
            ("BOTTOMPADDING", (0,0),(-1,-1), 8),
            ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ]))
        story.append(rt)
        story.append(Spacer(1, 4))
    story.append(Spacer(1, 14))

    # ══════════════════════════════════════════════════════════════════════
    # Section 5 — Prevention Guidelines
    # ══════════════════════════════════════════════════════════════════════
    story.append(SectionHeader("5.  Prevention Guidelines", W))
    story.append(Spacer(1, 10))
    for i, item in enumerate(data["prevention"], 1):
        story.append(Paragraph(f"<b>{i:02d}.</b>  {item}", S["bullet"]))
        story.append(Spacer(1, 4))
    story.append(Spacer(1, 18))

    # ── Footer disclaimer ─────────────────────────────────────────────────
    story.append(HRFlowable(width=W, thickness=0.8, color=ACCENT_GREEN))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Disclaimer & Limitations", ParagraphStyle(
        "dh", fontName="Helvetica-Bold", fontSize=9, textColor=MID_GRAY)))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "This report was generated by PlantCare AI using a MobileNetV2 deep-learning model "
        "trained on the PlantVillage dataset. The AI confidence score reflects probabilistic "
        "model output and does not constitute a definitive agronomic diagnosis. Results may "
        "not account for co-infections, growth stage variation, or local environmental factors. "
        "Treatment recommendations are for informational purposes only and are based on "
        "generalised agronomic literature. Verify pesticide registrations and pre-harvest "
        "intervals with local regulatory authorities before use. For critical crop-protection "
        "decisions consult a qualified plant pathologist or certified crop adviser. "
        "PlantCare AI and its developers accept no liability for crop losses, regulatory "
        "violations, or adverse outcomes arising from reliance on this report.",
        S["disc"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"© 2026 PlantCare AI  ·  Smart Bridge Hyderabad  ·  "
        f"Report ID: {report_id}  ·  {generated_on}",
        ParagraphStyle("ft", fontName="Helvetica", fontSize=7,
                       textColor=MID_GRAY, alignment=TA_CENTER)))

    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────
# Quick local test  →  python report_generator.py
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    pdf_bytes = generate_enhanced_report(
        plant="Strawberry",
        condition="Leaf scorch",
        confidence=97.77,
        image_path="/home/claude/leaf_0_FormXob.cda037be1734ad76b1f78272e56142ec.jpg",
        generated_on="February 27, 2026 at 19:31",
        report_id="PC-2026-0227-1931",
    )
    out = "/mnt/user-data/outputs/PlantCare_Enhanced_Report.pdf"
    with open(out, "wb") as f:
        f.write(pdf_bytes)
    print(f"Written {len(pdf_bytes):,} bytes → {out}")