"""
Cover Letter Generator – Sebastian Motzo Fernandez
Usage:
  python3 generate_cover_letter.py output.pdf job_data.json
"""
import sys, json, os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
PROFILE   = os.path.join(BASE_DIR, "profile_base.json")
FOTO_PATH = os.path.join(BASE_DIR, "foto.jpg")
_ALT_FOTO = "/sessions/happy-wizardly-tesla/mnt/Bot aplicaciones trabajo/foto_sebastian.png"
if not os.path.exists(FOTO_PATH) and os.path.exists(_ALT_FOTO):
    try:
        from PIL import Image as _Img
        _img = _Img.open(_ALT_FOTO)
        _img = _img.resize((400, 400), _Img.LANCZOS)
        if _img.mode == "RGBA":
            _bg = _Img.new("RGB", _img.size, (255, 255, 255))
            _bg.paste(_img, mask=_img.split()[3])
            _img = _bg
        _img.save(FOTO_PATH, "JPEG", quality=88, optimize=True)
    except Exception:
        FOTO_PATH = _ALT_FOTO
OUTPUT = os.path.join(BASE_DIR, "Bewerbungsschreiben_Sebastian_Motzo.pdf")

C_DARK   = colors.HexColor("#1a2e4a")
C_MID    = colors.HexColor("#2c4a6e")
C_ACCENT = colors.HexColor("#7a9ec0")
C_LIGHT  = colors.HexColor("#eef2f7")
C_WHITE  = colors.white
C_GRAY   = colors.HexColor("#3d3d3d")
C_LGRAY  = colors.HexColor("#666666")

PW, PH   = A4
SB_W     = 5.8 * cm
SB_PAD   = 0.45 * cm
MAIN_X   = SB_W + 0.7 * cm
MAIN_W   = PW - MAIN_X - 0.8 * cm
HEAD_H   = 3.2 * cm

LABELS = {
    "de": {
        "applying_as":   "Bewerbung als",
        "company":       "Unternehmen",
        "requirements":  "Ihre Anforderungen",
        "contact":       "Kontakt",
        "app_at":        "Bewerbung bei",
        "subject_prefix":"Bewerbung als",
        "greeting_m":    "Sehr geehrter Herr",
        "greeting_f":    "Sehr geehrte Frau",
        "greeting_gen":  "Sehr geehrte Damen und Herren",
        "closing":       "Mit freundlichen Grüssen,",
        "months": ["Januar","Februar","März","April","Mai","Juni",
                   "Juli","August","September","Oktober","November","Dezember"],
    },
    "en": {
        "applying_as":   "Applying for",
        "company":       "Company",
        "requirements":  "Your Requirements",
        "contact":       "Contact",
        "app_at":        "Application at",
        "subject_prefix":"Application for",
        "greeting_m":    "Dear Mr.",
        "greeting_f":    "Dear Ms.",
        "greeting_gen":  "Dear Hiring Team",
        "closing":       "Kind regards,",
        "months": ["January","February","March","April","May","June",
                   "July","August","September","October","November","December"],
    },
}


def para(c_obj, text, x, y, width, font="Helvetica", size=9.5, color=C_GRAY,
         leading_mult=1.55, align=TA_JUSTIFY):
    style = ParagraphStyle("p", fontName=font, fontSize=size,
                           leading=size*leading_mult, textColor=color, alignment=align)
    p = Paragraph(text.replace("\n", "<br/>"), style)
    _, ph = p.wrapOn(c_obj, width, 9999)
    p.drawOn(c_obj, x, y - ph)
    return y - ph


def section_bar(c_obj, x, y, width, title):
    bh = 0.5 * cm
    c_obj.setFillColor(C_MID)
    c_obj.roundRect(x, y - bh, width, bh, 2*mm, fill=1, stroke=0)
    c_obj.setFillColor(C_WHITE)
    c_obj.setFont("Helvetica-Bold", 7.5)
    c_obj.drawString(x + 0.2*cm, y - bh + 0.13*cm, title.upper())
    return y - bh - 0.3*cm


