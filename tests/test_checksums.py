from pii_app.checksums import (
    compute_verhoeff_checksum_digit,
    is_structurally_valid_pan,
    verhoeff_checksum_is_valid,
)


def test_verhoeff_rejects_tampered_digit():
    prefix = "23456789102"
    valid = prefix + compute_verhoeff_checksum_digit(prefix)
    assert verhoeff_checksum_is_valid(valid)

    tampered = valid[:-1] + str((int(valid[-1]) + 1) % 10)
    assert not verhoeff_checksum_is_valid(tampered)


def test_verhoeff_rejects_non_digit_input():
    assert not verhoeff_checksum_is_valid("12ab5678901")


def test_pan_structural_validation():
    assert is_structurally_valid_pan("ABCPE1234F")  # P = Individual
    assert is_structurally_valid_pan("ABCCE1234F")  # C = Company
    assert not is_structurally_valid_pan("ABCZE1234F")  # Z is not a holder-type code
    assert not is_structurally_valid_pan("TOOSHORT1")


def test_aadhaar_with_valid_checksum_scores_higher_than_invalid():
    from pii_app.pii_detection import detect_pii

    prefix = "234567891020"[:-1]
    valid_aadhaar = prefix + compute_verhoeff_checksum_digit(prefix)
    invalid_aadhaar = prefix + str((int(compute_verhoeff_checksum_digit(prefix)) + 1) % 10)

    valid_matches = [m for m in detect_pii(f"Aadhaar: {valid_aadhaar}") if m.label == "AADHAAR"]
    invalid_matches = [m for m in detect_pii(f"Aadhaar: {invalid_aadhaar}") if m.label == "AADHAAR"]

    assert len(valid_matches) == 1
    assert valid_matches[0].confidence == 1.0

    # An unverified-but-shape-matching Aadhaar is still surfaced for
    # review, just at a lower (non-verified) confidence than a checksum
    # pass — never silently dropped.
    assert len(invalid_matches) == 1
    assert invalid_matches[0].confidence < valid_matches[0].confidence
