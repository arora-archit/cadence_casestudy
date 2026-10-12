"""
PII Detection & Redaction Web Application
==========================================

Streamlit front-end for a consulting case study demo. Uploads evidence
artifacts (PDF/DOCX/PPTX/TXT/PNG/JPG), extracts text, detects PII with
regex + spaCy, redacts it with offset-accurate placeholders, and shows a
results dashboard with downloadable redacted text and JSON report.

Run with: streamlit run app.py
"""

import streamlit as st

from pii_app.config import DEFAULT_ENABLED_CATEGORIES
from pii_app.file_validation import validate_file
from pii_app.llm_simulation import simulate_llm_processing
from pii_app.pii_detection import detect_pii
from pii_app.redaction import redact_text
from pii_app.reporting import build_batch_report, build_file_report, report_to_json
from pii_app.text_extraction import extract_text

st.set_page_config(page_title="PII Detection & Redaction", page_icon="🛡️", layout="wide")


@st.cache_resource(show_spinner="Loading spaCy model...")
def _warm_spacy():
    from pii_app.pii_detection import get_nlp

    return get_nlp()


def process_file(uploaded_file, enabled_categories: dict) -> dict:
    """Run the full pipeline for one uploaded file. Returns a result dict."""
    file_bytes = uploaded_file.getvalue()
    validation = validate_file(uploaded_file.name, len(file_bytes))

    if not validation.is_valid:
        return {"filename": uploaded_file.name, "error": validation.reason}

    extraction = extract_text(uploaded_file.name, file_bytes)
    matches = detect_pii(extraction.text, enabled_categories)
    redacted_text, entries = redact_text(extraction.text, matches)

    extraction_meta = {
        "extension": validation.extension,
        "characters_extracted": len(extraction.text),
        "used_ocr": extraction.used_ocr,
        "pages_or_slides": extraction.pages_or_slides,
        "warnings": extraction.warnings,
    }
    file_report = build_file_report(uploaded_file.name, extraction_meta, entries)

    return {
        "filename": uploaded_file.name,
        "error": None,
        "extracted_text": extraction.text,
        "redacted_text": redacted_text,
        "entries": entries,
        "extraction_meta": extraction_meta,
        "file_report": file_report,
    }


def render_sidebar() -> dict:
    st.sidebar.header("Detection settings")
    st.sidebar.caption("Toggle which PII categories to detect and redact.")

    enabled = {}
    for category, default_on in DEFAULT_ENABLED_CATEGORIES.items():
        enabled[category] = st.sidebar.checkbox(category, value=default_on)

    st.sidebar.divider()
    st.sidebar.caption(
        "Patterns are defined in `pii_app/config.py` — edit regexes there "
        "to adapt detection to new document formats."
    )
    return enabled


def render_file_result(result: dict):
    if result["error"]:
        st.error(f"**{result['filename']}**: {result['error']}")
        return

    entries = result["entries"]
    meta = result["extraction_meta"]

    st.subheader(result["filename"])
    cols = st.columns(4)
    cols[0].metric("Characters extracted", meta["characters_extracted"])
    cols[1].metric("PII detections", len(entries))
    cols[2].metric("OCR used", "Yes" if meta["used_ocr"] else "No")
    cols[3].metric("Pages / slides", meta["pages_or_slides"])

    if meta["warnings"]:
        for w in meta["warnings"]:
            st.warning(w)

    tabs = st.tabs(
        ["Extracted text", "Detected PII", "Redacted text", "Safe LLM demo", "JSON report"]
    )

    with tabs[0]:
        st.text_area(
            "Raw extracted text", result["extracted_text"], height=300,
            key=f"extracted_{result['filename']}",
        )

    with tabs[1]:
        if not entries:
            st.info("No PII detected with the current settings.")
        else:
            counts = result["file_report"]["pii_summary"]["counts_by_category"]
            st.write("**Summary by category:**", counts)
            table_rows = [
                {
                    "Placeholder": e.placeholder,
                    "Category": e.label,
                    "Original text": e.original_text,
                    "Confidence": round(e.confidence, 2),
                    "Source": e.source,
                    "Start": e.start,
                    "End": e.end,
                }
                for e in entries
            ]
            st.dataframe(table_rows, use_container_width=True)

    with tabs[2]:
        st.text_area(
            "Redacted text (placeholders in place of PII)",
            result["redacted_text"], height=300,
            key=f"redacted_{result['filename']}",
        )
        st.download_button(
            "Download redacted text",
            data=result["redacted_text"],
            file_name=f"{result['filename']}.redacted.txt",
            mime="text/plain",
            key=f"dl_text_{result['filename']}",
        )

    with tabs[3]:
        st.caption(
            "This simulates a downstream LLM call that receives ONLY the "
            "redacted text below — never the raw extracted text, and no "
            "external API is called in this demo."
        )
        llm_result = simulate_llm_processing(result["redacted_text"])
        st.json(llm_result)

    with tabs[4]:
        report_json = report_to_json(result["file_report"])
        st.code(report_json, language="json")
        st.download_button(
            "Download JSON report",
            data=report_json,
            file_name=f"{result['filename']}.report.json",
            mime="application/json",
            key=f"dl_json_{result['filename']}",
        )


