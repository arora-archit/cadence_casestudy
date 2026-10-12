"""Simulated downstream LLM processing step.

This module demonstrates a "safe handoff" pattern: only redacted text is
passed in, never raw extracted text and never the original PII. There is
NO network call here and no external API key — the "analysis" is a local,
deterministic stand-in so the demo stays fully offline.

In a real deployment, this is where you would call an LLM API, but the
input contract (redacted text only) stays the same.
"""

import re


def simulate_llm_processing(redacted_text: str) -> dict:
    """Pretend to run an LLM-based analysis over already-redacted text.

    Returns a small summary so the UI can show that downstream processing
    received only placeholder tokens, never raw PII.
    """
    placeholder_tokens = re.findall(r"\[[A-Z_]+_\d+\]", redacted_text)
    word_count = len(redacted_text.split())

    return {
        "input_contains_raw_pii": False,
        "placeholder_tokens_seen": sorted(set(placeholder_tokens)),
        "placeholder_token_count": len(placeholder_tokens),
        "word_count": word_count,
        "simulated_summary": (
            "This document was processed with "
            f"{len(placeholder_tokens)} redaction placeholder(s) in place of "
            "sensitive data. No external API call was made; this is a local "
            "simulation confirming the downstream step never saw raw PII."
        ),
    }
