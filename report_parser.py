"""
Structured extraction of per-tooth findings from AI analysis text.

Public API
----------
extract_per_tooth_findings(text) → dict[FDI, list[finding_dict]]
parse_missing_teeth(text)         → list[FDI_str]
extract_recommendations(text)     → dict[priority_key, list[str]]
build_patient_summary(per_tooth)  → str  (plain English)
tooth_display_name(fdi)           → str
"""
from __future__ import annotations
import re

# ── FDI helpers ───────────────────────────────────────────────────────────────
_ALL_FDI = {f"{q}{t}" for q in range(1, 5) for t in range(1, 9)}

_QUAD  = {"1": "Upper Right", "2": "Upper Left",
          "3": "Lower Left",  "4": "Lower Right"}
_TNAME = {
    "1": "Central Incisor", "2": "Lateral Incisor",
    "3": "Canine",          "4": "1st Premolar",
    "5": "2nd Premolar",    "6": "1st Molar",
    "7": "2nd Molar",       "8": "3rd Molar (Wisdom)",
}


def tooth_display_name(fdi: str) -> str:
    """'36' → 'Lower Left 1st Molar'"""
    if len(fdi) == 2 and fdi[0] in _QUAD:
        return f"{_QUAD[fdi[0]]} {_TNAME.get(fdi[1], '')}".strip()
    return fdi


# ── Section → category mapping ────────────────────────────────────────────────
_SECTION_CAT = [
    ("caries",        re.compile(r"4a|caries|cavit", re.I)),
    ("periapical",    re.compile(r"4b|periapical|apical|abscess|lucen", re.I)),
    ("periodontal",   re.compile(r"4c|periodontal|bone.level|bone.loss", re.I)),
    ("cyst",          re.compile(r"4d|cyst|lesion|radiolucen", re.I)),
    ("root",          re.compile(r"4e|root.abnorm|dilacerat|resorption|fracture", re.I)),
    ("calcification", re.compile(r"4f|calcif|stone|sialolith", re.I)),
    ("restoration",   re.compile(r"^\s*#+\s*3|restora|crown|filling|implant|rct|root.canal", re.I)),
    ("impacted",      re.compile(r"impacted|unerupt|winter|pell", re.I)),
    ("missing",       re.compile(r"missing|absent|edentul", re.I)),
]

_URGENCY_RE = {
    "urgent":      re.compile(r"abscess|urgent|caries|cavity|resorption|fracture|periapical|PAI [3-5]|Stage (III|IV)", re.I),
    "pathology":   re.compile(r"lucen|lesion|bone loss|periodont|Stage (II|III|IV)|furcation|PAI [2-5]|radiolucen", re.I),
    "restoration": re.compile(r"crown|amalgam|composite|filling|implant|RCT|root canal|obturat|restoration", re.I),
    "impacted":    re.compile(r"impacted|unerupt|mesioangul|distoangul|horizontal", re.I),
    "monitor":     re.compile(r"monitor|review|recall|sinus|mild|minimal", re.I),
}

_CONF_RE = re.compile(r"\[(HIGH|MEDIUM|LOW)\]", re.I)
_FDI_RE  = re.compile(r"\b([1-4][1-8])\b(.{0,200}?)(?=\n|$)", re.DOTALL)


def _classify(text: str) -> str:
    for urg, rx in _URGENCY_RE.items():
        if rx.search(text):
            return urg
    return "default"


def _detect_section_cat(header: str) -> str:
    for cat, rx in _SECTION_CAT:
        if rx.search(header):
            return cat
    return "general"


# ── Main extraction ───────────────────────────────────────────────────────────

def extract_per_tooth_findings(text: str) -> dict[str, list[dict]]:
    """
    Parse structured per-tooth findings from the AI report.

    Returns
    -------
    dict mapping FDI code → list of dicts:
        {category, description, confidence, urgency}
    """
    findings: dict[str, list[dict]] = {}
    _prio = ["urgent", "pathology", "impacted", "restoration", "monitor", "normal", "default"]

    # Split on section headings
    sections = re.split(r"(?=\n#{1,4}\s)", "\n" + text)

    for section in sections:
        if not section.strip():
            continue
        header = section.split("\n")[0]
        cat    = _detect_section_cat(header)

        # Find all FDI mentions with surrounding context
        for m in _FDI_RE.finditer(section):
            tooth = m.group(1)
            if tooth not in _ALL_FDI:
                continue
            desc = m.group(2).strip().rstrip(".,;")
            if len(desc) < 3:
                continue

            # Extract confidence from nearby text (±300 chars)
            ctx  = section[max(0, m.start()-50): m.start() + 300]
            cm   = _CONF_RE.search(ctx)
            conf = cm.group(1).upper() if cm else ""

            urgency = _classify(desc)

            entry = {
                "category":    cat,
                "description": desc[:220],
                "confidence":  conf,
                "urgency":     urgency,
            }

            # Keep per-tooth list; de-duplicate very similar descriptions
            existing = findings.setdefault(tooth, [])
            if not any(e["description"][:60] == entry["description"][:60] for e in existing):
                existing.append(entry)

    return findings