def draw_photo_small(c_obj, cx, cy, r, foto_path):
    c_obj.saveState()
    if os.path.exists(foto_path):
        p = c_obj.beginPath()
        p.circle(cx, cy, r)
        c_obj.clipPath(p, stroke=0, fill=0)
        c_obj.drawImage(foto_path, cx - r, cy - r, width=r*2, height=r*2,
                        preserveAspectRatio=True, mask="auto")
    else:
        c_obj.setFillColor(colors.HexColor("#8aa8c8"))
        c_obj.circle(cx, cy, r, fill=1, stroke=0)
    c_obj.restoreState()
    c_obj.setStrokeColor(C_WHITE)
    c_obj.setLineWidth(2)
    c_obj.circle(cx, cy, r, fill=0, stroke=1)


def draw_letter(output_path, profile, job=None):
    c = canvas.Canvas(output_path, pagesize=A4)
    J = job or {}
    lang = J.get("lang", "de")
    L = LABELS[lang]

    position       = J.get("position_title", "")
    position_short = J.get("position_short", position)
    company        = J.get("company_name", "")
    contact        = J.get("contact_person", "")
    keywords       = J.get("keywords", [])

    # Build greeting
    if contact:
        anrede = f"{contact},"
    else:
        anrede = L["greeting_gen"] + ","

    # ── HEADER ──────────────────────────────────────────────────────────
    c.setFillColor(C_DARK)
    c.rect(0, PH - HEAD_H, PW, HEAD_H, fill=1, stroke=0)

    photo_cx = SB_W / 2
    photo_cy = PH - HEAD_H / 2
    draw_photo_small(c, photo_cx, photo_cy, 1.15*cm, FOTO_PATH)

    c.setFillColor(C_WHITE)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(MAIN_X, PH - 1.35*cm, profile["name_line1"])
    c.setFont("Helvetica", 13)
    c.drawString(MAIN_X, PH - 2.15*cm, profile["name_line2"])
    if company:
        c.setFont("Helvetica-Oblique", 8.5)
        c.setFillColor(colors.HexColor("#a8c4e0"))
        c.drawString(MAIN_X, PH - 2.8*cm, f"{L['app_at']} {company}")

    c.setFillColor(C_ACCENT)
    c.rect(SB_W, PH - HEAD_H, 0.18*cm, HEAD_H, fill=1, stroke=0)

    # ── SIDEBAR ──────────────────────────────────────────────────────────
    c.setFillColor(C_LIGHT)
    c.rect(0, 0, SB_W, PH - HEAD_H, fill=1, stroke=0)

    sw = SB_W - 2 * SB_PAD
    sy = PH - HEAD_H - 0.5*cm

    def sb_text(text, y, bold=False, size=8.5):
        style_t = ParagraphStyle("st", fontName="Helvetica-Bold" if bold else "Helvetica",
                                 fontSize=size, leading=size*1.35, textColor=C_GRAY)
        p = Paragraph(text, style_t)
        _, ph = p.wrapOn(c, sw, 999)
        p.drawOn(c, SB_PAD, y - ph)
        return y - ph

    sy = section_bar(c, SB_PAD, sy, sw, L["applying_as"])
    style_pos = ParagraphStyle("pos", fontName="Helvetica-Bold", fontSize=10,
                               leading=13, textColor=C_DARK)
    p = Paragraph(position_short, style_pos)
    _, ph = p.wrapOn(c, sw, 999)
    p.drawOn(c, SB_PAD, sy - ph)
    sy -= ph + 0.45*cm

    if company:
        sy = section_bar(c, SB_PAD, sy, sw, L["company"])
        sy = sb_text(company, sy, bold=True, size=9)
        sy -= 0.45*cm

    if keywords:
        sy = section_bar(c, SB_PAD, sy, sw, L["requirements"])
        for kw in keywords:
            c.setFillColor(C_ACCENT)
            c.circle(SB_PAD + 0.12*cm, sy - 0.26*cm, 0.055*cm, fill=1, stroke=0)
            style_kw = ParagraphStyle("kw", fontName="Helvetica", fontSize=8,
                                      leading=10.5, textColor=C_GRAY)
            p = Paragraph(kw, style_kw)
            _, ph = p.wrapOn(c, sw - 0.3*cm, 999)
            p.drawOn(c, SB_PAD + 0.3*cm, sy - ph)
            sy -= ph + 0.08*cm
        sy -= 0.35*cm

    sy = section_bar(c, SB_PAD, sy, sw, L["contact"])
    for line in [profile["telefon"], profile["email"], profile["adresse"]]:
        style_c = ParagraphStyle("ct", fontName="Helvetica", fontSize=7.8,
                                 leading=11, textColor=C_GRAY)
        p = Paragraph(line, style_c)
        _, ph = p.wrapOn(c, sw, 999)
        p.drawOn(c, SB_PAD, sy - ph)
        sy -= ph + 0.1*cm

    c.setFillColor(C_DARK)
    c.rect(0, 0, SB_W, 0.72*cm, fill=1, stroke=0)
    c.setFillColor(C_ACCENT)
    c.rect(0, 0.72*cm, SB_W, 0.12*cm, fill=1, stroke=0)

    # ── MAIN LETTER BODY ─────────────────────────────────────────────────
    my = PH - HEAD_H - 0.7*cm

    # Date
    today = datetime.today()
    month_name = L["months"][today.month - 1]
    if lang == "de":
        date_str = f"{today.day}. {month_name} {today.year}"
    else:
        date_str = f"{month_name} {today.day}, {today.year}"

    c.setFillColor(C_LGRAY)
    c.setFont("Helvetica", 8.5)
    c.drawRightString(PW - 0.8*cm, my, date_str)
    my -= 0.5*cm

    # Subject
    subject = f"{L['subject_prefix']} {position_short}"
    if company:
        subject += f" – {company}"
    subj_style = ParagraphStyle("subj", fontName="Helvetica-Bold", fontSize=10.5,
                                leading=13.5, textColor=C_DARK, alignment=TA_LEFT)
    subj_p = Paragraph(subject, subj_style)
    _, subj_h = subj_p.wrapOn(c, MAIN_W, 9999)
    subj_p.drawOn(c, MAIN_X, my - subj_h)
    my -= subj_h + 0.15*cm
    c.setStrokeColor(C_ACCENT)
    c.setLineWidth(1)
    c.line(MAIN_X, my, PW - 0.8*cm, my)
    my -= 0.45*cm

    # Greeting
    my = para(c, anrede, MAIN_X, my, MAIN_W,
              font="Helvetica-Bold", size=9.5, color=C_DARK,
              leading_mult=1.4, align=TA_LEFT)
    my -= 0.3*cm

    # Paragraphs
    paragraphen = J.get("paragraphen", [])
    for p_text in paragraphen:
        my = para(c, p_text, MAIN_X, my, MAIN_W, size=9.5, color=C_GRAY,
                  leading_mult=1.55, align=TA_JUSTIFY)
        my -= 0.35*cm

    my -= 0.2*cm
    my = para(c, L["closing"], MAIN_X, my, MAIN_W,
              size=9.5, color=C_GRAY, leading_mult=1.4, align=TA_LEFT)
    my -= 0.8*cm

    c.setFillColor(C_DARK)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(MAIN_X, my, profile["name_line1"] + " " + profile["name_line2"])

    c.save()
    print(f"Cover letter saved → {output_path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else OUTPUT
    with open(PROFILE, encoding="utf-8") as f:
        profile = json.load(f)
    job = None
    if len(sys.argv) > 2:
        with open(sys.argv[2], encoding="utf-8") as f:
            job = json.load(f)
    draw_letter(out, profile, job)
