"""
CV Generator ATS – Sebastian Motzo Fernandez
Single-column, no graphics, no sidebar — ATS-safe format.

Usage:
  python3 generate_cv_ats.py output.pdf job_data.json
"""
import sys, json, os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE  = os.path.join(BASE_DIR, "profile_base.json")
OUTPUT   = os.path.join(BASE_DIR, "CV_ATS_Sebastian_Motzo.pdf")

PW, PH = A4
ML = 2.0 * cm
MR = 2.0 * cm
MT = 2.0 * cm
MB = 1.8 * cm
TW = PW - ML - MR

C_BLACK  = colors.HexColor("#111111")
C_DARK   = colors.HexColor("#1a2e4a")
C_GRAY   = colors.HexColor("#3d3d3d")
C_LGRAY  = colors.HexColor("#666666")
C_RULE   = colors.HexColor("#aaaaaa")

LABELS = {
    "de": {
        "profile":        "Profil",
        "personal_data":  "Persönliche Daten",
        "languages":      "Sprachkenntnisse",
        "work_experience":"Berufserfahrung",
        "education":      "Ausbildung",
        "skills":         "Fähigkeiten",
        "competencies":   "Kompetenzen",
        "date_of_birth":  "Geburtsdatum",
        "nationality":    "Nationalität",
        "civil_status":   "Zivilstand",
        "residence":      "Aufenthaltsbewilligung",
        "permit":         "Bewilligung ",
        "native":         "Muttersprache",
    },
    "en": {
        "profile":        "Profile",
        "personal_data":  "Personal Details",
        "languages":      "Languages",
        "work_experience":"Work Experience",
        "education":      "Education",
        "skills":         "Skills",
        "competencies":   "Competencies",
        "date_of_birth":  "Date of Birth",
        "nationality":    "Nationality",
        "civil_status":   "Civil Status",
        "residence":      "Residence Permit",
        "permit":         "Permit ",
        "native":         "Native",
    },
}


def make_para(text, font="Helvetica", size=9.5, color=C_GRAY,
              leading=14, align=TA_LEFT):
    style = ParagraphStyle("p", fontName=font, fontSize=size,
                           leading=leading, textColor=color, alignment=align)
    return Paragraph(text.replace("\n", "<br/>"), style)


class ATSWriter:
    def __init__(self, output_path):
        self.c = canvas.Canvas(output_path, pagesize=A4)
        self.y = PH - MT

    def _check_space(self, need):
        if self.y - need < MB:
            self.c.showPage()
            self.y = PH - MT

    def text(self, text, font="Helvetica", size=9.5, color=C_GRAY,
             leading=14, align=TA_LEFT, indent=0):
        p = make_para(text, font, size, color, leading, align)
        w = TW - indent
        _, ph = p.wrapOn(self.c, w, 9999)
        self._check_space(ph)
        p.drawOn(self.c, ML + indent, self.y - ph)
        self.y -= ph

    def vspace(self, h):
        self.y -= h

    def rule(self, thickness=0.5, color=C_RULE):
        self._check_space(0.3 * cm)
        self.c.setStrokeColor(color)
        self.c.setLineWidth(thickness)
        self.c.line(ML, self.y, PW - MR, self.y)

    def section(self, title):
        self.vspace(0.4 * cm)
        self._check_space(0.9 * cm)
        self.c.setFillColor(C_DARK)
        self.c.setFont("Helvetica-Bold", 10.5)
        self.c.drawString(ML, self.y, title.upper())
        self.y -= 0.22 * cm
        self.rule(thickness=1.0, color=C_DARK)
        self.y -= 0.3 * cm

    def bullet(self, text, indent=0.4 * cm, size=9.5):
        p = make_para(text, size=size, color=C_GRAY, leading=13.5)
        w = TW - indent - 0.25 * cm
        _, ph = p.wrapOn(self.c, w, 9999)
        self._check_space(ph)
        self.c.setFillColor(C_DARK)
        self.c.circle(ML + indent - 0.1 * cm, self.y - size * 0.72,
                      0.055 * cm, fill=1, stroke=0)
        p.drawOn(self.c, ML + indent + 0.15 * cm, self.y - ph)
        self.y -= ph + 0.1 * cm

    def save(self, output_path):
        self.c.save()
        print(f"CV (ATS) saved → {output_path}")


