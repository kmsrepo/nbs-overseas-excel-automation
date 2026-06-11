#!/usr/bin/env python3
"""Build OECD Table 9B non-financial assets pivot payload."""

from __future__ import annotations

import csv
import json
import pathlib
from collections import defaultdict


ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "overseas_source_collection" / "oecd_table9b_nonfinancial_assets"
OUT_DIR = ROOT / "outputs" / "oecd_table9b_pivot"
LONG_CSV = SOURCE_DIR / "oecd_비금융자산_대차대조표_2000_2025_현지통화_긴형식.csv"
LOG_CSV = SOURCE_DIR / "oecd_비금융자산_수집로그.csv"
TRANSACTION_ORDER = ["NN", "N1N", "N111N", "N112N", "N1121N", "N211N"]
NORMAL_STATUS = {"A"}


def parse_number(value: str) -> float | None:
    if value in {"", "."}:
        return None
    return float(value)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with LONG_CSV.open(newline="", encoding="utf-8-sig") as handle:
        raw_rows = list(csv.DictReader(handle))
    with LOG_CSV.open(newline="", encoding="utf-8-sig") as handle:
        log_row = next(csv.DictReader(handle))

    rows = [
        row
        for row in raw_rows
        if row["섹터코드"] == "S1"
        and row["단위코드"] == "XDC"
        and row["가격기준코드"] == "V"
        and row["변환코드"] == "N"
        and row["Transact코드"] in TRANSACTION_ORDER
    ]
    years = sorted({row["연도"] for row in rows}, key=int)
    tx_order = {code: index for index, code in enumerate(TRANSACTION_ORDER)}

    by_key_year: dict[tuple[str, str, str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    keys: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (row["Transact코드"], row["Transact명"], row["국가명"], row["통화"])
        by_key_year[key][row["연도"]] = row
        keys[key] = row

    pivot_rows = []
    notes = []
    for key in sorted(keys, key=lambda k: (tx_order.get(k[0], 999), k[2], k[3])):
        row0 = keys[key]
        pivot_row = {
            "트랜잭션코드": row0["Transact코드"],
            "트랜잭션명": row0["Transact명"],
            "나라": row0["국가명"],
            "화폐단위": row0["통화"],
        }
        for year in years:
            row = by_key_year[key].get(year)
            if row is None:
                pivot_row[year] = None
                continue
            value = parse_number(row["값"])
            pivot_row[year] = value
            if row["관측상태코드"] not in NORMAL_STATUS:
                notes.append(
                    {
                        "트랜잭션코드": row["Transact코드"],
                        "트랜잭션명": row["Transact명"],
                        "나라": row["국가명"],
                        "화폐단위": row["통화"],
                        "연도": year,
                        "값_백만현지통화": value,
                        "관측상태코드": row["관측상태코드"],
                        "관측상태명": row["관측상태명"],
                    }
                )
        pivot_rows.append(pivot_row)

    code_map = {row["Transact코드"]: row["Transact명"] for row in rows}
    payload = {
        "years": years,
        "pivot_rows": pivot_rows,
        "notes": notes,
        "codes": [{"트랜잭션코드": code, "트랜잭션명": code_map.get(code, "")} for code in TRANSACTION_ORDER],
        "summary": {
            "원천파일": str(LONG_CSV),
            "수집일시": log_row["수집일시"],
            "원자료주소": log_row["원자료주소"],
            "탐색기주소": log_row["탐색기주소"],
            "필터": "섹터=Total economy(S1), 단위=XDC National currency, 가격기준=Current prices(V), 변환=N",
            "값정의": "피벗 셀 값 = OECD OBS_VALUE, 단위는 백만 현지통화",
            "행수": len(pivot_rows),
            "비확정값_노트수": len(notes),
            "국가수": len({row["나라"] for row in pivot_rows}),
            "트랜잭션코드수": len(TRANSACTION_ORDER),
        },
    }
    payload_path = OUT_DIR / "oecd_pivot_payload.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"rows={len(pivot_rows)}")
    print(f"notes={len(notes)}")
    print(f"payload={payload_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
