import io
import re
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Colour palette ────────────────────────────────────────────────────────────
BLUE_DARK  = colors.HexColor('#1a365d')
BLUE_MED   = colors.HexColor('#2b6cb0')
BLUE_LIGHT = colors.HexColor('#ebf8ff')
GRAY_DARK  = colors.HexColor('#4a5568')
GRAY_LIGHT = colors.HexColor('#f7fafc')
GRAY_LINE  = colors.HexColor('#e2e8f0')
RED_WARN   = colors.HexColor('#fff5f5')
RED_BORDER = colors.HexColor('#fc8181')
GREEN_OK   = colors.HexColor('#f0fff4')


def _build_styles():
    base = getSampleStyleSheet()

    title = ParagraphStyle(
        'DentalTitle',
        parent=base['Title'],
        fontSize=20,
        textColor=colors.white,
        spaceAfter=2,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
    )
    subtitle = ParagraphStyle(
        'DentalSubtitle',
        parent=base['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#bee3f8'),
        alignment=TA_CENTER,
        spaceAfter=0,
    )
    section = ParagraphStyle(
        'DentalSection',
        parent=base['Heading2'],
        fontSize=11,
        textColor=BLUE_MED,
        spaceBefore=14,
        spaceAfter=4,
        fontName='Helvetica-Bold',
        borderPad=0,
    )
    body = ParagraphStyle(
        'DentalBody',
        parent=base['Normal'],
        fontSize=9,
        leading=14,
        spaceAfter=3,
        textColor=colors.HexColor('#2d3748'),
    )
    bullet = ParagraphStyle(
        'DentalBullet',
        parent=body,
        leftIndent=12,
        bulletIndent=0,
        spaceAfter=2,
    )
    disclaimer = ParagraphStyle(
        'Disclaimer',
        parent=base['Normal'],
        fontSize=8,
        leading=12,
        textColor=GRAY_DARK,
        backColor=BLUE_LIGHT,
        borderColor=BLUE_MED,
        borderWidth=1,
        borderPad=8,
        spaceAfter=6,
    )
    footer = ParagraphStyle(
        'Footer',
        parent=base['Normal'],
        fontSize=7,
        textColor=colors.gray,
        alignment=TA_CENTER,
    )
    return dict(title=title, subtitle=subtitle, section=section,
                body=body, bullet=bullet, disclaimer=disclaimer, footer=footer)


def _inline_markup(text: str) -> str:
    """Convert markdown bold/italic to ReportLab XML."""
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.*?)\*',     r'<i>\1</i>', text)
    # Colour confidence tags
    text = text.replace('[HIGH]',   '<font color="#276749"><b>[HIGH]</b></font>')
    text = text.replace('[MEDIUM]', '<font color="#975a16"><b>[MEDIUM]</b></font>')
    text = text.replace('[LOW]',    '<font color="#9b2c2c"><b>[LOW]</b></font>')
    return text


