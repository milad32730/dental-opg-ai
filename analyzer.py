import base64
import os
from typing import Optional

FULL_ANALYSIS_PROMPT = """You are a highly experienced dental radiologist with 20+ years of expertise in OPG (Orthopantomogram / panoramic X-ray) interpretation.

Analyze the provided panoramic dental radiograph and produce a comprehensive, structured clinical report using the framework below. Use FDI Two-Digit Notation throughout.

---

## 1. EXECUTIVE SUMMARY
Provide 3–5 sentences covering the most clinically significant findings and overall radiographic impression.

---

## 2. TOOTH INVENTORY

### Present Teeth
List all visible teeth by FDI number.

### Missing Teeth / Edentulous Areas
List all apparent missing teeth.

### Impacted / Unerupted Teeth
For each: FDI number, angulation (vertical / mesioangular / distoangular / horizontal), depth, relationship to adjacent structures.

### Partially Erupted
Note any partially erupted teeth and stage of eruption.

### Supernumerary / Anomalous Teeth
Describe location, morphology, and potential impact.

---

## 3. EXISTING RESTORATIONS & PROSTHETICS

For each item include: teeth involved, material (if identifiable), condition impression.

- Amalgam / composite restorations
- Crowns (single unit / bridge abutments)
- Fixed partial dentures (bridge span)
- Dental implants (osseointegration impression)
- Root canal treated teeth (obturation quality: adequate / short / overfill)
- Post and core restorations
- Removable prosthetic components (if visible)

---

## 4. PATHOLOGY FINDINGS

### 4a. Caries
For each lesion:
- Tooth (FDI) and surface (M/D/O/B/L/I)
- Severity: enamel / dentine / approaching pulp / pulpal involvement
- Confidence: [HIGH] / [MEDIUM] / [LOW]

### 4b. Periapical Pathology
For each area:
- Tooth / region
- Description: periapical lucency, widening of PDL space, rarefaction
- Size estimate
- Differential: periapical granuloma / cyst / abscess
- Confidence: [HIGH] / [MEDIUM] / [LOW]

### 4c. Periodontal Bone Level Assessment
- Overall bone level: normal (2–3 mm below CEJ) / mildly / moderately / severely reduced
- Pattern: horizontal / vertical / angular / mixed
- Severity: mild (<25%) / moderate (25–50%) / severe (>50%)
- Distribution: localized / generalized
- Furcation involvement (Glickman grade if assessable)
- Specific sites of concern: list by FDI

### 4d. Cysts and Lesions
For each:
- Location and size estimate
- Borders: well-defined / ill-defined / corticated
- Unilocular / multilocular
- Associated teeth
- Differential diagnosis (ranked)
- Confidence: [HIGH] / [MEDIUM] / [LOW]

### 4e. Root Abnormalities
- Dilacerations (tooth and direction)
- External root resorption (site and severity)
- Internal root resorption
- Root fractures (if visible)
- Hypercementosis
- Pulp canal obliteration

### 4f. Calcifications (Incidental Findings)
- Pulp stones (location)
- Sialoliths (gland / duct)
- Carotid artery calcifications (bilateral assessment — clinically significant)
- Tonsilloliths
- Other calcifications with location

---

## 5. ANATOMICAL STRUCTURES

### Maxillary Sinuses (bilateral)
- Right: normal / mucosal thickening / partial opacification / complete opacification / other
- Left: normal / mucosal thickening / partial opacification / complete opacification / other
- Tooth–sinus relationship (proximity of upper posterior roots)

### Mandibular Canal
- Visibility and continuity (right / left)
- Relationship to lower third molars (if present)
- Cortical plate integrity

### Temporomandibular Joints (bilateral)
- Condylar shape: normal / flattened / irregular / erosive / osteophytic
- Size symmetry
- Articular surface irregularities
- Apparent joint space
- Any significant asymmetry

### Bone Quality
- Overall trabecular pattern impression
- Cortical plate integrity (lower border of mandible, anterior nasal spine, etc.)
- Overall bone density impression: normal / reduced / mixed

---

## 6. DEVELOPMENTAL AND SKELETAL FINDINGS
- Root development stages for erupting teeth (Nolla stages if assessable)
- Crown morphology variations / dens invaginatus / taurodontism etc.
- Skeletal jaw relationship impression (if assessable from OPG)
- Asymmetries

---

## 7. IMAGE QUALITY NOTES
- Overall diagnostic quality: excellent / good / acceptable / limited
- Areas of poor image quality or patient movement
- Findings potentially obscured by artifacts or overlapping structures

---

## 8. AREAS REQUIRING FURTHER INVESTIGATION
List any areas where findings are inconclusive and additional imaging (periapical X-rays, CBCT, occlusal views) would be beneficial, with the clinical reason.

---

## 9. CLINICAL RECOMMENDATIONS

**PRIORITY 1 — Urgent (address within 1–2 weeks):**
- (List items)

**PRIORITY 2 — Routine (address within 1–3 months):**
- (List items)

**PRIORITY 3 — Monitor (review at next recall):**
- (List items)

**Additional Imaging Recommended:**
- (List with rationale)

**Specialist Referral Suggested:**
- (List specialty and reason)

---

*This AI-assisted analysis is a clinical decision-support tool. All findings must be correlated with the patient's clinical presentation, medical history, and examination findings, and verified by the treating clinician before any clinical decisions are made.*"""

QUICK_SCREENING_PROMPT = """You are an expert dental radiologist. Quickly screen this OPG and provide:

1. **Key Pathological Findings** — List the most significant findings in bullet points (tooth/FDI, finding, severity).
2. **Urgent Items** — Flag anything requiring prompt attention.
3. **Overall Impression** — One sentence summary.
4. **Recommended Next Steps** — Brief list.

Be concise and clinically focused. Use FDI notation."""


def _build_prompt(mode: str, patient_context: Optional[str]) -> str:
    base = QUICK_SCREENING_PROMPT if mode == "quick" else FULL_ANALYSIS_PROMPT
    if patient_context and patient_context.strip():
        base += (
            f"\n\n---\n**Clinical Context Provided by Dentist:**\n{patient_context.strip()}\n"
            "Please incorporate this information into your assessment.\n---"
        )
    return base


def _analyze_anthropic(image_base64: str, prompt: str) -> str:
    import anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    client  = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64",
                                             "media_type": "image/jpeg",
                                             "data": image_base64}},
                {"type": "text",  "text": prompt},
            ],
        }],
    )
    return message.content[0].text


def _analyze_gemini(image_base64: str, prompt: str) -> str:
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    client  = genai.Client(api_key=api_key)

    img_bytes = base64.b64decode(image_base64)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
            types.Part.from_text(text=prompt),
        ],
    )
    return response.text


def analyze_opg(image_base64: str, patient_context: Optional[str] = None,
                mode: str = "full") -> str:
    """Analyse an OPG image.  Auto-selects provider based on available API keys.

    Priority: ANTHROPIC_API_KEY → GEMINI_API_KEY
    Get a free Gemini key at: https://aistudio.google.com/apikey
    """
    prompt = _build_prompt(mode, patient_context)

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    gemini_key    = os.environ.get("GEMINI_API_KEY",    "").strip()

    if anthropic_key:
        return _analyze_anthropic(image_base64, prompt)
    elif gemini_key:
        return _analyze_gemini(image_base64, prompt)
    else:
        raise ValueError(
            "No API key found.\n"
            "  • Free option : set GEMINI_API_KEY    (https://aistudio.google.com/apikey)\n"
            "  • Paid option : set ANTHROPIC_API_KEY (https://console.anthropic.com/settings/keys)"
        )
