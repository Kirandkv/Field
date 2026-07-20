"""Regex pattern libraries backing the guardrail rails.

Deliberately simple, inspectable regexes rather than an ML classifier — slice 1 needs
guardrails to be auditable and testable without another model dependency. Expanding
these from real adversarial-eval findings is tracked in docs/ROADMAP.md (DOCS-010).
"""

from __future__ import annotations

import re

# Threat-model row 1/2: direct + indirect prompt injection, incl. instructions hidden
# inside ingested documents (e.g. "SYSTEM:" lines, "ignore previous instructions").
INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore (all|any|the)? ?previous instructions", re.IGNORECASE),
    re.compile(
        r"disregard (all|any|the)? ?(prior|previous|above) (instructions|context)", re.IGNORECASE
    ),
    re.compile(r"^\s*system\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"you (must|should) now (act|behave|respond) as", re.IGNORECASE),
    re.compile(r"reveal (your|the) (system prompt|instructions)", re.IGNORECASE),
    re.compile(r"do not (mention|disclose|reveal) (this|that) to the user", re.IGNORECASE),
    re.compile(r"\bjailbreak\b", re.IGNORECASE),
]

# Threat-model row 14: PII shapes.
PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "phone": re.compile(r"\b(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "ssn_like": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
}

# Threat-model row 14: secret shapes.
SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "generic_api_key": re.compile(r"\b(api|secret)[_-]?key\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"),
    "private_key_header": re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "bearer_token": re.compile(r"\bBearer\s+[A-Za-z0-9\-_.]{20,}\b"),
}


def find_matches(text: str, patterns: dict[str, re.Pattern[str]]) -> list[str]:
    hits: list[str] = []
    for name, pattern in patterns.items():
        if pattern.search(text):
            hits.append(name)
    return hits


def find_injection_spans(text: str) -> list[str]:
    spans: list[str] = []
    for pattern in INJECTION_PATTERNS:
        m = pattern.search(text)
        if m:
            spans.append(m.group(0))
    return spans