def parse_missing_teeth(text: str) -> list[str]:
    """Extract FDI codes of missing teeth from the Tooth Inventory section."""
    m = re.search(
        r"(?:Missing Teeth|Missing|Absent)[^\n]*\n(.*?)(?=###|\n##|\Z)",
        text, re.S | re.I,
    )
    if not m:
        return []
    missing: list[str] = []
    for fm in re.finditer(r"\b([1-4][1-8])\b", m.group(1)):
        t = fm.group(1)
        if t in _ALL_FDI and t not in missing:
            missing.append(t)
    return missing


def extract_recommendations(text: str) -> dict[str, list[str]]:
    """
    Parse Section 9 Clinical Recommendations into structured lists.

    Returns
    -------
    dict with keys: priority_1, priority_2, priority_3, imaging, referral
    """
    result: dict[str, list[str]] = {
        "priority_1": [], "priority_2": [], "priority_3": [],
        "imaging": [], "referral": [],
    }

    sec = re.search(
        r"##\s*9\.?\s*CLINICAL RECOMMENDATIONS(.*?)(?=\n##\s|\Z)",
        text, re.S | re.I,
    )
    if not sec:
        return result

    body = sec.group(1)

    _patterns: dict[str, str] = {
        "priority_1": r"PRIORITY\s*1[^\n]*(.*?)(?=PRIORITY\s*2|Additional Imaging|Specialist|\Z)",
        "priority_2": r"PRIORITY\s*2[^\n]*(.*?)(?=PRIORITY\s*3|Additional Imaging|Specialist|\Z)",
        "priority_3": r"PRIORITY\s*3[^\n]*(.*?)(?=PRIORITY\s*4|Additional Imaging|Specialist|\Z)",
        "imaging":    r"Additional Imaging[^\n]*(.*?)(?=Specialist|\Z)",
        "referral":   r"Specialist Referral[^\n]*(.*?)(?=\n##|\Z)",
    }

    for key, pat in _patterns.items():
        m = re.search(pat, body, re.S | re.I)
        if m:
            lines = re.findall(r"[-•*]\s*(.+?)(?=\n|$)", m.group(1))
            cleaned = [
                l.strip() for l in lines
                if l.strip() and l.strip() not in ("(List items)", "(List)") and len(l.strip()) > 4
            ]
            result[key] = cleaned

    return result


# ── Patient-friendly summary ──────────────────────────────────────────────────

_SIMPLE_NAMES: dict[str, str] = {
    "caries":        "decay / cavity",
    "periapical":    "infection near the root tip",
    "periodontal":   "gum / bone disease",
    "cyst":          "cyst or lesion",
    "root":          "root abnormality",
    "calcification": "calcification",
    "restoration":   "existing dental work",
    "impacted":      "trapped / impacted tooth",
    "missing":       "missing tooth",
    "general":       "clinical finding",
}


def build_patient_summary(per_tooth: dict[str, list[dict]]) -> list[dict]:
    """
    Build a patient-friendly list of findings.

    Returns list of dicts: {tooth, name, urgency, simple_description}
    sorted by urgency priority.
    """
    _prio = ["urgent", "pathology", "impacted", "restoration", "monitor", "normal", "default"]
    rows: list[dict] = []

    for tooth, fs in per_tooth.items():
        if not fs:
            continue
        # Pick highest-urgency finding for this tooth
        best = min(fs, key=lambda f: _prio.index(f["urgency"]) if f["urgency"] in _prio else 99)

        cat_name = _SIMPLE_NAMES.get(best["category"], best["category"])
        rows.append({
            "tooth":       tooth,
            "name":        tooth_display_name(tooth),
            "urgency":     best["urgency"],
            "category":    best["category"],
            "simple_desc": cat_name,
            "detail":      best["description"],
            "confidence":  best["confidence"],
        })

    rows.sort(key=lambda r: _prio.index(r["urgency"]) if r["urgency"] in _prio else 99)
    return rows
