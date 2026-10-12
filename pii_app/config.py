"""
Configurable PII detection settings.

Detection is split across two engines (see pii_app/presidio_engine.py):
  - Presidio (presidio-analyzer) handles EMAIL, PHONE, PERSON, and the
    custom-registered structured categories below (AADHAAR, PAN,
    EMPLOYEE_ID, DATE_OF_BIRTH, PINCODE).
  - A small amount of our own heuristic code handles ADDRESS, which has
    no fixed shape Presidio's pattern mechanism can express.

CUSTOM_PATTERNS defines the structured categories Presidio doesn't ship
natively for India. Add, remove, or tweak patterns here without touching
detection logic elsewhere in the app.

Fields:
    label:       Category name used in reports and redaction placeholders.
    pattern:     Regex string (compiled by presidio_engine.py).
    confidence:  Base confidence (0-1) before any checksum validation.
                 AADHAAR and PAN are checksum/structure-validated in
                 checksums.py: a passing check raises the final score to
                 1.0; a failing check leaves it at this base score rather
                 than discarding the match (a redaction tool should err
                 toward flagging, not silently dropping, a candidate ID).
"""

CUSTOM_PATTERNS = {
    "EMAIL": {
        "label": "EMAIL",
        # Presidio's own built-in EmailRecognizer intermittently returns
        # zero matches on some real documents in this app's test corpus
        # (reproducible, cause not pinned down — likely an edge case in
        # its regex-timeout wrapper) despite the same pattern matching
        # fine standalone. Using our own well-tested pattern here avoids
        # depending on that recognizer at all.
        "pattern": r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
        "confidence": 0.9,
    },
    "AADHAAR": {
        "label": "AADHAAR",
        # 12 digits, optionally grouped as 4-4-4 with spaces or hyphens.
        # Verhoeff-checksum-validated in checksums.py.
        "pattern": r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b",
        "confidence": 0.50,
    },
    "PAN": {
        "label": "PAN",
        # Indian PAN: 5 letters, 4 digits, 1 letter. 4th-character
        # holder-type code validated in checksums.py.
        "pattern": r"\b[A-Z]{5}\d{4}[A-Z]\b",
        "confidence": 0.55,
    },
    "EMPLOYEE_ID": {
        "label": "EMPLOYEE_ID",
        # Common internal ID conventions: EMP-1234, EMP12345, E-00123, etc.
        "pattern": r"\b(?:EMP|EID)[\-_]?\d{3,8}\b",
        "confidence": 0.85,
    },
    "DATE_OF_BIRTH": {
        "label": "DATE_OF_BIRTH",
        # dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy — base score is deliberately
        # low; Presidio's context-aware enhancer (see presidio_engine.py)
        # boosts it when a DOB keyword is nearby, since a bare date could
        # be any date at all.
        "pattern": r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}\b",
        "confidence": 0.20,
    },
    "PINCODE": {
        "label": "PINCODE",
        "pattern": r"\b\d{6}\b",
        "confidence": 0.55,
    },
}

# Context words that let Presidio's context-aware enhancer boost a bare
# date match's score when one appears nearby — turning a low base score
# (any date) into a high one (specifically a date of birth). See
# presidio_engine.py for how this plugs into the recognizer.
#
# Presidio's context matcher checks "is this context word a substring of
# one of the (single-token, lemmatized) words surrounding the match" —
# so these must be single tokens, not phrases. "date of birth" as a whole
# phrase would never match against individual surrounding tokens like
# "birth"; "birth" alone does.
DOB_KEYWORDS = ["dob", "birth", "born", "bday"]

# Context words that boost PHONE_NUMBER confidence when nearby. Presidio's
# context matcher drops any surrounding word spaCy treats as a stopword
# before comparing — "call" is in spaCy's default English stopword list,
# so it's omitted here; it would never match anyway.
PHONE_CONTEXT_KEYWORDS = ["phone", "contact", "mobile", "cell", "telephone", "number", "reach", "reachable"]

# Indian mobile numbers only, for Presidio's built-in PhoneRecognizer
# (backed by the `phonenumbers` library, which validates real number
# structure — not just digit count — per region).
PHONE_SUPPORTED_REGIONS = ("IN",)

# Keywords that, when found on the same line as a PINCODE/number run,
# help flag an ADDRESS block. Simple heuristic, not a full NLP parse.
ADDRESS_KEYWORDS = ["address", "residing at", "resident of", "flat", "street", "road", "sector"]

# spaCy model used for PERSON name detection. "en_core_web_sm" is small and
# fast but prone to tagging title-cased business jargon (headers, product
# names, acronyms) as PERSON — see PERSON_NAME_STOPWORDS below for the
# mitigation. For higher-precision production use, swap in
# "en_core_web_lg" or "en_core_web_trf" (larger download, slower, more
# accurate) without changing any detection code.
SPACY_MODEL = "en_core_web_sm"

# Confidence assigned to spaCy PERSON detections.
PERSON_CONFIDENCE = 0.70

# A raw spaCy PERSON entity is only accepted as a name if it survives
# _looks_like_person_name() in pii_detection.py:
#   - 2 to PERSON_MAX_WORDS words (full names only — filters single-word
#     noise like "TPRM", "Workflow", "Trigger" outright)
#   - every word is alphabetic title-case (allows apostrophes/hyphens) or
#     a short (<=3 letter) all-caps token treated as initials ("KC", "DK")
#   - no word, once lowercased and stripped of a trailing possessive "'s",
#     appears in PERSON_NAME_STOPWORDS
# This is a precision-over-recall tradeoff appropriate for jargon-heavy
# corporate documents; see README "Limitations" for what it costs.
PERSON_MAX_WORDS = 4

# Domain/business nouns that are commonly Title-Cased in headers and
# templates and get misread as proper nouns by a small NER model. Extend
# this list per-document-set rather than relying on the model alone.
PERSON_NAME_STOPWORDS = {
    "tier", "workflow", "workflows", "trigger", "vendor", "vendors",
    "change", "type", "created", "description", "key", "diligence",
    "questionnaire", "questionnaires", "artificial", "intelligence",
    "cloud", "apps", "group", "groups", "template", "templates",
    "background", "navigate", "appendix", "document", "revision",
    "composed", "email", "database", "metadata", "admin", "privacy",
    "shield", "procurement", "finance", "it", "risk", "management",
    "tprm", "cadence", "ironclad", "optiv", "launching", "due",
    "disclosures", "approved", "contains", "reassessment", "custom",
    "no", "timeline", "custom field", "reviewed", "status", "stage",
    "process", "policy", "section", "overview", "summary", "scope",
    "purpose", "objective", "attachment", "attachments", "confidential",
}

# Minimum confidence a detection must have to be shown/redacted by default.
DEFAULT_MIN_CONFIDENCE = 0.5

# Which PII categories are active by default. UI can toggle these.
DEFAULT_ENABLED_CATEGORIES = {
    "PERSON": True,
    "EMAIL": True,
    "PHONE": True,
    "AADHAAR": True,
    "PAN": True,
    "EMPLOYEE_ID": True,
    "DATE_OF_BIRTH": True,
    "ADDRESS": True,
    "PINCODE": False,  # noisy on its own; off by default, address heuristic uses it
}
