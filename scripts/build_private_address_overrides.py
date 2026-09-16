#!/usr/bin/env python3
"""Build a private hashed address-to-district override file.

Raw addresses remain only in the reviewer-supplied CSV. The generated JSON
contains SHA-256 hashes of normalized addresses and controlled district codes;
it must still remain mode 0600 and outside Git.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import unicodedata
from pathlib import Path


DISTRICT_CODES = {
    "CW", "EST", "SOU", "WC", "KC", "KWT", "SSP", "WTS", "YTM",
    "IS", "KUI", "NOR", "SK", "ST", "TP", "TW", "TM", "YL",
}
SKIP_CODES = {"", "N/A", "NA", "UNKNOWN", "SKIP"}


def normalize_address(value: str) -> str:
    return "".join(
        character
        for character in value.strip().upper()
        if not character.isspace()
        and not unicodedata.category(character).startswith("P")
    )


def read_decisions(path: Path) -> list[tuple[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise ValueError("Review CSV is empty")

    decisions: list[tuple[str, str]] = []
    if len(rows[0]) >= 2:
        for row in rows[1:]:
            if not row or not any(cell.strip() for cell in row):
                continue
            decisions.append((row[0].strip(), row[1].strip().upper()))
        return decisions

    # Accept the spreadsheet export seen in production, where the complete
    # comma-separated row was itself quoted as one CSV cell. Splitting from the
    # right preserves commas embedded in the address.
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        if "," not in row[0]:
            raise ValueError("Single-column review row has no district separator")
        address, code = row[0].rsplit(",", 1)
        decisions.append((address.strip(), code.strip().upper()))
    return decisions


def read_review_addresses(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        if not rows.fieldnames or "address_text_private" not in rows.fieldnames:
            raise ValueError("Review export has no address_text_private column")
        return [
            row["address_text_private"].strip()
            for row in rows
            if row.get("address_text_private", "").strip()
        ]


def build_payload(
    decisions: list[tuple[str, str]], review_addresses: list[str] | None = None
) -> tuple[dict, dict]:
    normalized_decisions = []
    skipped = 0
    for address, code in decisions:
        if code in SKIP_CODES:
            skipped += 1
            continue
        if code not in DISTRICT_CODES:
            raise ValueError(f"Unsupported district code: {code!r}")
        normalized = normalize_address(address.strip().strip('"'))
        if not normalized:
            raise ValueError("A reviewed address becomes empty after normalization")
        normalized_decisions.append((normalized, code))

    matched_conflicts = 0
    unmatched_review_addresses = 0
    if review_addresses is not None:
        full_address_decisions = []
        for address in review_addresses:
            normalized = normalize_address(address)
            matched_codes = {
                code
                for reviewed_fragment, code in normalized_decisions
                if reviewed_fragment in normalized
            }
            if len(matched_codes) == 1:
                full_address_decisions.append((normalized, matched_codes.pop()))
            elif len(matched_codes) > 1:
                matched_conflicts += 1
            else:
                unmatched_review_addresses += 1
    else:
        full_address_decisions = normalized_decisions

    overrides: dict[str, str] = {}
    for normalized, code in full_address_decisions:
        address_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        previous = overrides.setdefault(address_hash, code)
        if previous != code:
            raise ValueError("One normalized address was assigned conflicting districts")

    rows = [
        {"address_hash": address_hash, "district_code": overrides[address_hash]}
        for address_hash in sorted(overrides)
    ]
    payload = {
        "version": 1,
        "normalization": "uppercase; remove Unicode whitespace and punctuation; SHA-256",
        "overrides": rows,
    }
    summary = {
        "reviewed_rows": len(decisions),
        "installed_overrides": len(rows),
        "skipped_rows": skipped,
        "conflicting_full_addresses": matched_conflicts,
        "unmatched_full_addresses": unmatched_review_addresses,
    }
    return payload, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--review-export",
        type=Path,
        help="Original private review export used to hash complete stored addresses",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    payload, summary = build_payload(
        read_decisions(args.input),
        read_review_addresses(args.review_export) if args.review_export else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.chmod(temporary, 0o600)
    temporary.replace(args.output)
    os.chmod(args.output, 0o600)
    summary.update({"output": str(args.output), "mode": "0o600"})
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
