"""
Dental arch SVG chart for the OPG AI Assistant.

render_tooth_chart_html(findings, missing_teeth) → self-contained HTML string
tooth_display_name(fdi)                          → "UR Central Incisor"
"""
from __future__ import annotations

# ── FDI arch layout (patient right → left = image left → right) ──────────────
_UPPER = ["18","17","16","15","14","13","12","11","21","22","23","24","25","26","27","28"]
_LOWER = ["48","47","46","45","44","43","42","41","31","32","33","34","35","36","37","38"]

# Crown widths by tooth type (second digit of FDI)
_CROWN_W = {1: 29, 2: 29, 3: 32, 4: 36, 5: 36, 6: 45, 7: 45, 8: 47}
_CROWN_H = 29
_ROOT_H  = 22

# Urgency → hex fill & stroke
_FILL = {
    "urgent":      "#dc2626",
    "pathology":   "#ea580c",
    "restoration": "#1d4ed8",
    "impacted":    "#7c3aed",
    "monitor":     "#b45309",
    "normal":      "#15803d",
    "missing":     "#0f172a",
    "default":     "#1e293b",
}
_STROKE = {
    "urgent":      "#fca5a5",
    "pathology":   "#fed7aa",
    "restoration": "#bfdbfe",
    "impacted":    "#ddd6fe",
    "monitor":     "#fde68a",
    "normal":      "#bbf7d0",
    "missing":     "#334155",
    "default":     "#475569",
}

_GAP    = 3
_PAD_X  = 26
_PAD_Y  = 22
_ARCH_G = 12   # gap between upper crown-bottom and lower crown-top

# Tooth-type readable names
_QUAD   = {"1": "UR", "2": "UL", "3": "LL", "4": "LR"}
_TNAME  = {
    "1": "Central Incisor", "2": "Lateral Incisor",
    "3": "Canine",          "4": "1st Premolar",
    "5": "2nd Premolar",    "6": "1st Molar",
    "7": "2nd Molar",       "8": "3rd Molar",
}


def tooth_display_name(fdi: str) -> str:
    """'36' → 'LL 1st Molar'"""
    if len(fdi) == 2:
        return f"{_QUAD.get(fdi[0], '?')} {_TNAME.get(fdi[1], '?')}"
    return fdi


