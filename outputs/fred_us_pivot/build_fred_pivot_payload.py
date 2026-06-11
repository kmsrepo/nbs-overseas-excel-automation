#!/usr/bin/env python3
"""Build FRED pivot payload from normalized long CSV."""

from __future__ import annotations

import csv
import json
import pathlib
from collections import defaultdict


ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "overseas_source_collection" / "fred_us"
OUT_DIR = ROOT / "outputs" / "fred_us_pivot"
LONG_CSV = SOURCE_DIR / "fred_미국_2000_2025_긴형식.csv"
LOG_CSV = SOURCE_DIR / "fred_미국_수집로그.csv"
SERIES_ORDER = [
    "BOGZ1LM152010005A",
    "BOGZ1LM102010005A",
    "BOGZ1LM112010005A",
    "BOGZ1LM312010095A",
    "BOGZ1LM212010095A",
    "BOGZ1LM795013865A",
    "BOGZ1LM155035005A",
    "BOGZ1LM105035005A",
    "BOGZ1LM115035005A",
]


def parse_number(value: str) -> float | None:
    if value in {"", "."}:
        return None
    return float(value)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with LONG_CSV.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    with LOG_CSV.open(newline="", encoding="utf-8-sig") as handle:
        log_rows = list(csv.DictReader(handle))

    years = sorted({row["연도"] for row in rows}, key=int)
    by_code: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    metadata: dict[str, dict[str, str]] = {}
    for row in rows:
        by_code[row["코드"]][row["연도"]] = row
        metadata.setdefault(row["코드"], row)

    pivot_rows = []
    for code in SERIES_ORDER:
        meta = metadata[code]
        pivot_row = {
            "코드": code,
            "코드항목명": meta["항목명"],
            "단위": meta["단위"],
            "빈도": meta["빈도"],
        }
        for year in years:
            pivot_row[year] = parse_number(by_code.get(code, {}).get(year, {}).get("값", ""))
        pivot_rows.append(pivot_row)

    first_row = rows[0]
    payload = {
        "years": years,
        "pivot_rows": pivot_rows,
        "summary": {
            "원천파일": str(LONG_CSV),
            "수집로그": str(LOG_CSV),
            "수집일시": first_row["수집일시"],
            "출처기관": first_row["출처기관"],
            "데이터베이스": first_row["데이터베이스"],
            "행수": len(pivot_rows),
            "연도수": len(years),
            "코드순서": "|".join(SERIES_ORDER),
        },
        "collection_log": log_rows,
    }
    payload_path = OUT_DIR / "fred_pivot_payload.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"rows={len(pivot_rows)}")
    print(f"years={min(years)}-{max(years)}")
    print(f"payload={payload_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
