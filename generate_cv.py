"""
CV Generator – Sebastian Motzo Fernandez
Usage:
  python3 generate_cv.py output.pdf job_data.json
"""
import sys, json, os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY

# ── Paths ──────────────────────────────────────────────────────────────
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
PROFILE   = os.path.join(BASE_DIR, "profile_base.json")
FOTO_PATH = os.path.join(BASE_DIR, "foto.jpg")
_ALT = "/sessions/happy-wizardly-tesla/mnt/Bot aplicaciones trabajo/foto_sebastian.png"
if not os.path.exists(FOTO_PATH) and os.path.exists(_ALT):
    try:
        from PIL import Image as _Img
        _img = _Img.open(_ALT)
        _img = _img.resize((400, 400), _Img.LANCZOS)
        if _img.mode == "RGBA":
            _bg = _Img.new("RGB", _img.size, (255, 255, 255))
            _bg.paste(_img, mask=_img.split()[3])
            _img = _bg
        _img.save(FOTO_PATH, "JPEG", quality=88, optimize=True)
    except Exception:
        FOTO_PATH = _ALT
OUTPUT = os.path.join(BASE_DIR, "CV_Sebastian_Motzo.pdf")

# ── Colors ─────────────────────────────────────────────────────────────
C_DARK   = colors.HexColor("#1a2e4a")
C_MID    = colors.HexColor("#2c4a6e")
C_ACCENT = colors.HexColor("#7a9ec0")
C_LIGHT  = colors.HexColor("#eef2f7")
C_WHITE  = colors.white
C_GRAY   = colors.HexColor("#3d3d3d")
C_LGRAY  = colors.HexColor("#666666")

# ── Labels (DE / EN) ────────────────────────────────────────────────────
LABELS = {
    "de": {
        "personal_data":  "Persönliche Daten",
        "contact":        "Kontakt",
        "languages":      "Sprachkenntnisse",
        "skills":         "Fähigkeiten",
        "competencies":   "Kompetenzen",
        "profile":        "Profil",
        "education":      "Ausbildung",
        "work_experience":"Berufserfahrung",
        "date_of_birth":  "Geburtsdatum",
        "nationality":    "Nationalität",
        "civil_status":   "Zivilstand",
        "residence":      "Aufenthalt",
        "permit":         "Bewilligung ",
        "photo":          "Foto",
        "native":         "Muttersprache",
    },
    "en": {
        "personal_data":  "Personal Details",
        "contact":        "Contact",
        "languages":      "Languages",
        "skills":         "Skills",
        "competencies":   "Competencies",
        "profile":        "Profile",
        "education":      "Education",
        "work_experience":"Work Experience",
        "date_of_birth":  "Date of Birth",
        "nationality":    "Nationality",
        "civil_status":   "Civil Status",
        "residence":      "Residence",
        "permit":         "Permit ",
        "photo":          "Photo",
        "native":         "Native",
    },
}

# ── Layout constants ────────────────────────────────────────────────────
PW, PH   = A4
SB_W     = 6.5 * cm
SB_PAD   = 0.45 * cm
MAIN_X   = SB_W + 0.6*cm
MAIN_W   = PW - MAIN_X - 0.5*cm
HEAD_H   = 3.4 * cm


# ── Helpers ─────────────────────────────────────────────────────────────
def para(c_obj, text, x, y, width, font="Helvetica", size=8, color=C_GRAY,
         leading_mult=1.4, align=TA_LEFT, max_h=None):
    style = ParagraphStyle("p", fontName=font, fontSize=size,
                           leading=size*leading_mult, textColor=color,
                           alignment=align)
    p = Paragraph(text.replace("\n", "<br/>"), style)
    _, ph = p.wrapOn(c_obj, width, 9999)
    if max_h and ph > max_h:
        return y
    p.drawOn(c_obj, x, y - ph)
    return y - ph


def section_bar(c_obj, x, y, width, title, text_color=C_WHITE, bar_color=C_MID):
    bh = 0.55 * cm
    c_obj.setFillColor(bar_color)
    c_obj.roundRect(x, y - bh, width, bh, 2*mm, fill=1, stroke=0)
    c_obj.setFillColor(text_color)
    c_obj.setFont("Helvetica-Bold", 7.5)
    c_obj.drawString(x + 0.2*cm, y - bh + 0.14*cm, title.upper())
    return y - bh - 0.3*cm