def generate_pdf_report(
    analysis_text: str,
    patient_name: str = '',
    patient_id: str = '',
    dentist_name: str = '',
    clinic_name: str = '',
    img_bytes: bytes = None,
) -> bytes:
    """Render a formatted PDF report and return it as bytes."""

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.8 * cm,
        leftMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
    )

    S = _build_styles()
    story = []

    # ── Header banner ─────────────────────────────────────────────────────────
    header_data = [[
        Paragraph('DENTAL OPG ANALYSIS REPORT', S['title']),
    ]]
    header_table = Table(header_data, colWidths=[doc.width])
    header_table.setStyle(TableStyle([
        ('BACKGROUND',  (0, 0), (-1, -1), BLUE_DARK),
        ('ROUNDEDCORNERS', [6]),
        ('TOPPADDING',  (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 14),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 10))

    # ── Patient / case info table ──────────────────────────────────────────────
    now = datetime.now()
    info_rows = [
        ['Patient Name', patient_name or '—',  'Report Date', now.strftime('%d %B %Y')],
        ['Patient ID',   patient_id or '—',    'Report Time', now.strftime('%H:%M')],
        ['Dentist',      dentist_name or '—',   'Clinic',      clinic_name or '—'],
    ]
    info_table = Table(info_rows, colWidths=[3.2*cm, 6.8*cm, 3*cm, 5.5*cm])
    info_table.setStyle(TableStyle([
        ('FONTNAME',    (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE',    (0, 0), (-1, -1), 8.5),
        ('FONTNAME',    (0, 0), (0, -1),  'Helvetica-Bold'),
        ('FONTNAME',    (2, 0), (2, -1),  'Helvetica-Bold'),
        ('TEXTCOLOR',   (0, 0), (0, -1),  GRAY_DARK),
        ('TEXTCOLOR',   (2, 0), (2, -1),  GRAY_DARK),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [GRAY_LIGHT, colors.white]),
        ('GRID',        (0, 0), (-1, -1), 0.5, GRAY_LINE),
        ('TOPPADDING',  (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 12))

    # ── Radiographic image ────────────────────────────────────────────────────
    if img_bytes:
        story.append(Paragraph('Radiographic Image', S['section']))
        story.append(HRFlowable(width='100%', thickness=1, color=GRAY_LINE))
        story.append(Spacer(1, 4))
        rl_img = RLImage(io.BytesIO(img_bytes), width=15*cm, height=7.5*cm, kind='proportional')
        # centre it
        img_table = Table([[rl_img]], colWidths=[doc.width])
        img_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(img_table)
        story.append(Spacer(1, 12))

    # ── Analysis findings ─────────────────────────────────────────────────────
    story.append(HRFlowable(width='100%', thickness=1.5, color=BLUE_MED))
    story.append(Spacer(1, 6))

    for raw_line in analysis_text.split('\n'):
        line = raw_line.rstrip()

        if not line:
            story.append(Spacer(1, 4))
            continue

        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if stripped.startswith('### '):
            text = _inline_markup(stripped[4:])
            story.append(Paragraph(text, S['section']))
            story.append(HRFlowable(width='100%', thickness=0.5, color=GRAY_LINE))

        elif stripped.startswith('## '):
            text = _inline_markup(stripped[3:])
            story.append(Spacer(1, 6))
            story.append(Paragraph(text, S['section']))
            story.append(HRFlowable(width='100%', thickness=1, color=BLUE_MED))

        elif stripped.startswith('# '):
            text = _inline_markup(stripped[2:])
            story.append(Paragraph(text, S['section']))

        elif stripped.startswith(('- ', '* ')):
            text = _inline_markup(stripped[2:])
            story.append(Paragraph(f'• {text}', S['bullet']))

        elif re.match(r'^\d+\.\s', stripped):
            text = _inline_markup(stripped)
            story.append(Paragraph(text, S['bullet']))

        else:
            text = _inline_markup(line)
            story.append(Paragraph(text, S['body']))

    story.append(Spacer(1, 16))

    # ── Disclaimer ────────────────────────────────────────────────────────────
    story.append(HRFlowable(width='100%', thickness=1, color=GRAY_LINE))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        '<b>⚕ Clinical Disclaimer:</b> This report was generated with AI assistance and is '
        'intended as a clinical decision-support tool only. All radiographic findings must be '
        'correlated with the patient\'s clinical presentation, medical history, and professional '
        'clinical examination. This report does not constitute a diagnosis and must be reviewed '
        'and validated by a qualified dental professional before any clinical decisions are made.',
        S['disclaimer'],
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f'Dental OPG AI Assistant  |  Generated {now.strftime("%Y-%m-%d %H:%M")}  |  '
        'Powered by Claude (Anthropic)',
        S['footer'],
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# PATIENT-FRIENDLY REPORT
# ─────────────────────────────────────────────────────────────────────────────

_URGENCY_LABEL = {
    "urgent":      ("Needs urgent treatment",   colors.HexColor('#dc2626')),
    "pathology":   ("Disease detected",          colors.HexColor('#ea580c')),
    "impacted":    ("Impacted tooth",            colors.HexColor('#7c3aed')),
    "restoration": ("Has existing dental work",  colors.HexColor('#1d4ed8')),
    "monitor":     ("Monitor at next visit",     colors.HexColor('#b45309')),
    "normal":      ("Appears healthy",           colors.HexColor('#15803d')),
    "default":     ("No specific finding",       colors.HexColor('#475569')),
}

_SIMPLE_NAMES: dict[str, str] = {
    "caries":        "Tooth decay / cavity",
    "periapical":    "Infection near the root",
    "periodontal":   "Gum or bone disease",
    "cyst":          "Cyst or lesion",
    "root":          "Root problem",
    "calcification": "Calcification",
    "restoration":   "Existing dental work",
    "impacted":      "Trapped / impacted tooth",
    "missing":       "Missing tooth",
    "general":       "Clinical finding",
}


def generate_patient_report(
    patient_name: str,
    patient_id: str,
    dentist_name: str,
    clinic_name: str,
    patient_rows: list[dict],      # from report_parser.build_patient_summary()
    recommendations: dict,         # from report_parser.extract_recommendations()
    img_bytes: bytes = None,
) -> bytes:
    """
    Generate a patient-friendly PDF — plain English, no clinical jargon.
    patient_rows: list of {tooth, name, urgency, simple_desc, detail, confidence}
    """
    # Styles
    GREEN_SOFT  = colors.HexColor('#f0fff4')
    AMBER_SOFT  = colors.HexColor('#fffbeb')
    RED_SOFT    = colors.HexColor('#fff5f5')
    TEAL        = colors.HexColor('#0d9488')

    base = getSampleStyleSheet()
    title_s = ParagraphStyle('PatTitle', parent=base['Title'],
                              fontSize=22, textColor=colors.white,
                              alignment=TA_CENTER, fontName='Helvetica-Bold',
                              spaceAfter=2)
    sub_s = ParagraphStyle('PatSub', parent=base['Normal'],
                            fontSize=10, textColor=colors.HexColor('#ccfbf1'),
                            alignment=TA_CENTER)
    h2_s = ParagraphStyle('PatH2', parent=base['Normal'],
                           fontSize=12, fontName='Helvetica-Bold',
                           textColor=TEAL, spaceBefore=14, spaceAfter=4)
    body_s = ParagraphStyle('PatBody', parent=base['Normal'],
                             fontSize=9.5, leading=15,
                             textColor=colors.HexColor('#1e293b'))
    small_s = ParagraphStyle('PatSmall', parent=base['Normal'],
                              fontSize=8, textColor=colors.HexColor('#475569'))
    disc_s = ParagraphStyle('PatDisc', parent=base['Normal'],
                             fontSize=8, leading=12,
                             textColor=colors.HexColor('#374151'),
                             backColor=colors.HexColor('#f1f5f9'),
                             borderColor=colors.HexColor('#94a3b8'),
                             borderWidth=1, borderPad=8)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                             rightMargin=1.8*cm, leftMargin=1.8*cm,
                             topMargin=1.8*cm,   bottomMargin=1.8*cm)
    story = []

    # Header
    hdr = Table([[Paragraph('Your Dental Health Report', title_s)],
                 [Paragraph('Prepared by your dental team', sub_s)]],
                colWidths=[doc.width])
    hdr.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), TEAL),
        ('ROUNDEDCORNERS', [8]),
        ('TOPPADDING',    (0,0), (-1,-1), 14),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 10))

    # Patient info
    now = datetime.now()
    info = [
        ['Patient', patient_name or '—',   'Date', now.strftime('%d %B %Y')],
        ['Patient ID', patient_id or '—',  'Dentist', dentist_name or '—'],
        ['Clinic', clinic_name or '—',     '', ''],
    ]
    it = Table(info, colWidths=[3*cm, 7*cm, 2.8*cm, 5.7*cm])
    it.setStyle(TableStyle([
        ('FONTNAME',  (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME',  (2,0), (2,-1), 'Helvetica-Bold'),
        ('FONTSIZE',  (0,0), (-1,-1), 8.5),
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [GRAY_LIGHT, colors.white]),
        ('GRID', (0,0), (-1,-1), 0.4, GRAY_LINE),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(it)
    story.append(Spacer(1, 12))

    # OPG image (optional)
    if img_bytes:
        story.append(Paragraph('Your X-ray', h2_s))
        story.append(HRFlowable(width='100%', thickness=0.5, color=GRAY_LINE))
        rl_img = RLImage(io.BytesIO(img_bytes), width=14*cm, height=7*cm, kind='proportional')
        it2 = Table([[rl_img]], colWidths=[doc.width])
        it2.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER')]))
        story.append(it2)
        story.append(Spacer(1, 10))

    # Findings summary
    story.append(Paragraph('What We Found', h2_s))
    story.append(HRFlowable(width='100%', thickness=0.5, color=GRAY_LINE))
    story.append(Spacer(1, 6))

    if not patient_rows:
        story.append(Paragraph(
            '✅  No significant findings were identified on this radiograph. '
            'Continue with regular dental check-ups.', body_s))
    else:
        # Count urgency levels
        urgent_count = sum(1 for r in patient_rows if r['urgency'] == 'urgent')
        patho_count  = sum(1 for r in patient_rows if r['urgency'] == 'pathology')

        if urgent_count:
            story.append(Paragraph(
                f'⚠️  <b>{urgent_count} tooth/teeth require urgent attention.</b> '
                'Please contact your dentist within 1–2 weeks.', body_s))
            story.append(Spacer(1, 4))
        if patho_count:
            story.append(Paragraph(
                f'🔶  <b>{patho_count} tooth/teeth show signs of disease.</b> '
                'Treatment is recommended soon.', body_s))
            story.append(Spacer(1, 8))

        # Tooth findings table
        tdata = [['Tooth', 'Location', 'Finding', 'Status']]
        for row in patient_rows:
            label, col = _URGENCY_LABEL.get(row['urgency'], _URGENCY_LABEL['default'])
            tdata.append([
                row['tooth'],
                Paragraph(row['name'], small_s),
                Paragraph(_SIMPLE_NAMES.get(row.get('category',''), 'Finding'), small_s),
                Paragraph(f'<font color="{col.hexval()}">{label}</font>', small_s),
            ])

        col_w = [1.4*cm, 5.5*cm, 4.5*cm, 5*cm]
        ft = Table(tdata, colWidths=col_w, repeatRows=1)
        ft.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,0), colors.HexColor('#0f172a')),
            ('TEXTCOLOR',     (0,0), (-1,0), colors.white),
            ('FONTNAME',      (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0,0), (-1,-1), 8.5),
            ('ROWBACKGROUNDS',(0,1), (-1,-1), [GRAY_LIGHT, colors.white]),
            ('GRID',          (0,0), (-1,-1), 0.4, GRAY_LINE),
            ('TOPPADDING',    (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING',   (0,0), (-1,-1), 6),
            ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ]))
        story.append(ft)

    story.append(Spacer(1, 14))

    # Recommendations
    p1 = recommendations.get('priority_1', [])
    p2 = recommendations.get('priority_2', [])
    p3 = recommendations.get('priority_3', [])

    if p1 or p2 or p3:
        story.append(Paragraph('What We Recommend', h2_s))
        story.append(HRFlowable(width='100%', thickness=0.5, color=GRAY_LINE))
        story.append(Spacer(1, 6))

    for items, bg, heading in [
        (p1, RED_SOFT,   '🔴  As Soon As Possible (within 1–2 weeks)'),
        (p2, AMBER_SOFT, '🟡  Schedule Soon (within 1–3 months)'),
        (p3, GREEN_SOFT, '🟢  Monitor at Next Check-up'),
    ]:
        if items:
            story.append(Paragraph(f'<b>{heading}</b>', body_s))
            for item in items:
                rd = [[Paragraph(f'• {item}', body_s)]]
                rt = Table(rd, colWidths=[doc.width])
                rt.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), bg),
                    ('ROUNDEDCORNERS', [4]),
                    ('TOPPADDING',    (0,0), (-1,-1), 4),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                    ('LEFTPADDING',   (0,0), (-1,-1), 10),
                    ('BOTTOMMARGIN',  (0,0), (-1,-1), 3),
                ]))
                story.append(rt)
                story.append(Spacer(1, 3))
            story.append(Spacer(1, 6))

    story.append(Spacer(1, 14))
    story.append(HRFlowable(width='100%', thickness=0.5, color=GRAY_LINE))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        'This report summarises the AI-assisted analysis of your dental radiograph. '
        'All findings have been reviewed by your dental professional. '
        'Please discuss any questions with your dentist at your next appointment.',
        disc_s,
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f'Dental OPG AI Assistant  |  Generated {now.strftime("%Y-%m-%d %H:%M")}',
        ParagraphStyle('PFoot', parent=base['Normal'], fontSize=7,
                       textColor=colors.gray, alignment=TA_CENTER),
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
