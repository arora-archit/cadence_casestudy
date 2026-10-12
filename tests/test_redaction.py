from pii_app.pii_detection import PIIMatch, detect_pii
from pii_app.redaction import redact_text


def test_redacts_single_match_with_placeholder():
    text = "Contact jane.doe@example.com now."
    matches = [PIIMatch("EMAIL", 8, 28, "jane.doe@example.com", 0.95, "regex")]

    redacted, entries = redact_text(text, matches)

    assert redacted == "Contact [EMAIL_1] now."
    assert len(entries) == 1
    assert entries[0].placeholder == "[EMAIL_1]"
    assert entries[0].original_text == "jane.doe@example.com"


def test_redacts_multiple_matches_same_category_numbered_in_order():
    text = "a@example.com and b@example.com"
    matches = [
        PIIMatch("EMAIL", 0, 13, "a@example.com", 0.95, "regex"),
        PIIMatch("EMAIL", 18, 32, "b@example.com", 0.95, "regex"),
    ]

    redacted, entries = redact_text(text, matches)

    assert redacted == "[EMAIL_1] and [EMAIL_2]"
    assert entries[0].placeholder == "[EMAIL_1]"
    assert entries[1].placeholder == "[EMAIL_2]"


def test_redaction_preserves_surrounding_text_exactly():
    text = "Employee EMP-1234 lives at an undisclosed address."
    matches = [PIIMatch("EMPLOYEE_ID", 9, 17, "EMP-1234", 0.85, "regex")]

    redacted, _ = redact_text(text, matches)

    assert redacted == "Employee [EMPLOYEE_ID_1] lives at an undisclosed address."


def test_redaction_with_no_matches_returns_identical_text():
    text = "Nothing sensitive here."
    redacted, entries = redact_text(text, [])

    assert redacted == text
    assert entries == []


def test_end_to_end_detection_and_redaction_removes_raw_pii():
    text = "Email: jane.doe@example.com, PAN: ABCDE1234F"
    matches = detect_pii(text)
    redacted, entries = redact_text(text, matches)

    assert "jane.doe@example.com" not in redacted
    assert "ABCDE1234F" not in redacted
    assert len(entries) == len(matches)
