from __future__ import annotations

from fieldforge_contracts import GuardrailDecision

from fieldforge_guardrails.patterns import (
    PII_PATTERNS,
    SECRET_PATTERNS,
    find_injection_spans,
    find_matches,
)

ALLOWED_CONTENT_TYPES = {"text/plain", "text/markdown", "application/pdf"}
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}
MAX_UPLOAD_BYTES_DEFAULT = 10 * 1024 * 1024
MAX_QUERY_CHARS = 2000


def validate_upload(
    filename: str,
    content_type: str,
    size_bytes: int,
    max_upload_bytes: int = MAX_UPLOAD_BYTES_DEFAULT,
) -> GuardrailDecision:
    """Input rail: file-type validation, size limits, filename sanitization.

    Runs before any parsing touches the file content (threat-model row 8).
    """
    if "/" in filename or "\\" in filename or filename.startswith("."):
        return GuardrailDecision(
            rail="input.upload_validation",
            passed=False,
            reason=f"unsafe filename: {filename!r}",
        )
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS or content_type not in ALLOWED_CONTENT_TYPES:
        return GuardrailDecision(
            rail="input.upload_validation",
            passed=False,
            reason=f"unsupported file type: filename={filename!r} content_type={content_type!r}",
        )
    if size_bytes > max_upload_bytes:
        return GuardrailDecision(
            rail="input.upload_validation",
            passed=False,
            reason=f"file too large: {size_bytes} bytes > {max_upload_bytes} limit",
        )
    return GuardrailDecision(rail="input.upload_validation", passed=True)


def scan_query_text(question: str, max_chars: int = MAX_QUERY_CHARS) -> list[GuardrailDecision]:
    """Input rails applied to the user's question: size limit, injection pattern scan,
    PII/secret detection (a user should not be paste-leaking secrets into a query either).
    """
    decisions: list[GuardrailDecision] = []

    if len(question) > max_chars:
        decisions.append(
            GuardrailDecision(
                rail="input.size_limit",
                passed=False,
                reason=f"query length {len(question)} exceeds max {max_chars}",
            )
        )
        return decisions  # don't scan an oversized payload further
    decisions.append(GuardrailDecision(rail="input.size_limit", passed=True))

    injection_spans = find_injection_spans(question)
    decisions.append(
        GuardrailDecision(
            rail="input.injection_scan",
            passed=not injection_spans,
            reason="injection pattern detected in query" if injection_spans else None,
            flagged_spans=injection_spans,
        )
    )

    secret_hits = find_matches(question, SECRET_PATTERNS)
    pii_hits = find_matches(question, PII_PATTERNS)
    decisions.append(
        GuardrailDecision(
            rail="input.pii_secret_scan",
            passed=not (secret_hits or pii_hits),
            reason=f"detected: {secret_hits + pii_hits}" if (secret_hits or pii_hits) else None,
            flagged_spans=secret_hits + pii_hits,
        )
    )
    return decisions