def main():
    st.title("🛡️ PII Detection & Redaction")
    st.caption(
        "Upload evidence artifacts, detect personally identifiable information, "
        "and produce redacted text safe for downstream processing. "
        "All processing is local — nothing is sent to external services."
    )

    enabled_categories = render_sidebar()

    uploaded_files = st.file_uploader(
        "Upload evidence artifacts",
        type=["pdf", "docx", "pptx", "txt", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )

    if not uploaded_files:
        st.info("Upload one or more files to begin. Supported: PDF, DOCX, PPTX, TXT, PNG, JPG.")
        with st.expander("Limitations & known trade-offs"):
            st.markdown(_LIMITATIONS_TEXT)
        return

    with st.spinner("Loading NLP model..."):
        _warm_spacy()

    results = []
    progress = st.progress(0.0, text="Processing files...")
    for i, uploaded_file in enumerate(uploaded_files):
        results.append(process_file(uploaded_file, enabled_categories))
        progress.progress((i + 1) / len(uploaded_files), text=f"Processed {uploaded_file.name}")
    progress.empty()

    valid_reports = [r["file_report"] for r in results if not r["error"]]
    if valid_reports:
        batch_report = build_batch_report(valid_reports)
        st.header("Summary across all files")
        cols = st.columns(3)
        cols[0].metric("Files processed", batch_report["files_processed"])
        cols[1].metric("Total PII detections", batch_report["total_detections"])
        cols[2].metric("Categories found", len(batch_report["counts_by_category"]))
        st.bar_chart(batch_report["counts_by_category"])

        st.download_button(
            "Download full batch JSON report",
            data=report_to_json(batch_report),
            file_name="pii_batch_report.json",
            mime="application/json",
        )

    st.divider()
    st.header("Per-file results")
    for result in results:
        render_file_result(result)
        st.divider()

    with st.expander("Limitations & known trade-offs"):
        st.markdown(_LIMITATIONS_TEXT)


_LIMITATIONS_TEXT = """
- **False positives**: 6-digit PIN codes, 12-digit Aadhaar-like numbers, and
  generic phone-length numbers can be flagged even when they aren't PII
  (e.g. order numbers, amounts). The PINCODE category is off by default
  for this reason.
- **False negatives**: Unusual name formats, nicknames, or names spaCy's
  small English model doesn't recognize (especially non-Western names)
  may be missed. Addresses use a keyword-proximity heuristic, not a true
  address parser, so unconventional formatting may be missed.
- **OCR accuracy**: Scanned PDFs and images depend on Tesseract OCR
  quality — low-resolution scans, skewed pages, or unusual fonts reduce
  both text extraction and downstream PII detection accuracy.
- **Confidence scores**: These reflect pattern reliability, not a
  statistical model — treat them as a triage aid, and have a human
  review flagged content before relying on redaction for compliance.
"""


if __name__ == "__main__":
    main()
