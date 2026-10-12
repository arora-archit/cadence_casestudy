"""Real validation algorithms for government-issued ID formats.

These replace "looks like the right shape" with "is actually
well-formed": a Verhoeff checksum for Aadhaar (the same check digit
algorithm UIDAI uses), and PAN's structural holder-type rule. Both
only ever raise confidence on a pattern-matched candidate — they never
silently delete a detection, since a failed check could equally mean
"someone typo'd a real ID" as "this was never an ID," and a redaction
tool should err toward flagging, not hiding.
"""

_VERHOEFF_D_TABLE = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]

_VERHOEFF_P_TABLE = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def verhoeff_checksum_is_valid(digits: str) -> bool:
    """Validate a numeric string's last digit as a Verhoeff check digit.

    UIDAI uses this algorithm for the 12th (final) digit of every Aadhaar
    number, so a string that fails this check is either not an Aadhaar
    number at all, or has a typo/OCR error in it.
    """
    digits = digits.strip()
    if not digits.isdigit():
        return False

    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _VERHOEFF_D_TABLE[c][_VERHOEFF_P_TABLE[i % 8][int(ch)]]
    return c == 0


def compute_verhoeff_checksum_digit(digits_without_checksum: str) -> str:
    """Compute the Verhoeff check digit that should be appended to
    `digits_without_checksum` to make it pass `verhoeff_checksum_is_valid`.

    Used by sample_data/generate_samples.py to mint synthetic Aadhaar
    numbers that validate like real ones, for demo purposes only.
    """
    c = 0
    for i, ch in enumerate(reversed(digits_without_checksum)):
        c = _VERHOEFF_D_TABLE[c][_VERHOEFF_P_TABLE[(i + 1) % 8][int(ch)]]

    inv_table = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]
    return str(inv_table[c])


# Fourth character of a PAN encodes the holder type. A PAN whose 4th
# character isn't one of these is structurally invalid, regardless of
# whether the rest of the format matches.
_VALID_PAN_HOLDER_TYPE_CODES = set("ABCFGHJLPT")


def is_structurally_valid_pan(pan: str) -> bool:
    """Check PAN's 4th-character holder-type code (P=Individual,
    C=Company, H=HUF, F=Firm, A=AOP, T=Trust, B=BOI, L=Local Authority,
    J=Artificial Juridical Person, G=Government). PAN has no public
    check-digit algorithm, so this structural rule is the strongest
    validation available without a government lookup API.
    """
    pan = pan.strip().upper()
    if len(pan) != 10:
        return False
    return pan[3] in _VALID_PAN_HOLDER_TYPE_CODES
