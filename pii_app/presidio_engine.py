"""Builds the Presidio AnalyzerEngine used for structured + NER detection.

Why Presidio instead of hand-rolled regex for everything: it gives us
(1) a real phone-number validator (the `phonenumbers` library — actual
number-plan validity, not just "10 digits starting with 6-9"), (2) a
context-aware scorer that boosts confidence when a relevant keyword sits
near a match instead of a hand-written character-offset window, and (3) a
single, extensible recognizer-registry architecture instead of a growing
pile of bespoke detector functions. We still plug in custom recognizers
for the categories Presidio has no India-specific support for (AADHAAR,
PAN, EMPLOYEE_ID, DATE_OF_BIRTH, PINCODE), now backed by real validation
(checksums.py) rather than regex shape alone.

The engine is expensive to build (loads the spaCy model) so it's cached
process-wide, mirroring how pii_detection.py already caches the raw
spaCy pipeline.
"""

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import PhoneRecognizer

from pii_app.checksums import is_structurally_valid_pan, verhoeff_checksum_is_valid
from pii_app.config import (
    CUSTOM_PATTERNS,
    DOB_KEYWORDS,
    PHONE_CONTEXT_KEYWORDS,
    PHONE_SUPPORTED_REGIONS,
    SPACY_MODEL,
)

_ANALYZER_CACHE = {}

# Entities this app actually wants out of Presidio's analyze() call. We
# pass this explicitly rather than taking Presidio's full default entity
# list, which includes many out-of-scope US/UK/crypto recognizers (SSN,
# NHS, IBAN, credit card, URL, ...) that would otherwise fire noisily on
# arbitrary digit runs.
SUPPORTED_ENTITIES = [
    "EMAIL",
    "PHONE_NUMBER",
    "PERSON",
    "AADHAAR",
    "PAN",
    "EMPLOYEE_ID",
    "DATE_OF_BIRTH",
    "PINCODE",
]


class CustomEmailRecognizer(PatternRecognizer):
    """Custom email recognizer — see CUSTOM_PATTERNS["EMAIL"] in config.py
    for why this replaces Presidio's built-in EmailRecognizer.
    """

    def __init__(self):
        spec = CUSTOM_PATTERNS["EMAIL"]
        pattern = Pattern(name="email_format", regex=spec["pattern"], score=spec["confidence"])
        super().__init__(supported_entity="EMAIL", patterns=[pattern], context=["email"])


class AadhaarRecognizer(PatternRecognizer):
    """Aadhaar number recognizer with real Verhoeff checksum validation.

    A checksum pass raises the score to 1.0 (Presidio's MAX_SCORE); a
    checksum fail leaves the score at the pattern's base confidence
    rather than discarding the match — see config.py's CUSTOM_PATTERNS
    docstring for why we don't treat a failed checksum as a hard reject.
    """

    def __init__(self):
        spec = CUSTOM_PATTERNS["AADHAAR"]
        pattern = Pattern(name="aadhaar_12_digit", regex=spec["pattern"], score=spec["confidence"])
        super().__init__(
            supported_entity="AADHAAR",
            patterns=[pattern],
            context=["aadhaar", "uid", "aadhar"],
        )

    def validate_result(self, pattern_text: str):
        digits_only = "".join(ch for ch in pattern_text if ch.isdigit())
        if len(digits_only) != 12:
            return None
        return True if verhoeff_checksum_is_valid(digits_only) else None


class PanRecognizer(PatternRecognizer):
    """Indian PAN recognizer with structural holder-type validation
    (PAN's 4th character; see checksums.is_structurally_valid_pan).
    """

    def __init__(self):
        spec = CUSTOM_PATTERNS["PAN"]
        pattern = Pattern(name="pan_format", regex=spec["pattern"], score=spec["confidence"])
        super().__init__(
            supported_entity="PAN",
            patterns=[pattern],
            context=["pan", "permanent account number"],
        )

    def validate_result(self, pattern_text: str):
        return True if is_structurally_valid_pan(pattern_text) else None


class EmployeeIdRecognizer(PatternRecognizer):
    def __init__(self):
        spec = CUSTOM_PATTERNS["EMPLOYEE_ID"]
        pattern = Pattern(name="employee_id_format", regex=spec["pattern"], score=spec["confidence"])
        super().__init__(
            supported_entity="EMPLOYEE_ID",
            patterns=[pattern],
            context=["employee", "emp id", "staff id"],
        )


class DateOfBirthRecognizer(PatternRecognizer):
    """Any dd/mm/yyyy-shaped date, scored low by default and boosted by
    Presidio's context-aware enhancer only when a DOB keyword is nearby
    (see DOB_KEYWORDS in config.py) — otherwise it's just "a date."
    """

    def __init__(self):
        spec = CUSTOM_PATTERNS["DATE_OF_BIRTH"]
        pattern = Pattern(name="date_shape", regex=spec["pattern"], score=spec["confidence"])
        super().__init__(
            supported_entity="DATE_OF_BIRTH",
            patterns=[pattern],
            context=DOB_KEYWORDS,
        )


class PincodeRecognizer(PatternRecognizer):
    def __init__(self):
        spec = CUSTOM_PATTERNS["PINCODE"]
        pattern = Pattern(name="pincode_6_digit", regex=spec["pattern"], score=spec["confidence"])
        super().__init__(supported_entity="PINCODE", patterns=[pattern])


def build_analyzer() -> AnalyzerEngine:
    nlp_configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": SPACY_MODEL}],
    }
    nlp_engine = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()

    analyzer = AnalyzerEngine(
        nlp_engine=nlp_engine,
        supported_languages=["en"],
        default_score_threshold=0.0,  # we filter by confidence ourselves, later in the pipeline
    )

    # Narrow the default PhoneRecognizer to Indian numbers only and add
    # phone-specific context words, instead of the library-wide default
    # region set (US/GB/DE/FR/IL/IN/CA/BR), which is noisy for this use case.
    analyzer.registry.remove_recognizer("PhoneRecognizer")
    analyzer.registry.remove_recognizer("EmailRecognizer")
    analyzer.registry.add_recognizer(
        PhoneRecognizer(supported_regions=PHONE_SUPPORTED_REGIONS, context=PHONE_CONTEXT_KEYWORDS)
    )

    for recognizer_cls in (
        CustomEmailRecognizer,
        AadhaarRecognizer,
        PanRecognizer,
        EmployeeIdRecognizer,
        DateOfBirthRecognizer,
        PincodeRecognizer,
    ):
        analyzer.registry.add_recognizer(recognizer_cls())

    return analyzer


def get_analyzer() -> AnalyzerEngine:
    """Return the process-wide cached AnalyzerEngine, building it on first use."""
    if "analyzer" not in _ANALYZER_CACHE:
        _ANALYZER_CACHE["analyzer"] = build_analyzer()
    return _ANALYZER_CACHE["analyzer"]