def render_tooth_chart_html(findings: list[dict],
                             missing_teeth: list[str] | None = None) -> str:
    """
    Return a self-contained HTML page containing the SVG tooth chart.
    Use with st.components.v1.html(html_str, height=...).
    """
    # Build urgency map (keep highest-urgency per tooth)
    priority = ["urgent","pathology","impacted","restoration","monitor","normal","default"]
    urgency_map: dict[str, str] = {}
    for f in findings:
        t, u = f["tooth"], f["urgency"]
        if t not in urgency_map or priority.index(u) < priority.index(urgency_map[t]):
            urgency_map[t] = u
    for t in (missing_teeth or []):
        urgency_map[t] = "missing"

    # ── Geometry ─────────────────────────────────────────────────────────────
    row_h     = _CROWN_H + _ROOT_H
    label_h   = 13          # height reserved for FDI number labels
    legend_h  = 26
    spacing   = 6           # bottom padding before legend

    total_w = _PAD_X * 2 + sum(_CROWN_W.get(int(t[1]), 38) for t in _UPPER) + _GAP * 15
    total_h = (_PAD_Y + label_h               # top padding + upper labels
               + row_h                        # upper teeth
               + _ARCH_G                      # gap between arches
               + row_h                        # lower teeth
               + label_h + spacing            # lower labels
               + legend_h + 4)                # legend

    svg: list[str] = []
    svg.append(f'<svg width="{total_w}" height="{total_h}" xmlns="http://www.w3.org/2000/svg">')

    # Dark background
    svg.append(f'<rect width="{total_w}" height="{total_h}" fill="#0f172a" rx="12"/>')

    # Midline
    mid_x = total_w / 2
    arch_top    = _PAD_Y + label_h
    arch_bottom = arch_top + row_h + _ARCH_G + row_h
    svg.append(f'<line x1="{mid_x:.1f}" y1="{arch_top}" x2="{mid_x:.1f}" y2="{arch_bottom}" '
               f'stroke="#334155" stroke-width="1.5" stroke-dasharray="5,3"/>')

    # R / L labels
    svg.append(f'<text x="{mid_x-28:.1f}" y="{arch_top-6}" fill="#475569" '
               f'font-size="9" font-family="Arial,sans-serif">&#8592; R</text>')
    svg.append(f'<text x="{mid_x+6:.1f}"  y="{arch_top-6}" fill="#475569" '
               f'font-size="9" font-family="Arial,sans-serif">L &#8594;</text>')

    # "UPPER" / "LOWER" vertical labels
    upper_mid_y = arch_top + row_h / 2
    lower_mid_y = arch_top + row_h + _ARCH_G + row_h / 2
    svg.append(f'<text x="10" y="{upper_mid_y+18:.1f}" fill="#334155" '
               f'font-size="8" font-family="Arial,sans-serif" '
               f'transform="rotate(-90,10,{upper_mid_y:.1f})">UPPER</text>')
    svg.append(f'<text x="10" y="{lower_mid_y+18:.1f}" fill="#334155" '
               f'font-size="8" font-family="Arial,sans-serif" '
               f'transform="rotate(-90,10,{lower_mid_y:.1f})">LOWER</text>')

    # ── Draw one arch row ─────────────────────────────────────────────────────
    def draw_row(teeth: list[str], y_base: int, flipped: bool) -> None:
        x = _PAD_X
        for tooth in teeth:
            cw   = _CROWN_W.get(int(tooth[1]), 38)
            urg  = urgency_map.get(tooth, "default")
            fill = _FILL[urg]
            stk  = _STROKE[urg]

            rw   = cw * 0.52
            rx_c = min(cw * 0.28, 9)
            rx_r = min(rw * 0.4, 7)
            rx_f = x + (cw - rw) / 2   # root x

            if not flipped:
                # Upper: root ↑, crown ↓
                crown_y = y_base + _ROOT_H
                root_y  = y_base
                label_y = root_y - 3

                svg.append(
                    f'<rect x="{rx_f:.1f}" y="{root_y}" w="{rw:.1f}" width="{rw:.1f}" '
                    f'height="{_ROOT_H}" fill="{fill}" opacity="0.50" rx="{rx_r:.1f}"/>')
                svg.append(
                    f'<rect x="{x:.1f}" y="{crown_y}" width="{cw}" height="{_CROWN_H}" '
                    f'fill="{fill}" rx="{rx_c:.1f}" '
                    f'stroke="{stk}" stroke-width="0.8"/>')
                # FDI label above root
                svg.append(
                    f'<text x="{x+cw/2:.1f}" y="{label_y}" text-anchor="middle" '
                    f'fill="#64748b" font-size="8" font-family="Arial,sans-serif">{tooth}</text>')
            else:
                # Lower: crown ↑, root ↓
                crown_y = y_base
                root_y  = y_base + _CROWN_H
                label_y = root_y + _ROOT_H + 10

                svg.append(
                    f'<rect x="{x:.1f}" y="{crown_y}" width="{cw}" height="{_CROWN_H}" '
                    f'fill="{fill}" rx="{rx_c:.1f}" '
                    f'stroke="{stk}" stroke-width="0.8"/>')
                svg.append(
                    f'<rect x="{rx_f:.1f}" y="{root_y}" width="{rw:.1f}" '
                    f'height="{_ROOT_H}" fill="{fill}" opacity="0.50" rx="{rx_r:.1f}"/>')
                # FDI label below root
                svg.append(
                    f'<text x="{x+cw/2:.1f}" y="{label_y}" text-anchor="middle" '
                    f'fill="#64748b" font-size="8" font-family="Arial,sans-serif">{tooth}</text>')

            # White dot = has finding
            if urg not in ("default", "missing", "normal"):
                dot_y = crown_y + 4 if not flipped else crown_y + 4
                svg.append(
                    f'<circle cx="{x+cw-5:.1f}" cy="{dot_y:.1f}" '
                    f'r="3" fill="white" opacity="0.9"/>')

            x += cw + _GAP

    draw_row(_UPPER, arch_top,                      flipped=False)
    draw_row(_LOWER, arch_top + row_h + _ARCH_G,    flipped=True)

    # ── Legend ────────────────────────────────────────────────────────────────
    legend_items = [
        ("urgent",      "Urgent"),
        ("pathology",   "Pathology"),
        ("restoration", "Restored"),
        ("impacted",    "Impacted"),
        ("monitor",     "Monitor"),
        ("missing",     "Missing"),
        ("default",     "No data"),
    ]
    step = total_w / len(legend_items)
    ly = total_h - legend_h + 16
    lx = _PAD_X / 2
    for key, label in legend_items:
        svg.append(
            f'<rect x="{lx:.1f}" y="{ly-10}" width="12" height="12" '
            f'fill="{_FILL[key]}" rx="2" stroke="{_STROKE[key]}" stroke-width="0.6"/>')
        svg.append(
            f'<text x="{lx+15:.1f}" y="{ly}" fill="#94a3b8" '
            f'font-size="9" font-family="Arial,sans-serif">{label}</text>')
        lx += step

    svg.append('</svg>')

    svg_str = "".join(svg)
    return f"""<!DOCTYPE html>
<html>
<head>
<style>
  body {{ margin:0; padding:2px; background:#0f172a; overflow:hidden; }}
  div  {{ overflow-x:auto; }}
</style>
</head>
<body>
<div>{svg_str}</div>
</body>
</html>"""
