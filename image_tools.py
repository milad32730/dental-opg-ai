"""
Advanced image analysis toolkit for dental OPG.

Tools:
  - AI Finding Overlay  : colour-coded FDI markers parsed from the report
  - Bone Density Heatmap: false-colour density map (CLAHE + colormap blend)
  - Multi-Enhancement Grid: all 7 modes rendered simultaneously
  - Quadrant Zoom        : UR / UL / LL / LR magnified extraction
  - Brightness Profile   : horizontal density scan (bone density proxy)
  - Annotated Report Image: clean overlay suitable for embedding in PDF
"""

import io
import re
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter


# ── FDI approximate positions (normalised x, y) on a standard panoramic ──────
# Calibrated from DENTEX / Tufts dataset panoramic landmark statistics.
# x: 0 = left edge, 1 = right edge   (patient's R is on image L)
# y: 0 = top,       1 = bottom

_FDI_POSITIONS: dict[str, tuple[float, float]] = {
    # Upper right (Q1) — image LEFT side
    "18": (0.11, 0.32), "17": (0.17, 0.30), "16": (0.23, 0.29),
    "15": (0.29, 0.28), "14": (0.33, 0.28), "13": (0.37, 0.27),
    "12": (0.41, 0.26), "11": (0.44, 0.26),
    # Upper left (Q2) — image RIGHT side
    "21": (0.56, 0.26), "22": (0.59, 0.26), "23": (0.63, 0.27),
    "24": (0.67, 0.28), "25": (0.71, 0.28), "26": (0.77, 0.29),
    "27": (0.83, 0.30), "28": (0.89, 0.32),
    # Lower right (Q4) — image LEFT side
    "48": (0.10, 0.72), "47": (0.17, 0.70), "46": (0.23, 0.68),
    "45": (0.29, 0.67), "44": (0.33, 0.66), "43": (0.37, 0.65),
    "42": (0.41, 0.65), "41": (0.44, 0.65),
    # Lower left (Q3) — image RIGHT side
    "31": (0.56, 0.65), "32": (0.59, 0.65), "33": (0.63, 0.65),
    "34": (0.67, 0.66), "35": (0.71, 0.67), "36": (0.77, 0.68),
    "37": (0.83, 0.70), "38": (0.90, 0.72),
}