def bullet_item(c_obj, x, y, width, text, size=7.5, color=C_GRAY):
    dot_x = x + 0.15*cm
    text_x = x + 0.38*cm
    text_w = width - 0.42*cm
    style = ParagraphStyle("b", fontName="Helvetica", fontSize=size,
                           leading=size*1.45, textColor=color)
    p = Paragraph(text, style)
    _, ph = p.wrapOn(c_obj, text_w, 9999)
    c_obj.setFillColor(C_ACCENT)
    c_obj.circle(dot_x, y - size * 0.72, 0.06*cm, fill=1, stroke=0)
    p.drawOn(c_obj, text_x, y - ph)
    return y - ph - 0.15*cm


def draw_photo(c_obj, x, y, size, foto_path):
    r = size / 2
    cx_p, cy_p = x + r, y - r
    if os.path.exists(foto_path):
        p = c_obj.beginPath()
        p.circle(cx_p, cy_p, r)
        c_obj.clipPath(p, stroke=0, fill=0)
        c_obj.drawImage(foto_path, x, y - size, width=size, height=size,
                        preserveAspectRatio=True, mask="auto")
        c_obj.restoreState()
    else:
        c_obj.setFillColor(colors.HexColor("#8aa8c8"))
        c_obj.circle(cx_p, cy_p, r, fill=1, stroke=0)
        c_obj.setFillColor(C_WHITE)
        c_obj.setFont("Helvetica", 7)
        c_obj.drawCentredString(cx_p, cy_p - 3, "Photo")
    c_obj.setStrokeColor(C_WHITE)
    c_obj.setLineWidth(2.5)
    c_obj.circle(cx_p, cy_p, r, fill=0, stroke=1)


