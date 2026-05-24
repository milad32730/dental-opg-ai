import os
from datetime import datetime
from pathlib import Path

import streamlit as st

from analyzer import analyze_opg
from database import (
    delete_case, get_all_cases, get_case, init_db, save_case, search_cases,
)
from image_handler import (
    enhance_image, get_image_bytes, image_to_base64, load_image,
)
from report_generator import generate_pdf_report

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Dental OPG AI Assistant",
    page_icon="🦷",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

# Inject Streamlit Cloud secrets into environment so analyzer picks them up
def _load_secrets():
    try:
        for key in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
            val = st.secrets.get(key, "")
            if val and not os.environ.get(key):
                os.environ[key] = val
    except Exception:
        pass

_load_secrets()

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1a365d 0%, #2b6cb0 100%);
        color: white;
        padding: 22px 28px 16px 28px;
        border-radius: 10px;
        margin-bottom: 18px;
    }
    .main-header h1 { margin: 0; font-size: 26px; }
    .main-header p  { margin: 4px 0 0 0; opacity: .85; font-size: 13px; }

    .finding-card {
        background: #f7fafc;
        border-left: 4px solid #2b6cb0;
        padding: 10px 14px;
        border-radius: 4px;
        margin-bottom: 8px;
        font-size: 14px;
    }
    .urgent-card {
        background: #fff5f5;
        border-left: 4px solid #e53e3e;
        padding: 10px 14px;
        border-radius: 4px;
        margin-bottom: 8px;
    }
    .disclaimer-box {
        background: #ebf8ff;
        border: 1px solid #90cdf4;
        border-radius: 6px;
        padding: 10px 14px;
        font-size: 12px;
        color: #2c5282;
        margin-top: 12px;
    }
    div[data-testid="stExpander"] { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

CASES_DIR = Path(__file__).parent / "cases_images"
CASES_DIR.mkdir(exist_ok=True)

ENHANCEMENT_OPTIONS = [
    'original', 'clahe', 'contrast', 'brightness', 'sharpen', 'inverted', 'edges',
]

ENHANCEMENT_HELP = {
    'original':   'Unmodified image',
    'clahe':      'Adaptive histogram equalisation — best for X-ray detail',
    'contrast':   'Boost overall contrast',
    'brightness': 'Increase brightness',
    'sharpen':    'Accentuate fine structures',
    'inverted':   'Reverse tones (negative)',
    'edges':      'Edge-detection overlay',
}


def _active_provider() -> tuple[str, str]:
    """Return (provider_label, model_name) based on which key is set."""
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return "Claude (Anthropic)", "claude-sonnet-4-6"
    if os.environ.get("GEMINI_API_KEY", "").strip():
        return "Gemini 2.5 Flash (Google)", "gemini-2.5-flash"
    return "", ""


def sidebar():
    with st.sidebar:
        st.markdown("### ⚙️ Configuration")

        # ── Provider tabs ─────────────────────────────────────────────────────
        prov = st.radio(
            "AI Provider",
            ["🆓  Google Gemini (Free)", "💳  Anthropic Claude (Paid)"],
            index=0 if os.environ.get("GEMINI_API_KEY") else 1,
            help="Gemini is free (1,500 analyses/day). Claude is paid (~$0.02/analysis) but slightly more detailed.",
        )

        if "Gemini" in prov:
            gemini_key = st.text_input(
                "Gemini API Key",
                value=os.environ.get("GEMINI_API_KEY", ""),
                type="password",
                help="Free key at: aistudio.google.com/apikey",
            )
            if gemini_key:
                os.environ["GEMINI_API_KEY"] = gemini_key
                os.environ.pop("ANTHROPIC_API_KEY", None)
            if os.environ.get("GEMINI_API_KEY"):
                st.success("Gemini connected — FREE tier active")
            else:
                st.info("Get a free key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)")
        else:
            anthropic_key = st.text_input(
                "Anthropic API Key",
                value=os.environ.get("ANTHROPIC_API_KEY", ""),
                type="password",
                help="Get yours at: console.anthropic.com/settings/keys",
            )
            if anthropic_key:
                os.environ["ANTHROPIC_API_KEY"] = anthropic_key
                os.environ.pop("GEMINI_API_KEY", None)
            if os.environ.get("ANTHROPIC_API_KEY"):
                st.success("Claude connected")
            else:
                st.info("Get a key at [console.anthropic.com](https://console.anthropic.com/settings/keys)")

        # ── Active model badge ────────────────────────────────────────────────
        provider_label, model_name = _active_provider()
        if provider_label:
            st.caption(f"Model: `{model_name}`")

        st.markdown("---")

        # ── Learning stats ────────────────────────────────────────────────────
        try:
            from knowledge_base import get_feedback_stats
            stats = get_feedback_stats()
            if stats:
                st.markdown("### 🧠 AI Learning Progress")
                st.caption(f"Trained on **{stats['total']}** reviewed findings")
                acc = stats['accuracy_pct']
                color = "green" if acc >= 80 else "orange" if acc >= 60 else "red"
                st.markdown(f"Confirmed accuracy: :{color}[**{acc}%**]")
                c1, c2 = st.columns(2)
                c1.metric("Confirmed", stats['confirmed'], help="AI was correct")
                c2.metric("Corrected", stats['corrected'] + stats['missed'] + stats['false_positive'],
                          help="AI was wrong — learned from these")
                st.markdown("---")
        except Exception:
            pass

        cases = get_all_cases()
        col1, col2 = st.columns(2)
        col1.metric("Total Cases", len(cases))
        if cases:
            today = datetime.now().strftime("%Y-%m-%d")
            col2.metric("Today", sum(1 for c in cases if c[6].startswith(today)))

        st.markdown("---")
        st.markdown("""
**Supported formats**
- DICOM (.dcm / .dicom)
- JPEG (.jpg / .jpeg)
- PNG (.png)
- TIFF (.tif / .tiff)
- BMP (.bmp)
""")
        st.markdown("---")
        st.markdown("""
<div class='disclaimer-box'>
⚕️ <b>Medical Disclaimer</b><br>
For clinical decision support only. All findings must be verified by a qualified dental professional.
</div>
""", unsafe_allow_html=True)


def tab_analyze():
    st.subheader("Patient Information")
    pc1, pc2 = st.columns(2)
    with pc1:
        patient_name = st.text_input("Patient Name", placeholder="Full name")
        dentist_name = st.text_input("Dentist Name", placeholder="Dr. Smith")
    with pc2:
        patient_id   = st.text_input("Patient ID / Chart #", placeholder="P-12345")
        clinic_name  = st.text_input("Clinic / Practice",    placeholder="Smile Dental Clinic")

    patient_context = st.text_area(
        "Clinical Context (optional)",
        placeholder="Chief complaint, relevant history, medications, reason for OPG...",
        height=72,
    )

    st.markdown("---")

    # ── Image upload ──────────────────────────────────────────────────────────
    left, right = st.columns([1, 1], gap="large")

    with left:
        st.subheader("Upload OPG")
        uploaded = st.file_uploader(
            "Drag & drop or click to browse",
            type=['dcm', 'dicom', 'jpg', 'jpeg', 'png', 'bmp', 'tif', 'tiff'],
        )

        if uploaded:
            file_bytes = uploaded.read()
            with st.spinner("Loading image…"):
                try:
                    img, dicom_meta = load_image(file_bytes, uploaded.name)
                    st.session_state.update({
                        'img':        img,
                        'file_bytes': file_bytes,
                        'filename':   uploaded.name,
                    })
                    st.success(f"Loaded: {uploaded.name} ({img.width}×{img.height} px)")

                    if dicom_meta:
                        with st.expander("📋 DICOM Metadata"):
                            attrs = [
                                'PatientName', 'PatientID', 'StudyDate', 'Modality',
                                'Manufacturer', 'InstitutionName', 'StudyDescription',
                                'KVP', 'ExposureTime',
                            ]
                            for attr in attrs:
                                if hasattr(dicom_meta, attr):
                                    st.text(f"{attr}: {getattr(dicom_meta, attr)}")
                except Exception as exc:
                    st.error(f"Could not load image: {exc}")

    with right:
        if 'img' in st.session_state:
            st.subheader("Image Preview")
            mode = st.select_slider(
                "Enhancement",
                options=ENHANCEMENT_OPTIONS,
                value='original',
                help=" | ".join(f"{k}: {v}" for k, v in ENHANCEMENT_HELP.items()),
            )
            try:
                display_img = enhance_image(st.session_state['img'], mode=mode)
                st.image(display_img, caption=f"{mode.upper()} view", use_column_width=True)
                dl_bytes = get_image_bytes(display_img)
                st.download_button(
                    "⬇️ Download Enhanced Image",
                    data=dl_bytes,
                    file_name=f"enhanced_{mode}_{st.session_state['filename']}.jpg",
                    mime="image/jpeg",
                )
            except Exception as exc:
                st.warning(f"Enhancement unavailable: {exc}. Showing original.")
                st.image(st.session_state['img'], use_column_width=True)
        else:
            st.info("Upload an OPG image to preview it here.")

    # ── Analysis controls ─────────────────────────────────────────────────────
    if 'img' in st.session_state:
        st.markdown("---")
        bc1, bc2, _ = st.columns([2, 2, 3])
        run_full  = bc1.button("🔬 Full AI Analysis",    type="primary", use_container_width=True)
        run_quick = bc2.button("⚡ Quick Screening",                      use_container_width=True)

        if run_full or run_quick:
            provider_label, model_name = _active_provider()
            if not provider_label:
                st.error("No API key set. Add a free Gemini key or an Anthropic key in the sidebar.")
            else:
                mode_str = "quick" if run_quick else "full"
                label    = "Quick screening" if run_quick else "Full analysis"
                with st.spinner(f"🤖 {label} via {provider_label} — please wait…"):
                    try:
                        img_b64  = image_to_base64(st.session_state['img'])
                        analysis = analyze_opg(img_b64, patient_context=patient_context or None,
                                               mode=mode_str)
                        st.session_state.update({
                            'analysis':        analysis,
                            'a_patient_name':  patient_name,
                            'a_patient_id':    patient_id,
                            'a_dentist_name':  dentist_name,
                            'a_clinic_name':   clinic_name,
                        })
                        st.success("Analysis complete!")
                    except Exception as exc:
                        st.error(f"Analysis failed: {exc}")

        # ── Results ───────────────────────────────────────────────────────────
        if 'analysis' in st.session_state:
            st.markdown("---")
            st.subheader("📋 Radiographic Report")
            with st.container(border=True):
                st.markdown(st.session_state['analysis'])

            st.markdown("""
<div class='disclaimer-box'>
⚕️ <b>Clinical Disclaimer:</b> This AI-assisted report is for decision-support only.
All findings must be correlated with clinical examination and verified by the treating clinician.
</div>
""", unsafe_allow_html=True)

            st.markdown("---")
            ac1, ac2, ac3 = st.columns(3)

            # PDF download
            img_bytes_pdf = get_image_bytes(st.session_state['img'])
            pdf_bytes = generate_pdf_report(
                st.session_state['analysis'],
                st.session_state.get('a_patient_name', ''),
                st.session_state.get('a_patient_id',   ''),
                st.session_state.get('a_dentist_name', ''),
                st.session_state.get('a_clinic_name',  ''),
                img_bytes=img_bytes_pdf,
            )
            fname_base = (
                f"OPG_{st.session_state.get('a_patient_name') or 'patient'}_"
                f"{datetime.now().strftime('%Y%m%d_%H%M')}"
            )
            ac1.download_button(
                "📄 Download PDF Report",
                data=pdf_bytes,
                file_name=f"{fname_base}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

            # Save to history
            with ac2:
                notes = st.text_input("Case notes", placeholder="Optional notes…", key="case_notes")
                if st.button("💾 Save to History", use_container_width=True):
                    img_save_path = str(
                        CASES_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{st.session_state['filename']}"
                    )
                    with open(img_save_path, 'wb') as f:
                        f.write(st.session_state['file_bytes'])
                    cid = save_case(
                        st.session_state.get('a_patient_name', ''),
                        st.session_state.get('a_patient_id',   ''),
                        st.session_state.get('a_dentist_name', ''),
                        st.session_state.get('a_clinic_name',  ''),
                        img_save_path,
                        st.session_state['analysis'],
                        notes=notes,
                    )
                    st.success(f"Saved — Case ID: {cid}")

            # Plain-text download
            ac3.download_button(
                "📝 Download as Text",
                data=st.session_state['analysis'],
                file_name=f"{fname_base}.txt",
                mime="text/plain",
                use_container_width=True,
            )


def tab_history():
    st.subheader("Case History")
    query = st.text_input("🔍 Search", placeholder="Patient name, ID, dentist…")
    cases = search_cases(query) if query else get_all_cases()

    if not cases:
        st.info("No cases found. Analyse an OPG and save it to build your history.")
        return

    st.caption(f"{len(cases)} case(s) found")

    for case in cases:
        cid, pname, pid, dname, cname, date, img_path, analysis, _, notes, _ = case
        label = f"🦷  {pname or 'Unknown Patient'}  —  {date}  |  ID: {pid or '—'}  |  Dr. {dname or '—'}"

        with st.expander(label):
            col_img, col_txt = st.columns([1, 2])

            with col_img:
                if img_path and Path(img_path).exists():
                    with open(img_path, 'rb') as f:
                        raw = f.read()
                    img, _ = load_image(raw, Path(img_path).name)
                    st.image(img, use_column_width=True)
                else:
                    st.caption("Image file not found")
                if notes:
                    st.markdown(f"**Notes:** {notes}")

            with col_txt:
                preview = analysis[:1200] + '…' if len(analysis) > 1200 else analysis
                st.markdown(preview)

                dl1, dl2, dl3 = st.columns(3)

                # Re-generate PDF
                if img_path and Path(img_path).exists():
                    with open(img_path, 'rb') as f:
                        raw_pdf = f.read()
                    img_pdf, _ = load_image(raw_pdf, Path(img_path).name)
                    pdf = generate_pdf_report(
                        analysis, pname, pid, dname, cname, get_image_bytes(img_pdf)
                    )
                    dl1.download_button(
                        "📄 PDF",
                        data=pdf,
                        file_name=f"OPG_{pname}_{date[:10]}.pdf",
                        mime="application/pdf",
                        key=f"pdf_{cid}",
                        use_container_width=True,
                    )

                dl2.download_button(
                    "📝 Text",
                    data=analysis,
                    file_name=f"OPG_{pname}_{date[:10]}.txt",
                    mime="text/plain",
                    key=f"txt_{cid}",
                    use_container_width=True,
                )

                if dl3.button("🗑️ Delete", key=f"del_{cid}", use_container_width=True):
                    delete_case(cid)
                    st.rerun()


def tab_compare():
    st.subheader("Compare Cases Side-by-Side")
    all_cases = get_all_cases()

    if len(all_cases) < 2:
        st.info("You need at least 2 saved cases to use the comparison view.")
        return

    opts = {f"{c[1] or 'Unknown'}  —  {c[5]}  (Case #{c[0]})": c[0] for c in all_cases}
    keys = list(opts.keys())

    sel1, sel2 = st.columns(2)
    k1 = sel1.selectbox("Case 1", keys,            key="cmp1")
    k2 = sel2.selectbox("Case 2", keys, index=1,   key="cmp2")

    if st.button("Compare →", type="primary"):
        c1 = get_case(opts[k1])
        c2 = get_case(opts[k2])

        col1, col2 = st.columns(2)
        for col, case in [(col1, c1), (col2, c2)]:
            _, pname, pid, dname, _, date, img_path, analysis, _, notes, _ = case
            with col:
                st.markdown(f"**{pname or 'Unknown'}** — {date}")
                st.caption(f"ID: {pid or '—'} | Dr. {dname or '—'}")
                if img_path and Path(img_path).exists():
                    with open(img_path, 'rb') as f:
                        raw = f.read()
                    img, _ = load_image(raw, Path(img_path).name)
                    st.image(img, use_column_width=True)
                with st.container(border=True):
                    st.markdown(analysis)


def tab_feedback():
    from knowledge_base import (
        save_feedback, get_all_feedback, get_feedback_stats, build_learning_context
    )
    from database import get_all_cases

    st.subheader("🧠 Dentist Feedback & AI Learning")
    st.caption(
        "Review AI findings case by case. Every correction is learned and applied to future analyses."
    )

    # ── Stats banner ──────────────────────────────────────────────────────────
    stats = get_feedback_stats()
    if stats:
        sc1, sc2, sc3, sc4, sc5 = st.columns(5)
        sc1.metric("Total Reviewed",   stats["total"])
        sc2.metric("Confirmed ✓",      stats["confirmed"])
        sc3.metric("Corrected",        stats["corrected"])
        sc4.metric("Missed (added)",   stats["missed"])
        sc5.metric("False Positives",  stats["false_positive"])
        acc = stats["accuracy_pct"]
        color = "green" if acc >= 80 else "orange" if acc >= 60 else "red"
        st.markdown(f"**AI confirmed accuracy: :{color}[{acc}%]** — improves as you review more cases.")
        st.markdown("---")

    # ── Current learned patterns ──────────────────────────────────────────────
    lc = build_learning_context()
    if lc:
        with st.expander("📚 What the AI has learned so far"):
            st.markdown(lc)
        st.markdown("---")

    # ── Case selector ─────────────────────────────────────────────────────────
    cases = get_all_cases()
    if not cases:
        st.info("No cases yet. Run an analysis first, then return here to give feedback.")
        return

    case_opts = {
        f"Case #{c[0]} — {c[1] or 'Unknown'} — {c[5]}": c[0]
        for c in cases
    }
    selected_label = st.selectbox("Select a case to review", list(case_opts.keys()))
    case_id = case_opts[selected_label]

    # Find the case
    case = next((c for c in cases if c[0] == case_id), None)
    if not case:
        return

    _, pname, pid, dname, cname, date, img_path, analysis, _, notes, _ = case

    col_img, col_analysis = st.columns([1, 2])
    with col_img:
        if img_path and Path(img_path).exists():
            with open(img_path, "rb") as f:
                raw = f.read()
            img, _ = load_image(raw, Path(img_path).name)
            st.image(img, use_column_width=True)
        st.caption(f"Patient: {pname} | {date}")

    with col_analysis:
        with st.container(border=True):
            st.markdown(analysis[:2000] + ("…" if len(analysis) > 2000 else ""))

    st.markdown("---")
    st.markdown("### Rate AI Findings for This Case")
    st.caption("Submit one row per finding you want to correct or confirm.")

    CATEGORIES = [
        "caries", "periapical", "periodontal_bone", "impacted_tooth",
        "restoration", "bone_quality", "tmj", "sinus", "calcification",
        "root_abnormality", "general",
    ]
    VERDICTS = {
        "confirmed":      "✅ Confirmed — AI was correct",
        "corrected":      "✏️ Corrected — AI was wrong, here is the right finding",
        "missed":         "➕ Missed — AI didn't report this, but it's present",
        "false_positive": "❌ False Positive — AI reported this, but it's NOT present",
    }

    with st.form(f"feedback_form_{case_id}", clear_on_submit=True):
        fb_col1, fb_col2, fb_col3 = st.columns([1, 1, 1])
        with fb_col1:
            category    = st.selectbox("Category", CATEGORIES)
            tooth_fdi   = st.text_input("Tooth (FDI)", placeholder="e.g. 36, 48, or leave blank")
        with fb_col2:
            verdict_key = st.selectbox("Verdict", list(VERDICTS.keys()),
                                       format_func=lambda k: VERDICTS[k])
            severity    = st.selectbox("Severity (your assessment)",
                                       ["", "mild", "moderate", "severe", "not applicable"])
        with fb_col3:
            ai_finding   = st.text_area("AI finding (copy from report)", height=80,
                                        placeholder="Paste the relevant sentence from the AI report")
            correct_find = st.text_area("Correct finding (if corrected/missed)", height=80,
                                        placeholder="Describe the correct clinical finding")

        fb_notes = st.text_input("Additional notes (optional)")
        submitted = st.form_submit_button("💾 Submit Feedback", type="primary", use_container_width=True)

        if submitted:
            if not ai_finding and verdict_key != "missed":
                st.warning("Please paste the AI finding you are rating.")
            else:
                save_feedback(
                    case_id=case_id,
                    category=category,
                    tooth_fdi=tooth_fdi.strip(),
                    ai_finding=ai_finding.strip(),
                    verdict=verdict_key,
                    correct_finding=correct_find.strip(),
                    severity=severity,
                    notes=fb_notes.strip(),
                )
                st.success(f"Feedback saved — AI will learn from this on next analysis.")

    # ── Feedback history for this case ────────────────────────────────────────
    all_fb = get_all_feedback()
    case_fb = [r for r in all_fb if r[1] == case_id]
    if case_fb:
        st.markdown(f"**{len(case_fb)} feedback entries for this case:**")
        for row in case_fb:
            _, _, cat, tooth, ai_f, verdict, correct_f, sev, fb_note, ts = row
            badge = {"confirmed": "✅", "corrected": "✏️",
                     "missed": "➕", "false_positive": "❌"}.get(verdict, "•")
            st.markdown(
                f"{badge} **{cat}** {f'[{tooth}]' if tooth else ''} — "
                f"_{verdict}_ {f'→ {correct_f}' if correct_f else ''}"
            )


def tab_image_tools():
    from image_tools import (
        parse_fdi_findings, create_finding_overlay,
        density_heatmap, create_multipanel_grid,
        quadrant_zoom, quadrant_options, brightness_profile,
    )

    st.subheader("🖼️ Advanced Image Analysis Tools")

    if 'img' not in st.session_state:
        st.info("Upload an OPG in the **Analyse OPG** tab first to use these tools.")
        return

    img = st.session_state['img']

    tool_tabs = st.tabs([
        "🎯 AI Finding Overlay",
        "🌡️ Bone Density Heatmap",
        "📊 Multi-Enhancement Grid",
        "🔍 Quadrant Zoom",
        "📈 Brightness Profile",
    ])

    # ── 1. AI Finding Overlay ─────────────────────────────────────────────────
    with tool_tabs[0]:
        st.markdown("**AI Finding Overlay** — colour-coded FDI markers parsed from the analysis report.")
        st.caption(
            "🔴 Urgent  🟠 Pathology  🟣 Impacted  🔵 Restoration  🟡 Monitor"
        )

        if 'analysis' not in st.session_state:
            st.warning("Run a **Full AI Analysis** first (Analyse OPG tab) to enable the finding overlay.")
        else:
            col_ov, col_ctrl = st.columns([3, 1])
            with col_ctrl:
                show_labels = st.checkbox("Show tooth labels", value=True, key="ov_labels")
                show_legend = st.checkbox("Show legend",       value=True, key="ov_legend")
                if st.button("🎨 Generate Overlay", type="primary", use_container_width=True, key="btn_overlay"):
                    with st.spinner("Parsing findings and rendering overlay…"):
                        findings = parse_fdi_findings(st.session_state['analysis'])
                        overlay_img = create_finding_overlay(
                            img, findings,
                            show_labels=show_labels,
                            show_legend=show_legend,
                        )
                        st.session_state['overlay_img']      = overlay_img
                        st.session_state['overlay_findings'] = findings

            with col_ov:
                if 'overlay_img' in st.session_state:
                    st.image(st.session_state['overlay_img'],
                             use_column_width=True, caption="AI Finding Overlay")
                    findings = st.session_state.get('overlay_findings', [])
                    if findings:
                        urgent = [f for f in findings if f['urgency'] == 'urgent']
                        if urgent:
                            st.error(f"⚠️ {len(urgent)} urgent finding(s): "
                                     f"{', '.join(f['tooth'] for f in urgent)}")
                        st.caption(f"{len(findings)} teeth with findings identified from report")
                    dl = get_image_bytes(st.session_state['overlay_img'])
                    st.download_button("⬇️ Download Overlay", data=dl,
                                       file_name="finding_overlay.jpg", mime="image/jpeg",
                                       key="dl_overlay")
                else:
                    st.image(img, use_column_width=True, caption="Upload will appear here after overlay")

    # ── 2. Bone Density Heatmap ───────────────────────────────────────────────
    with tool_tabs[1]:
        st.markdown("**Bone Density Heatmap** — CLAHE-enhanced false-colour density map.")
        st.caption("Hot (red/orange) = low density · Cool (blue/purple) = high density")

        col_hm, col_ctrl = st.columns([3, 1])
        with col_ctrl:
            alpha = st.slider("Heatmap opacity", 0.2, 0.9, 0.55, 0.05, key="hm_alpha")
            colormap_choice = st.selectbox(
                "Colormap", ["INFERNO", "JET", "HOT", "PLASMA", "VIRIDIS"], key="hm_cmap"
            )
            if st.button("🌡️ Generate Heatmap", type="primary", use_container_width=True, key="btn_heatmap"):
                with st.spinner("Computing density heatmap…"):
                    import cv2
                    cmap_map = {
                        "INFERNO": cv2.COLORMAP_INFERNO,
                        "JET":     cv2.COLORMAP_JET,
                        "HOT":     cv2.COLORMAP_HOT,
                        "PLASMA":  cv2.COLORMAP_PLASMA,
                        "VIRIDIS": cv2.COLORMAP_VIRIDIS,
                    }
                    hmap = density_heatmap(img, alpha=alpha, colormap=cmap_map[colormap_choice])
                    st.session_state['heatmap_img'] = hmap

        with col_hm:
            if 'heatmap_img' in st.session_state:
                st.image(st.session_state['heatmap_img'],
                         use_column_width=True, caption="Bone Density Heatmap")
                dl = get_image_bytes(st.session_state['heatmap_img'])
                st.download_button("⬇️ Download Heatmap", data=dl,
                                   file_name="density_heatmap.jpg", mime="image/jpeg",
                                   key="dl_heatmap")
            else:
                st.image(img, use_column_width=True, caption="Original OPG")

    # ── 3. Multi-Enhancement Grid ─────────────────────────────────────────────
    with tool_tabs[2]:
        st.markdown("**Multi-Enhancement Grid** — Original + 6 enhancement modes + Density Map in one view.")
        st.caption("Useful for quickly comparing how different processing modes reveal different features.")

        if st.button("📊 Generate Grid", type="primary", key="btn_grid"):
            with st.spinner("Rendering all 7 panels — please wait…"):
                grid = create_multipanel_grid(img, cols=3)
                st.session_state['grid_img'] = grid

        if 'grid_img' in st.session_state:
            st.image(st.session_state['grid_img'],
                     use_column_width=True, caption="7-Panel Enhancement Grid")
            dl = get_image_bytes(st.session_state['grid_img'])
            st.download_button("⬇️ Download Grid", data=dl,
                               file_name="enhancement_grid.jpg", mime="image/jpeg",
                               key="dl_grid")

    # ── 4. Quadrant Zoom ──────────────────────────────────────────────────────
    with tool_tabs[3]:
        st.markdown("**Quadrant Zoom** — magnified, enhanced crop of any jaw region or TMJ.")

        col_zq, col_ctrl = st.columns([3, 1])
        with col_ctrl:
            quad = st.selectbox("Region", quadrant_options(), key="qz_region")
            enh  = st.selectbox("Enhancement",
                                ["clahe", "contrast", "sharpen", "original", "edges"],
                                key="qz_enh")
            if st.button("🔍 Zoom In", type="primary", use_container_width=True, key="btn_zoom"):
                with st.spinner(f"Extracting {quad}…"):
                    zoomed = quadrant_zoom(img, quad, enhance=enh)
                    st.session_state['zoomed_img']   = zoomed
                    st.session_state['zoomed_label'] = quad

        with col_zq:
            if 'zoomed_img' in st.session_state:
                st.image(st.session_state['zoomed_img'],
                         use_column_width=True,
                         caption=st.session_state.get('zoomed_label', 'Zoomed region'))
                dl = get_image_bytes(st.session_state['zoomed_img'])
                label = st.session_state.get('zoomed_label', 'region').replace(' ', '_')[:30]
                st.download_button("⬇️ Download Zoom", data=dl,
                                   file_name=f"zoom_{label}.jpg", mime="image/jpeg",
                                   key="dl_zoom")
            else:
                st.image(img, use_column_width=True, caption="Original OPG")

    # ── 5. Brightness Profile ─────────────────────────────────────────────────
    with tool_tabs[4]:
        st.markdown("**Brightness Profile** — horizontal pixel-brightness scan as a bone density proxy.")
        st.caption(
            "X-axis = left → right position · Y-axis = mean pixel brightness (0 = black, 255 = white). "
            "Dips in the bone regions may indicate lucencies or reduced trabecular density."
        )

        col_ctrl, col_chart = st.columns([1, 3])
        with col_ctrl:
            region = st.selectbox(
                "Jaw region",
                ["full", "upper_jaw", "lower_jaw", "mandible"],
                format_func=lambda x: x.replace('_', ' ').title(),
                key="bp_region_sel",
            )
            if st.button("📈 Compute Profile", type="primary", use_container_width=True, key="btn_bp"):
                with st.spinner("Computing brightness profile…"):
                    x_pos, brightness = brightness_profile(img, region=region)
                    st.session_state['bp_x']      = x_pos
                    st.session_state['bp_y']      = brightness
                    st.session_state['bp_region'] = region

        with col_chart:
            if 'bp_x' in st.session_state:
                import pandas as pd
                df = pd.DataFrame({
                    "Mean Brightness": st.session_state['bp_y'],
                }, index=st.session_state['bp_x'])
                st.line_chart(df, height=320)
                y = st.session_state['bp_y']
                region_label = st.session_state.get('bp_region', 'full').replace('_', ' ').title()
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Region",  region_label)
                c2.metric("Min",     f"{y.min():.0f}")
                c3.metric("Max",     f"{y.max():.0f}")
                c4.metric("Mean",    f"{y.mean():.0f}")
            else:
                st.info("Select a region and click **Compute Profile**.")


def tab_about():
    st.subheader("About Dental OPG AI Assistant")
    st.markdown("""
### What This Tool Does
The **Dental OPG AI Assistant** uses Claude's vision AI to assist dental professionals in
analysing panoramic dental radiographs (OPGs). It delivers structured, section-by-section
radiographic assessments and generates downloadable PDF reports.

---

### Full Analysis Coverage

| Section | What is assessed |
|---|---|
| **Tooth Inventory** | Present, missing, impacted, partially erupted, supernumerary teeth (FDI) |
| **Restorations** | Fillings, crowns, bridges, implants, RCT, post/core |
| **Caries** | Location by surface, severity, confidence rating |
| **Periapical Pathology** | Lucencies, widening PDL, differential (granuloma/cyst/abscess) |
| **Periodontal Bone** | Level, pattern, severity, furcation involvement |
| **Cysts & Lesions** | Location, size, borders, differential list |
| **Root Abnormalities** | Dilacerations, resorption, fractures, hypercementosis |
| **Calcifications** | Pulp stones, sialoliths, carotid calcifications, tonsilloliths |
| **Maxillary Sinuses** | Bilateral: mucosal thickening, opacification, tooth–sinus relations |
| **Mandibular Canal** | Continuity, cortical integrity, proximity to wisdom teeth |
| **TMJ** | Condylar shape, symmetry, articular surface, joint space |
| **Bone Quality** | Trabecular pattern, cortical plate, density impression |
| **Developmental** | Root stages, crown anomalies, skeletal impression |
| **Recommendations** | Priority 1–3 treatment needs, additional imaging, referrals |

---

### Image Enhancement Modes

| Mode | Best for |
|---|---|
| **CLAHE** | Revealing fine trabecular detail and subtle lucencies |
| **Contrast** | Improving overall radiographic contrast |
| **Sharpen** | Accentuating margins and crown morphology |
| **Inverted** | Alternative viewing preference |
| **Edges** | Identifying cortical borders |

---

### ⚕️ Medical & Legal Disclaimer

> This tool is a **clinical decision-support system** only. It is not a medical device,
> has not been cleared by any regulatory body (FDA / CE / TGA), and must not be used
> as the sole basis for diagnosis or treatment planning. All AI-generated findings must
> be verified by a qualified dental clinician with full clinical context.

---

### AI Providers

| Provider | Model | Cost | Limit |
|---|---|---|---|
| **Google Gemini** (default) | Gemini 2.5 Flash | **Free** | 1,500 / day |
| **Anthropic Claude** | Claude Sonnet 4.6 | ~$0.02 / analysis | Pay as you go |

Get a free Gemini key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

---

### Technology Stack

| Component | Technology |
|---|---|
| AI Vision (free) | Google Gemini 2.5 Flash |
| AI Vision (paid) | Claude Sonnet 4.6 (Anthropic) |
| Web Interface | Streamlit |
| DICOM Support | pydicom |
| Image Processing | Pillow, OpenCV (CLAHE) |
| PDF Generation | ReportLab |
| Case Database | SQLite |
""")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    st.markdown("""
<div class="main-header">
    <h1>🦷 Dental OPG AI Assistant</h1>
    <p>AI-powered panoramic radiograph analysis &nbsp;·&nbsp; Clinical decision support for dental professionals</p>
</div>
""", unsafe_allow_html=True)

    sidebar()

    tabs = st.tabs(["🔬 Analyse OPG", "🖼️ Image Tools", "📁 Case History", "📊 Compare Cases", "🧠 Feedback & Learning", "ℹ️ About"])
    with tabs[0]: tab_analyze()
    with tabs[1]: tab_image_tools()
    with tabs[2]: tab_history()
    with tabs[3]: tab_compare()
    with tabs[4]: tab_feedback()
    with tabs[5]: tab_about()


if __name__ == "__main__":
    main()
