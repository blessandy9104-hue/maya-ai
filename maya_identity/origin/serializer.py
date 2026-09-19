"""Deterministic canonical serialization for Founder Origin records (8N-E).

Canonical form: UTF-8, LF line terminator, compact separators (',', ':'),
ensure_ascii=False, sort_keys=True at every level, trailing newline.
Records with identical logical content always produce identical bytes.
"""

from __future__ import annotations

import json

ENCODING = "utf-8"
LINE_TERMINATOR = "\n"
SEPARATORS = (",", ":")
ENSURE_ASCII = False
SORT_KEYS = True


def canonical_text(record: dict) -> str:
    return (
        json.dumps(
            record,
            sort_keys=SORT_KEYS,
            separators=SEPARATORS,
            ensure_ascii=ENSURE_ASCII,
        )
        + LINE_TERMINATOR
    )


def canonical_bytes(record: dict) -> bytes:
    return canonical_text(record).encode(ENCODING)