# ── Main draw function ──────────────────────────────────────────────────
def draw_cv(output_path, profile, job=None):
    c = canvas.Canvas(output_path, pagesize=A4)
    c.saveState()

    J = job or {}
    lang = J.get("lang", "de")
    L = LABELS[lang]

    # ── HEADER ──────────────────────────────────────────────────────────
    c.setFillColor(C_DARK)
    c.rect(0, PH - HEAD_H, PW, HEAD_H, fill=1, stroke=0)

    c.setFillColor(C_ACCENT)
    c.rect(SB_W, PH - HEAD_H, 0.18*cm, HEAD_H, fill=1, stroke=0)

    c.setFillColor(C_WHITE)
    c.setFont("Helvetica-Bold", 21)
    c.drawString(MAIN_X, PH - 1.45*cm, profile["name_line1"])
    c.setFont("Helvetica", 16)
    c.drawString(MAIN_X, PH - 2.35*cm, profile["name_line2"])

    # ── SIDEBAR BACKGROUND ───────────────────────────────────────────────
    c.setFillColor(C_LIGHT)
    c.rect(0, 0, SB_W, PH - HEAD_H, fill=1, stroke=0)

    FOOTER_H = 0.72*cm

    # ── PHOTO ────────────────────────────────────────────────────────────
    foto_size = 2.8 * cm
    foto_x = (SB_W - foto_size) / 2
    foto_y = PH - HEAD_H - 0.35*cm
    c.saveState()
    draw_photo(c, foto_x, foto_y, foto_size, FOTO_PATH)
    c.restoreState()

    # ── SIDEBAR CONTENT ──────────────────────────────────────────────────
    sy = PH - HEAD_H - foto_size - 0.5*cm
    sw = SB_W - 2 * SB_PAD
    FS = 8.0

    faehigkeiten = J.get("faehigkeiten", profile["faehigkeiten_base"])
    kompetenzen  = J.get("kompetenzen",  profile["kompetenzen_base"])

    # Personal Data
    sy = section_bar(c, SB_PAD, sy, sw, L["personal_data"])
    def sb_row(label, value, y):
        c.setFillColor(C_LGRAY); c.setFont("Helvetica", FS)
        c.drawString(SB_PAD, y, label + ":")
        c.setFillColor(C_GRAY);  c.setFont("Helvetica", FS)
        c.drawString(SB_PAD + 2.5*cm, y, value)
        return y - 0.38*cm
    sy = sb_row(L["date_of_birth"], profile["geburtsdatum"] + "  |  " + profile["alter"], sy)
    sy = sb_row(L["nationality"],   profile.get("nationalitaet", ""), sy)
    sy = sb_row(L["civil_status"],  profile.get("zivilstand", ""), sy)
    sy = sb_row(L["residence"],     L["permit"] + profile["aufenthalt"], sy)
    sy -= 0.28*cm

    # Contact
    sy = section_bar(c, SB_PAD, sy, sw, L["contact"])
    for line in [profile["telefon"], profile["email"], profile["adresse"]]:
        sy = para(c, line, SB_PAD, sy, sw, size=FS, color=C_GRAY, leading_mult=1.3)
        sy -= 0.1*cm
    sy -= 0.3*cm

    # Languages — reorder so document language appears first
    LANG_FIRST = {"en": ["english", "englisch"], "de": ["deutsch", "german"]}
    first_keys = LANG_FIRST.get(lang, [])
    sprachen = sorted(profile["sprachen"],
                      key=lambda x: 0 if x[0].lower() in first_keys else 1)

    # Languages
    sy = section_bar(c, SB_PAD, sy, sw, L["languages"])
    bar_full = sw - 0.1*cm
    LEVELS = {"A1":0.17,"A2":0.33,"B1":0.5,"B2":0.67,"C1":0.83,"C2":1.0,"Muttersprache":1.0,"Native":1.0}
    for lang_name, level in sprachen:
        pct = LEVELS.get(level, 0.5)
        display_level = L["native"] if level in ("Muttersprache", "Native") else level
        c.setFillColor(C_GRAY);  c.setFont("Helvetica", FS)
        c.drawString(SB_PAD, sy, lang_name)
        c.setFillColor(C_LGRAY); c.setFont("Helvetica-Oblique", FS - 0.5)
        c.drawRightString(SB_PAD + bar_full, sy, display_level)
        sy -= 0.25*cm
        c.setFillColor(colors.HexColor("#ccd8e8"))
        c.roundRect(SB_PAD, sy - 0.12*cm, bar_full, 0.18*cm, 1*mm, fill=1, stroke=0)
        c.setFillColor(C_ACCENT)
        c.roundRect(SB_PAD, sy - 0.12*cm, bar_full*pct, 0.18*cm, 1*mm, fill=1, stroke=0)
        sy -= 0.38*cm
    sy -= 0.25*cm

    SB_BOTTOM = FOOTER_H + 0.5*cm

    # Skills
    if sy > SB_BOTTOM:
        sy = section_bar(c, SB_PAD, sy, sw, L["skills"])
    for f in faehigkeiten[:8]:
        if sy > SB_BOTTOM:
            sy = bullet_item(c, SB_PAD, sy, sw, f, size=FS)
    sy -= 0.28*cm

    # Competencies
    if sy > SB_BOTTOM:
        sy = section_bar(c, SB_PAD, sy, sw, L["competencies"])
    for k in kompetenzen[:8]:
        if sy > SB_BOTTOM:
            sy = bullet_item(c, SB_PAD, sy, sw, k, size=FS)

    # Footer strip
    c.setFillColor(C_DARK)
    c.rect(0, 0, SB_W, FOOTER_H, fill=1, stroke=0)
    c.setFillColor(C_ACCENT)
    c.rect(0, FOOTER_H, SB_W, 0.12*cm, fill=1, stroke=0)

    # ── MAIN CONTENT ─────────────────────────────────────────────────────
    FOOTER_H   = 0.72 * cm
    main_bottom = FOOTER_H + 0.3 * cm
    HDR2_H     = 1.0 * cm

    def draw_main_footer():
        c.setFillColor(C_DARK)
        c.rect(SB_W, 0, PW - SB_W, FOOTER_H, fill=1, stroke=0)
        c.setFillColor(C_ACCENT)
        c.rect(SB_W, FOOTER_H, PW - SB_W, 0.12*cm, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#8aa8c8"))
        c.setFont("Helvetica", 7.5)
        c.drawRightString(PW - 0.5*cm, 0.22*cm,
                          profile["email"] + "  |  " + profile["telefon"])

    def new_page():
        draw_main_footer()
        c.showPage()
        c.setFillColor(C_DARK)
        c.rect(0, PH - HDR2_H, PW, HDR2_H, fill=1, stroke=0)
        c.setFillColor(C_ACCENT)
        c.rect(SB_W, PH - HDR2_H, 0.18*cm, HDR2_H, fill=1, stroke=0)
        c.setFillColor(C_WHITE)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(MAIN_X, PH - 0.62*cm,
                     profile["name_line1"] + " " + profile["name_line2"])
        draw_main_footer()
        return PH - HDR2_H - 0.5*cm

    def check_space(y, need):
        if y - need < main_bottom:
            return new_page()
        return y

    def main_section(title, y, min_need=1.5*cm):
        y = check_space(y, min_need)
        c.setFillColor(C_DARK)
        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(MAIN_X, y, title.upper())
        y -= 0.24*cm
        c.setStrokeColor(C_ACCENT)
        c.setLineWidth(1.5)
        c.line(MAIN_X, y, PW - 0.5*cm, y)
        return y - 0.35*cm

    my = PH - HEAD_H - 0.45*cm

    erfahrungen = J.get("erfahrungen", profile["erfahrungen"])
    profil_text = J.get("profil", profile.get("profil_base", ""))

    # Profile
    my = main_section(L["profile"], my)
    my = para(c, profil_text, MAIN_X, my, MAIN_W, size=9, color=C_GRAY,
              leading_mult=1.55, align=TA_JUSTIFY)
    my -= 0.55*cm

    # Education (optional)
    ausbildung = J.get("ausbildung", [])
    if ausbildung:
        my = main_section(L["education"], my)
        for i, edu in enumerate(ausbildung):
            my = check_space(my, 2.5*cm)
            c.setFillColor(C_DARK)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(MAIN_X, my, edu["titel"])
            my -= 0.37*cm
            c.setFillColor(C_ACCENT)
            c.setFont("Helvetica-Oblique", 8.5)
            c.drawString(MAIN_X, my, edu["institution"])
            c.setFillColor(C_LGRAY)
            c.setFont("Helvetica", 8.2)
            c.drawRightString(PW - 0.5*cm, my, edu.get("zeitraum", ""))
            my -= 0.3*cm
            c.setStrokeColor(colors.HexColor("#dde6f0"))
            c.setLineWidth(0.6)
            c.line(MAIN_X, my, PW - 0.5*cm, my)
            my -= 0.3*cm
            if edu.get("beschreibung"):
                my = para(c, edu["beschreibung"], MAIN_X, my, MAIN_W,
                          size=8.8, color=C_GRAY, leading_mult=1.5, align=TA_JUSTIFY)
                my -= 0.15*cm
            if i < len(ausbildung) - 1:
                my -= 0.35*cm
        my -= 0.45*cm

    # Work Experience
    my = main_section(L["work_experience"], my)

    for i, job_exp in enumerate(erfahrungen):
        is_last = (i == len(erfahrungen) - 1)
        if not is_last and my - main_bottom < 5.0*cm:
            my = new_page()

        c.setFillColor(C_DARK)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(MAIN_X, my, job_exp["titel"])
        my -= 0.37*cm

        c.setFillColor(C_ACCENT)
        c.setFont("Helvetica-Oblique", 8.5)
        c.drawString(MAIN_X, my, job_exp["firma"])
        c.setFillColor(C_LGRAY)
        c.setFont("Helvetica", 8.2)
        c.drawRightString(PW - 0.5*cm, my, job_exp["zeitraum"])
        my -= 0.3*cm

        c.setStrokeColor(colors.HexColor("#dde6f0"))
        c.setLineWidth(0.6)
        c.line(MAIN_X, my, PW - 0.5*cm, my)
        my -= 0.3*cm

        my = para(c, job_exp["beschreibung"], MAIN_X, my, MAIN_W,
                  size=8.8, color=C_GRAY, leading_mult=1.5, align=TA_JUSTIFY)
        my -= 0.15*cm

        aufgaben = job_exp.get("aufgaben", job_exp.get("aufgaben_base", []))
        for task in aufgaben:
            my = bullet_item(c, MAIN_X, my, MAIN_W, task, size=8.8)

        if not is_last:
            my -= 0.5*cm

    draw_main_footer()
    c.save()
    print(f"CV saved → {output_path}")


# ── Entry point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else OUTPUT
    with open(PROFILE, encoding="utf-8") as f:
        profile = json.load(f)
    job = None
    if len(sys.argv) > 2:
        with open(sys.argv[2], encoding="utf-8") as f:
            job = json.load(f)
    draw_cv(out, profile, job)
