"""Redact detected PII from text using character offsets.

Matches are replaced with placeholders like [PERSON_1], [EMAIL_1], each
category numbered independently in order of appearance. Replacement is
done in a single right-to-left pass over sorted, non-overlapping offsets so
earlier offsets stay valid as later ones are substituted.
"""

from dataclasses import dataclass


@dataclass
class RedactionEntry:
    label: str
    placeholder: str
    original_text: str
    start: int
    end: int
    confidence: float
    source: str


def redact_text(text: str, matches: list) -> tuple:
    """Return (redacted_text, list[RedactionEntry]).

    `matches` must be PIIMatch objects with non-overlapping spans (as
    produced by pii_detection.detect_pii). Matches are assumed sorted by
    start offset; this function sorts defensively regardless.
    """
    ordered = sorted(matches, key=lambda m: m.start)

    counters = {}
    entries = []
    for match in ordered:
        counters[match.label] = counters.get(match.label, 0) + 1
        placeholder = f"[{match.label}_{counters[match.label]}]"
        entries.append(
            RedactionEntry(
                label=match.label,
                placeholder=placeholder,
                original_text=match.text,
                start=match.start,
                end=match.end,
                confidence=match.confidence,
                source=match.source,
            )
        )

    redacted_text = text
    for entry in reversed(entries):
        redacted_text = (
            redacted_text[: entry.start] + entry.placeholder + redacted_text[entry.end :]
        )

    return redacted_text, entries