# Urgency colour mapping
_URGENCY_COLOURS = {
    "urgent":      (220, 38,  38,  200),   # red
    "pathology":   (234, 88,  12,  190),   # orange
    "restoration": (59,  130, 246, 180),   # blue
    "impacted":    (168, 85,  247, 180),   # purple
    "monitor":     (234, 179, 8,   170),   # yellow
    "normal":      (34,  197, 94,  160),   # green
    "default":     (156, 163, 175, 160),   # grey
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. AI FINDING OVERLAY
# ─────────────────────────────────────────────────────────────────────────────

def parse_fdi_findings(analysis_text: str) -> list[dict]:
    """
    Extract FDI tooth references and classify urgency from report text.
    Returns list of {tooth, label, urgency, snippet}.
    """
    # Pattern: standalone 2-digit FDI codes (11-18, 21-28, 31-38, 41-48)
    fdi_re = re.compile(
        r'\b([1-4][1-8])\b'   # FDI number
        r'([^.\n]{0,120})',    # surrounding context
    )

    # Urgency keywords
    urgent_kw    = r'abscess|urgent|caries|cavity|cavit|resorption|fracture|periapical|PAI [3-5]|Stage (III|IV)'
    pathology_kw = r'lucen|lesion|bone loss|periodont|Stage (II|III|IV)|furcation|PAI [2-5]|impacted|radiolucen'
    restore_kw   = r'crown|amalgam|composite|filling|implant|RCT|root canal|obturat|restoration'
    impacted_kw  = r'impacted|unerupt|mesioangul|distoangul|horizontal|Winter|Pell'
    monitor_kw   = r'monitor|review|recall|sinus|mild|minimal'

    findings: dict[str, dict] = {}

    for m in fdi_re.finditer(analysis_text):
        tooth   = m.group(1)
        snippet = m.group(2).lower()

        if tooth not in _FDI_POSITIONS:
            continue

        if re.search(urgent_kw, snippet, re.I):
            urgency = "urgent"
        elif re.search(restore_kw, snippet, re.I):
            urgency = "restoration"
        elif re.search(impacted_kw, snippet, re.I):
            urgency = "impacted"
        elif re.search(pathology_kw, snippet, re.I):
            urgency = "pathology"
        elif re.search(monitor_kw, snippet, re.I):
            urgency = "monitor"
        else:
            urgency = "default"

        # Keep highest-urgency mention per tooth
        priority = ["urgent","pathology","impacted","restoration","monitor","normal","default"]
        if tooth not in findings or priority.index(urgency) < priority.index(findings[tooth]["urgency"]):
            findings[tooth] = {
                "tooth":   tooth,
                "urgency": urgency,
                "snippet": m.group(2).strip()[:80],
            }

    return list(findings.values())


def create_finding_overlay(img: Image.Image,
                           findings: list[dict],
                           show_labels: bool = True,
                           show_legend: bool = True) -> Image.Image:
    """
    Draw colour-coded FDI markers on the OPG.
    Returns a new PIL Image with findings overlaid.
    """
    result = img.convert("RGBA")
    overlay = Image.new("RGBA", result.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    W, H = img.size
    r_base = max(12, min(W, H) // 55)   # marker radius scales with image

    try:
        font = ImageFont.truetype("arial.ttf", max(10, r_base))
    except Exception:
        font = ImageFont.load_default()

    for f in findings:
        tooth   = f["tooth"]
        urgency = f["urgency"]
        colour  = _URGENCY_COLOURS.get(urgency, _URGENCY_COLOURS["default"])
        nx, ny  = _FDI_POSITIONS[tooth]
        cx, cy  = int(nx * W), int(ny * H)

        # Filled circle with slight transparency
        draw.ellipse(
            [(cx - r_base, cy - r_base), (cx + r_base, cy + r_base)],
            fill=colour,
            outline=(255, 255, 255, 220),
        )

        if show_labels:
            draw.text((cx, cy), tooth, fill=(255, 255, 255, 255),
                      font=font, anchor="mm")

    # Legend
    if show_legend and findings:
        _draw_legend(draw, W, H, font)

    result = Image.alpha_composite(result, overlay)
    return result.convert("RGB")


def _draw_legend(draw: ImageDraw.ImageDraw, W: int, H: int, font) -> None:
    items = [
        ("urgent",      "Urgent pathology"),
        ("pathology",   "Pathology / bone loss"),
        ("impacted",    "Impacted tooth"),
        ("restoration", "Restoration"),
        ("monitor",     "Monitor / mild"),
    ]
    pad, box = 8, 14
    lx, ly = 10, H - (len(items) * (box + 4) + pad * 2)
    # Background
    draw.rectangle(
        [(lx - 4, ly - 4), (lx + 160, H - 4)],
        fill=(0, 0, 0, 140), outline=(255, 255, 255, 80)
    )
    for label, desc in items:
        col = _URGENCY_COLOURS[label]
        draw.rectangle([(lx, ly), (lx + box, ly + box)], fill=col)
        draw.text((lx + box + 5, ly), desc, fill=(255, 255, 255, 230), font=font)
        ly += box + 4


# ─────────────────────────────────────────────────────────────────────────────
# 2. BONE DENSITY HEATMAP
# ─────────────────────────────────────────────────────────────────────────────

def density_heatmap(img: Image.Image, alpha: float = 0.55,
                    colormap: int = cv2.COLORMAP_INFERNO) -> Image.Image:
    """
    False-colour bone density overlay.
    Low density (dark areas) → warm colours (red/orange).
    High density (bright areas) → cool colours (blue/purple).
    alpha: blend weight of the heatmap over the original (0 = original, 1 = full heatmap).
    """
    gray = np.array(img.convert("L"))

    # CLAHE to enhance local contrast
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Invert: in X-ray, dark = low density; we want low density → hot colour
    inverted = 255 - enhanced

    # Apply colourmap
    heatmap_bgr = cv2.applyColorMap(inverted, colormap)
    heatmap_rgb = cv2.cvtColor(heatmap_bgr, cv2.COLOR_BGR2RGB)

    # Blend with original
    orig_rgb = np.array(img.convert("RGB"))
    blended  = cv2.addWeighted(orig_rgb, 1 - alpha, heatmap_rgb, alpha, 0)

    return Image.fromarray(blended)


# ─────────────────────────────────────────────────────────────────────────────
# 3. MULTI-ENHANCEMENT GRID
# ─────────────────────────────────────────────────────────────────────────────

def create_multipanel_grid(img: Image.Image,
                           cols: int = 3) -> Image.Image:
    """
    Render all enhancement modes + heatmap in a labelled grid.
    Returns a single PIL Image.
    """
    from image_handler import enhance_image

    panels = [
        ("Original",    img),
        ("CLAHE",       enhance_image(img, "clahe")),
        ("Contrast",    enhance_image(img, "contrast")),
        ("Sharpen",     enhance_image(img, "sharpen")),
        ("Inverted",    enhance_image(img, "inverted")),
        ("Edges",       enhance_image(img, "edges")),
        ("Density Map", density_heatmap(img, alpha=0.6)),
    ]

    # Thumb size
    tw = img.width  // 2
    th = img.height // 2
    rows = (len(panels) + cols - 1) // cols

    grid = Image.new("RGB", (tw * cols, th * rows + 24 * rows), (20, 20, 20))

    try:
        font = ImageFont.truetype("arial.ttf", 13)
    except Exception:
        font = ImageFont.load_default()

    for i, (label, panel) in enumerate(panels):
        row, col = divmod(i, cols)
        thumb = panel.convert("RGB").resize((tw, th), Image.LANCZOS)
        x, y  = col * tw, row * (th + 24)
        grid.paste(thumb, (x, y + 24))

        # Label bar
        draw = ImageDraw.Draw(grid)
        draw.rectangle([(x, y), (x + tw, y + 24)], fill=(40, 40, 40))
        draw.text((x + tw // 2, y + 12), label, fill=(220, 220, 220), font=font, anchor="mm")

    return grid


# ─────────────────────────────────────────────────────────────────────────────
# 4. QUADRANT ZOOM
# ─────────────────────────────────────────────────────────────────────────────

# Crop boxes for each quadrant (normalised x0, y0, x1, y1)
_QUADRANT_BOXES = {
    "Upper Right (Q1 — teeth 11–18)": (0.04, 0.10, 0.52, 0.60),
    "Upper Left  (Q2 — teeth 21–28)": (0.48, 0.10, 0.96, 0.60),
    "Lower Right (Q4 — teeth 41–48)": (0.04, 0.45, 0.52, 0.95),
    "Lower Left  (Q3 — teeth 31–38)": (0.48, 0.45, 0.96, 0.95),
    "Anterior (teeth 13–23 / 43–33)": (0.32, 0.15, 0.68, 0.90),
    "TMJ — Right":                    (0.00, 0.00, 0.18, 0.55),
    "TMJ — Left":                     (0.82, 0.00, 1.00, 0.55),
}


def quadrant_zoom(img: Image.Image, quadrant_name: str,
                  enhance: str = "clahe") -> Image.Image:
    """
    Crop and magnify a labelled quadrant region with enhancement.
    """
    from image_handler import enhance_image
    W, H = img.size
    x0n, y0n, x1n, y1n = _QUADRANT_BOXES[quadrant_name]
    box = (int(x0n * W), int(y0n * H), int(x1n * W), int(y1n * H))
    cropped = img.crop(box)

    if enhance != "none":
        cropped = enhance_image(cropped, enhance)

    # Scale up to at least 700 px wide for visibility
    scale  = max(1.0, 700 / cropped.width)
    target = (int(cropped.width * scale), int(cropped.height * scale))
    return cropped.resize(target, Image.LANCZOS)


def quadrant_options() -> list[str]:
    return list(_QUADRANT_BOXES.keys())


# ─────────────────────────────────────────────────────────────────────────────
# 5. BRIGHTNESS PROFILE (bone density proxy)
# ─────────────────────────────────────────────────────────────────────────────

def brightness_profile(img: Image.Image,
                       region: str = "full") -> tuple[np.ndarray, np.ndarray]:
    """
    Compute column-wise mean brightness across the image (or a jaw band).
    Returns (x_positions_normalised, brightness_values_0_to_255).

    region: "full" | "upper_jaw" | "lower_jaw" | "mandible"
    """
    W, H = img.size
    gray = np.array(img.convert("L")).astype(float)

    bands = {
        "full":        (0.0,  1.0),
        "upper_jaw":   (0.20, 0.50),
        "lower_jaw":   (0.50, 0.82),
        "mandible":    (0.60, 0.88),
    }
    y0n, y1n = bands.get(region, (0.0, 1.0))
    y0, y1 = int(y0n * H), int(y1n * H)

    # Gaussian blur to suppress noise
    band  = cv2.GaussianBlur(gray[y0:y1, :], (1, 31), 0)
    col_mean = band.mean(axis=0)

    x_pos = np.linspace(0, 1, W)
    return x_pos, col_mean


# ─────────────────────────────────────────────────────────────────────────────
# 6. ANNOTATED EXPORT (for PDF embedding)
# ─────────────────────────────────────────────────────────────────────────────

def annotated_report_image(img: Image.Image,
                           findings: list[dict]) -> bytes:
    """
    Create an annotated OPG with findings marked, suitable for PDF embedding.
    Returns JPEG bytes.
    """
    # Use CLAHE-enhanced base for better visibility
    from image_handler import enhance_image
    base = enhance_image(img, "clahe")
    annotated = create_finding_overlay(base, findings, show_labels=True, show_legend=True)

    buf = io.BytesIO()
    annotated.save(buf, format="JPEG", quality=92)
    return buf.getvalue()
