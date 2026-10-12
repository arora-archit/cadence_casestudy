"""File validation for uploaded evidence artifacts."""

from dataclasses import dataclass

ALLOWED_EXTENSIONS = {"pdf", "docx", "pptx", "txt", "png", "jpg", "jpeg"}
MAX_FILE_SIZE_MB = 25


@dataclass
class ValidationResult:
    is_valid: bool
    reason: str = ""
    extension: str = ""


def validate_file(filename: str, size_bytes: int) -> ValidationResult:
    """Check a file's extension and size before processing.

    This is a lightweight gate, not a security sandbox: it only guards the
    pipeline against unsupported formats and oversized uploads.
    """
    if "." not in filename:
        return ValidationResult(False, "File has no extension.")

    extension = filename.rsplit(".", 1)[-1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        return ValidationResult(
            False,
            f"Unsupported file type '.{extension}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
            extension,
        )

    size_mb = size_bytes / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        return ValidationResult(
            False,
            f"File too large ({size_mb:.1f} MB). Limit is {MAX_FILE_SIZE_MB} MB.",
            extension,
        )

    if size_bytes == 0:
        return ValidationResult(False, "File is empty.", extension)

    return ValidationResult(True, "", extension)
