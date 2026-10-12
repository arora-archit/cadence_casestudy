from pii_app.pii_detection import detect_pii


def _labels(matches):
    return {m.label for m in matches}


def test_detects_email():
    text = "Contact me at jane.doe@example.com for details."
    matches = detect_pii(text)
    emails = [m for m in matches if m.label == "EMAIL"]
    assert len(emails) == 1
    assert emails[0].text == "jane.doe@example.com"


def test_detects_phone_number():
    text = "Call +91 9876543210 for support."
    matches = detect_pii(text)
    phones = [m for m in matches if m.label == "PHONE"]
    assert len(phones) == 1


def test_detects_pan():
    text = "PAN: ABCDE1234F on file."
    matches = detect_pii(text)
    pans = [m for m in matches if m.label == "PAN"]
    assert len(pans) == 1
    assert pans[0].text == "ABCDE1234F"


def test_detects_aadhaar():
    text = "Aadhaar: 2345 6789 1023"
    matches = detect_pii(text)
    aadhaar = [m for m in matches if m.label == "AADHAAR"]
    assert len(aadhaar) == 1


def test_detects_employee_id():
    text = "Employee ID: EMP-20481 reporting to manager."
    matches = detect_pii(text)
    emp_ids = [m for m in matches if m.label == "EMPLOYEE_ID"]
    assert len(emp_ids) == 1
    assert emp_ids[0].text == "EMP-20481"


def test_date_of_birth_requires_keyword_context():
    with_keyword = "Date of Birth: 14/03/1991"
    without_keyword = "Meeting scheduled for 14/03/1991"

    matches_with = detect_pii(with_keyword)
    matches_without = detect_pii(without_keyword)

    assert "DATE_OF_BIRTH" in _labels(matches_with)
    assert "DATE_OF_BIRTH" not in _labels(matches_without)


def test_detects_address_after_keyword():
    text = "Address: 14 Lakeview Residency, Sector 21, Gurugram, Haryana, 122018"
    matches = detect_pii(text)
    addresses = [m for m in matches if m.label == "ADDRESS"]
    assert len(addresses) == 1
    assert "Lakeview Residency" in addresses[0].text


def test_detects_person_name_via_spacy():
    text = "This record belongs to Rohan Mehta, reviewed by Priya Nair."
    matches = detect_pii(text)
    persons = [m for m in matches if m.label == "PERSON"]
    assert len(persons) >= 1


def test_disabled_category_is_not_detected():
    text = "Email: jane.doe@example.com"
    enabled = {"EMAIL": False, "PERSON": False, "PHONE": False, "AADHAAR": False,
               "PAN": False, "EMPLOYEE_ID": False, "DATE_OF_BIRTH": False,
               "ADDRESS": False, "PINCODE": False}
    matches = detect_pii(text, enabled_categories=enabled)
    assert matches == []


def test_business_jargon_is_not_detected_as_person():
    text = (
        "Navigate to the TPRM Workflow and review the Vendor Tier. "
        "The Trigger Type: Approved status launches the Change Workflow."
    )
    matches = detect_pii(text)
    person_texts = {m.text for m in matches if m.label == "PERSON"}
    assert person_texts == set()


def test_multiline_spacy_entity_is_split_into_separate_names():
    # Table-cell text extracted without sentence punctuation can fuse
    # several names (and trailing header text) into one spaCy entity;
    # the detector must split on line breaks and validate each piece.
    text = "Daniela Figueroa\nBridgett Gatewood\nVendor Risk Management Group"
    matches = detect_pii(text)
    person_texts = {m.text for m in matches if m.label == "PERSON"}
    assert person_texts == {"Daniela Figueroa", "Bridgett Gatewood"}
    assert "Vendor Risk Management Group" not in person_texts


def test_address_keyword_substring_inside_another_word_is_ignored():
    # "address" is a substring of "addressee" — must not match as a
    # keyword hit with no real address content behind it.
    text = (
        "This email and any attachments are intended solely for the "
        "addressee and may contain confidential material."
    )
    matches = detect_pii(text)
    assert [m for m in matches if m.label == "ADDRESS"] == []


def test_overlapping_matches_are_resolved_without_duplication():
    # A PAN-like pattern should not also partially trip other patterns
    # in a way that produces overlapping spans in the final result.
    text = "PAN: ABCDE1234F, Email: abcde1234f@example.com"
    matches = detect_pii(text)
    spans = [(m.start, m.end) for m in matches]
    for i, (s1, e1) in enumerate(spans):
        for j, (s2, e2) in enumerate(spans):
            if i != j:
                assert not (s1 < e2 and s2 < e1), "Detected spans overlap"
