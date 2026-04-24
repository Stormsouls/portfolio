# Job Application Bot

A Python-based automation system that generates tailored CVs and cover letters in PDF format for job applications.

## What it does

For each job offer, the system produces:
- A **visual CV** (two-column layout with photo, auto-paginated)
- An **ATS-safe CV** (single-column, no graphics, for large company portals)
- A **cover letter** (matching design, sidebar with keywords)

All documents adapt automatically to the language of the job offer (German or English), including section headers, date formatting, greeting, and closing.

## How it works

1. A `job_data.json` file is prepared for each offer — containing the adapted profile text, selected experiences, keywords, and cover letter paragraphs
2. The scripts read this file and render the PDFs using [ReportLab](https://www.reportlab.com/)
3. The photo is automatically compressed (1800px PNG → 400px JPEG) so output files stay under LinkedIn's 2MB upload limit

The content in `job_data.json` is generated with the help of Claude AI, which selects the most relevant experiences from a base profile, matches the language of the offer, and writes the cover letter paragraphs.

## Stack

- Python 3.10+
- [ReportLab](https://pypi.org/project/reportlab/) — PDF rendering
- [Pillow](https://pypi.org/project/Pillow/) — image compression
- [Claude AI](https://www.anthropic.com/) — content generation and adaptation

## File structure

```
├── generate_cv.py            # Visual two-column CV generator
├── generate_cv_ats.py        # ATS-safe single-column CV generator
├── generate_cover_letter.py  # Cover letter generator
├── profile_base.json         # Base profile (not included — contains personal data)
├── job_data_example.json     # Example job data structure
└── index.html                # Portfolio page (GitHub Pages)
```

## Usage

```bash
python3 generate_cv.py output/CV_Company.pdf job_data_company.json
python3 generate_cv_ats.py output/CV_ATS_Company.pdf job_data_company.json
python3 generate_cover_letter.py output/Cover_Letter_Company.pdf job_data_company.json
```

## Language support

Set `"lang": "de"` or `"lang": "en"` in your `job_data.json`. The scripts will:
- Translate all section headers (Profile, Work Experience, Education, Skills, etc.)
- Reorder languages so the document language appears first
- Format dates and greetings accordingly

## Notes

`profile_base.json` is not included in this repository as it contains personal contact information. See `job_data_example.json` for the expected structure of the job-specific input file.
