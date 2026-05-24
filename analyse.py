"""
Dental OPG Analyser — standalone command-line prototype
Usage:
    python analyse.py                        # prompts for image path
    python analyse.py path/to/opg.jpg        # direct path
    python analyse.py path/to/opg.dcm --quick  # fast screening mode
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# ── API key ───────────────────────────────────────────────────────────────────
def ensure_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print("\n" + "="*60)
        print("  Anthropic API key not found in environment.")
        print("  Get yours at: https://console.anthropic.com/settings/keys")
        print("="*60)
        key = input("  Paste your API key: ").strip()
        if not key:
            print("No key provided. Exiting.")
            sys.exit(1)
        os.environ["ANTHROPIC_API_KEY"] = key
    return key


# ── Pretty console output ─────────────────────────────────────────────────────
def banner(text, char="="):
    width = 60
    print("\n" + char * width)
    print(f"  {text}")
    print(char * width)

def section(text):
    print(f"\n{'─'*60}")
    print(f"  {text}")
    print('─'*60)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Dental OPG AI Analyser")
    parser.add_argument("image", nargs="?", help="Path to OPG image (DICOM or JPEG/PNG)")
    parser.add_argument("--quick", action="store_true", help="Quick screening mode (faster, less detail)")
    parser.add_argument("--no-pdf", action="store_true", help="Skip PDF report generation")
    parser.add_argument("--out", default="", help="Output folder for PDF (default: same folder as image)")
    args = parser.parse_args()

    banner("🦷  Dental OPG AI Assistant  —  Local Prototype")

    # ── API key ───────────────────────────────────────────────────────────────
    ensure_api_key()

    # ── Image path ────────────────────────────────────────────────────────────
    image_path = args.image
    if not image_path:
        print("\nDrag & drop your OPG file here, or type the full path:")
        image_path = input("  Image path: ").strip().strip('"')

    image_path = Path(image_path)
    if not image_path.exists():
        print(f"\nFile not found: {image_path}")
        sys.exit(1)

    print(f"\n  File   : {image_path.name}")
    print(f"  Size   : {image_path.stat().st_size / 1024:.1f} KB")

    # ── Patient info (optional) ───────────────────────────────────────────────
    section("Patient Information  (press Enter to skip each field)")
    patient_name = input("  Patient name   : ").strip() or "Unknown"
    patient_id   = input("  Patient ID     : ").strip() or "—"
    dentist_name = input("  Dentist name   : ").strip() or "—"
    clinic_name  = input("  Clinic / practice: ").strip() or "—"
    context      = input("  Clinical notes (optional): ").strip() or None

    # ── Load image ────────────────────────────────────────────────────────────
    section("Loading Image")
    from image_handler import load_image, image_to_base64, get_image_bytes, enhance_image

    with open(image_path, "rb") as f:
        raw = f.read()

    try:
        img, dicom_meta = load_image(raw, image_path.name)
        print(f"  Loaded  : {img.width} x {img.height} px")
        if dicom_meta:
            print(f"  Format  : DICOM")
            for attr in ("PatientName", "StudyDate", "Modality", "Manufacturer"):
                if hasattr(dicom_meta, attr):
                    print(f"  {attr:12}: {getattr(dicom_meta, attr)}")
        else:
            print(f"  Format  : {image_path.suffix.upper().lstrip('.')}")
    except Exception as e:
        print(f"  ERROR loading image: {e}")
        sys.exit(1)

    # ── Run analysis ──────────────────────────────────────────────────────────
    mode_label = "Quick Screening" if args.quick else "Full Analysis"
    section(f"Running AI Analysis  [{mode_label}]")
    print("  Sending to Claude — this takes 20–40 seconds for full analysis...")

    from analyzer import analyze_opg
    try:
        img_b64  = image_to_base64(img)
        mode_str = "quick" if args.quick else "full"
        analysis = analyze_opg(img_b64, patient_context=context, mode=mode_str)
    except Exception as e:
        print(f"\n  ERROR during analysis: {e}")
        sys.exit(1)

    # ── Print results ─────────────────────────────────────────────────────────
    banner("Analysis Report", char="=")
    print()

    # Strip markdown for clean console output
    import re
    clean = re.sub(r'\*\*(.*?)\*\*', r'\1', analysis)   # bold
    clean = re.sub(r'\*(.*?)\*',     r'\1', clean)       # italic
    clean = re.sub(r'^#{1,3} ',      '',    clean, flags=re.MULTILINE)  # headers
    print(clean)

    # ── Save PDF ──────────────────────────────────────────────────────────────
    if not args.no_pdf:
        section("Generating PDF Report")
        from report_generator import generate_pdf_report

        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name  = re.sub(r'[^a-zA-Z0-9_-]', '_', patient_name)
        pdf_name   = f"OPG_{safe_name}_{timestamp}.pdf"

        out_dir = Path(args.out) if args.out else image_path.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = out_dir / pdf_name

        try:
            pdf_bytes = generate_pdf_report(
                analysis,
                patient_name=patient_name,
                patient_id=patient_id,
                dentist_name=dentist_name,
                clinic_name=clinic_name,
                img_bytes=get_image_bytes(img),
            )
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)
            print(f"  PDF saved : {pdf_path}")
            print(f"  Size      : {len(pdf_bytes) / 1024:.0f} KB")

            # Auto-open PDF
            try:
                os.startfile(str(pdf_path))
                print("  Opening PDF...")
            except Exception:
                pass

        except Exception as e:
            print(f"  PDF generation failed: {e}")

    # ── Save to case history ──────────────────────────────────────────────────
    section("Saving to Case History")
    from database import init_db, save_case
    init_db()
    case_id = save_case(
        patient_name, patient_id, dentist_name, clinic_name,
        str(image_path), analysis,
        notes=f"CLI analysis [{mode_label}]",
    )
    print(f"  Case saved  : ID #{case_id}")

    banner("Done ✓", char="=")
    print(f"  Patient : {patient_name}")
    print(f"  Mode    : {mode_label}")
    if not args.no_pdf:
        print(f"  Report  : {pdf_path}")
    print()


if __name__ == "__main__":
    main()
