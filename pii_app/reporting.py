"""Build JSON-serializable reports summarizing detection/redaction results."""

import json
from datetime import datetime, timezone


def build_file_report(filename: str, extraction_meta: dict, entries: list) -> dict:
    """Report for a single processed file."""
    counts_by_category = {}
    for entry in entries:
        counts_by_category[entry.label] = counts_by_category.get(entry.label, 0) + 1

    return {
        "filename": filename,
        "extraction": extraction_meta,
        "pii_summary": {
            "total_detections": len(entries),
            "counts_by_category": counts_by_category,
        },
        "detections": [
            {
                "placeholder": e.placeholder,
                "category": e.label,
                "confidence": round(e.confidence, 2),
                "source": e.source,
                "start": e.start,
                "end": e.end,
                "original_text": e.original_text,
            }
            for e in entries
        ],
    }


def build_batch_report(file_reports: list) -> dict:
    """Combine per-file reports into one overall report."""
    total_detections = sum(r["pii_summary"]["total_detections"] for r in file_reports)

    combined_counts = {}
    for report in file_reports:
        for category, count in report["pii_summary"]["counts_by_category"].items():
            combined_counts[category] = combined_counts.get(category, 0) + count

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files_processed": len(file_reports),
        "total_detections": total_detections,
        "counts_by_category": combined_counts,
        "files": file_reports,
    }


def report_to_json(report: dict) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False)