def draw_cv_ats(output_path, profile, job=None):
    J   = job or {}
    lang = J.get("lang", "de")
    L   = LABELS[lang]
    w   = ATSWriter(output_path)
    c   = w.c

    erfahrungen  = J.get("erfahrungen",  profile["erfahrungen"])
    profil_text  = J.get("profil",       profile.get("profil_base", ""))
    faehigkeiten = J.get("faehigkeiten", profile["faehigkeiten_base"])
    kompetenzen  = J.get("kompetenzen",  profile["kompetenzen_base"])
    ausbildung   = J.get("ausbildung",   [])

    # ── NAME ─────────────────────────────────────────────────────────────
    c.setFillColor(C_DARK)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(ML, w.y, profile["name_line1"] + " " + profile["name_line2"])
    w.y -= 0.75 * cm

    # ── CONTACT LINE ─────────────────────────────────────────────────────
    contact_parts = [
        profile["adresse"],
        profile["telefon"],
        profile["email"],
        L["residence"] + ": " + L["permit"] + profile["aufenthalt"],
        profile.get("nationalitaet", ""),
    ]
    w.text("  |  ".join(p for p in contact_parts if p),
           font="Helvetica", size=8.8, color=C_LGRAY, leading=12)
    w.vspace(0.15 * cm)
    w.rule(thickness=1.5, color=C_DARK)
    w.vspace(0.25 * cm)

    # ── PROFILE ──────────────────────────────────────────────────────────
    if profil_text:
        w.section(L["profile"])
        w.text(profil_text, size=9.5, color=C_GRAY, leading=14.5, align=TA_JUSTIFY)
        w.vspace(0.1 * cm)

    # ── PERSONAL DETAILS ─────────────────────────────────────────────────
    w.section(L["personal_data"])
    personal = [
        f"{L['date_of_birth']}: {profile['geburtsdatum']} ({profile['alter']})",
        f"{L['nationality']}: {profile.get('nationalitaet', '')}",
        f"{L['civil_status']}: {profile.get('zivilstand', '')}",
        f"{L['residence']}: {L['permit']}{profile['aufenthalt']}",
    ]
    w.text("  |  ".join(personal), size=9.2, color=C_GRAY, leading=14)

    # ── LANGUAGES ────────────────────────────────────────────────────────
    w.section(L["languages"])
    native_label = L["native"]
    LANG_FIRST = {"en": ["english", "englisch"], "de": ["deutsch", "german"]}
    first_keys = LANG_FIRST.get(lang, [])
    sprachen_sorted = sorted(profile["sprachen"],
                             key=lambda x: 0 if x[0].lower() in first_keys else 1)
    lang_parts = []
    for lang_name, level in sprachen_sorted:
        display = native_label if level in ("Muttersprache", "Native") else level
        lang_parts.append(f"{lang_name}: {display}")
    w.text("  |  ".join(lang_parts), size=9.2, color=C_GRAY)

    # ── WORK EXPERIENCE ──────────────────────────────────────────────────
    w.section(L["work_experience"])
    for i, exp in enumerate(erfahrungen):
        c.setFillColor(C_DARK)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(ML, w.y, exp["titel"])
        c.setFillColor(C_LGRAY)
        c.setFont("Helvetica", 9)
        c.drawRightString(PW - MR, w.y, exp["zeitraum"])
        w.y -= 0.36 * cm

        c.setFillColor(C_LGRAY)
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(ML, w.y, exp["firma"])
        w.y -= 0.35 * cm

        if exp.get("beschreibung"):
            w.text(exp["beschreibung"], size=9.2, color=C_GRAY,
                   leading=13.5, align=TA_JUSTIFY)
            w.vspace(0.05 * cm)

        for task in exp.get("aufgaben", exp.get("aufgaben_base", [])):
            w.bullet(task, size=9.2)

        if i < len(erfahrungen) - 1:
            w.vspace(0.4 * cm)

    # ── EDUCATION ────────────────────────────────────────────────────────
    if ausbildung:
        w.section(L["education"])
        for i, edu in enumerate(ausbildung):
            c.setFillColor(C_DARK)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(ML, w.y, edu["titel"])
            c.setFillColor(C_LGRAY)
            c.setFont("Helvetica", 9)
            c.drawRightString(PW - MR, w.y, edu.get("zeitraum", ""))
            w.y -= 0.36 * cm
            c.setFillColor(C_LGRAY)
            c.setFont("Helvetica-Oblique", 9)
            c.drawString(ML, w.y, edu["institution"])
            w.y -= 0.32 * cm
            if edu.get("beschreibung"):
                w.text(edu["beschreibung"], size=9.2, color=C_GRAY, leading=13.5)
            if i < len(ausbildung) - 1:
                w.vspace(0.3 * cm)

    # ── SKILLS ───────────────────────────────────────────────────────────
    w.section(L["skills"])
    for f in faehigkeiten:
        w.bullet(f, size=9.2)

    # ── COMPETENCIES ─────────────────────────────────────────────────────
    w.section(L["competencies"])
    w.text(" · ".join(kompetenzen), size=9.2, color=C_GRAY, leading=14)

    w.save(output_path)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else OUTPUT
    with open(PROFILE, encoding="utf-8") as f:
        profile = json.load(f)
    job = None
    if len(sys.argv) > 2:
        with open(sys.argv[2], encoding="utf-8") as f:
            job = json.load(f)
    draw_cv_ats(out, profile, job)
