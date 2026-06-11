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
FRED_PAYLOAD = ROOT / "outputs" / "fred_us_pivot" / "fred_pivot_payload.json"
TRANSACTION_ORDER = ["NN", "N1N", "N111N", "N112N", "N1121N", "N211N"]
FRED_US_NONFINANCIAL_CODES = [
    "BOGZ1LM152010005A",
    "BOGZ1LM102010005A",
    "BOGZ1LM112010005A",
    "BOGZ1LM312010095A",
    "BOGZ1LM212010095A",
    "BOGZ1LM795013865A",
]
FRED_US_REAL_ESTATE_CODES = [
    "BOGZ1LM155035005A",
    "BOGZ1LM105035005A",
    "BOGZ1LM115035005A",
]
NORMAL_STATUS = {"A"}


def parse_number(value: str) -> float | None:
    if value in {"", "."}:
        return None
    return float(value)


def validate_fred_codes(required_codes: list[str]) -> dict[str, dict[str, object]]:
    fred_payload = json.loads(FRED_PAYLOAD.read_text(encoding="utf-8"))
    fred_rows = {row["코드"]: row for row in fred_payload["pivot_rows"]}
    missing_codes = [code for code in required_codes if code not in fred_rows]
    if missing_codes:
        raise KeyError(f"FRED payload is missing required series: {', '.join(missing_codes)}")
    return fred_rows


def build_fred_sum_row(
    *,
    years: list[str],
    required_codes: list[str],
    transaction_code: str,
    transaction_name: str,
    highlight: str,
    sort_transaction_code: str,
    sort_after_us_nn: int,
) -> tuple[dict[str, object], dict[str, int]]:
    """Build a FRED-derived row whose workbook cells will be SUM formulas."""
    fred_rows = validate_fred_codes(required_codes)
    pivot_row: dict[str, object] = {
        "트랜잭션코드": transaction_code,
        "트랜잭션명": transaction_name,
        "나라": "United States",
        "화폐단위": "USD",
        "행강조": highlight,
        "FRED합산코드": required_codes,
        "정렬트랜잭션코드": sort_transaction_code,
        "정렬미국보강순서": sort_after_us_nn,
    }
    missing_years = 0
    for year in years:
        values = [fred_rows[code].get(year) for code in required_codes]
        if any(value is None for value in values):
            missing_years += 1
        pivot_row[year] = None

    return pivot_row, {"결측연도수": missing_years, "합산코드수": len(required_codes)}


def sort_key(row: dict[str, object], tx_order: dict[str, int]) -> tuple[int, str, str, int]:
    tx_code = str(row.get("정렬트랜잭션코드") or row["트랜잭션코드"])
    return (
        tx_order.get(tx_code, 999),
        str(row["나라"]),
        str(row["화폐단위"]),
        int(row.get("정렬미국보강순서", 0)),
    )


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
    raw_us_nn_exists = any(row["트랜잭션코드"] == "NN" and row["나라"] == "United States" for row in pivot_rows)
    fred_us_summary = {
        "보강행수": 0,
        "부동산보강행수": 0,
        "결측연도수": 0,
        "부동산결측연도수": 0,
        "합산코드수": len(FRED_US_NONFINANCIAL_CODES),
        "부동산합산코드수": len(FRED_US_REAL_ESTATE_CODES),
    }
    if not raw_us_nn_exists:
        fred_us_row, fred_us_nn_summary = build_fred_sum_row(
            years=years,
            required_codes=FRED_US_NONFINANCIAL_CODES,
            transaction_code="NN",
            transaction_name=code_map.get("NN", "Total non-financial assets, net"),
            highlight="FRED_US_NONFINANCIAL_NN",
            sort_transaction_code="NN",
            sort_after_us_nn=0,
        )
        fred_real_estate_row, fred_real_estate_summary = build_fred_sum_row(
            years=years,
            required_codes=FRED_US_REAL_ESTATE_CODES,
            transaction_code="",
            transaction_name="Real estate at market value (FRED 3-series sum)",
            highlight="FRED_US_REAL_ESTATE",
            sort_transaction_code="NN",
            sort_after_us_nn=1,
        )
        pivot_rows.extend([fred_us_row, fred_real_estate_row])
        fred_us_summary.update(
            {
                "보강행수": 1,
                "부동산보강행수": 1,
                "결측연도수": fred_us_nn_summary["결측연도수"],
                "부동산결측연도수": fred_real_estate_summary["결측연도수"],
            }
        )
    pivot_rows.sort(key=lambda row: sort_key(row, tx_order))
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
            "FRED_US_NN_보강행수": fred_us_summary["보강행수"],
            "FRED_US_NN_결측연도수": fred_us_summary["결측연도수"],
            "FRED_US_NN_원천코드": "|".join(FRED_US_NONFINANCIAL_CODES),
            "FRED_US_NN_값정의": "미국 NN은 OECD 결측 보강용으로 요청된 FRED 비금융자산 6개 코드를 엑셀 SUM 수식으로 합산, 단위는 백만 USD",
            "FRED_US_부동산_보강행수": fred_us_summary["부동산보강행수"],
            "FRED_US_부동산_결측연도수": fred_us_summary["부동산결측연도수"],
            "FRED_US_부동산_원천코드": "|".join(FRED_US_REAL_ESTATE_CODES),
            "FRED_US_부동산_값정의": "미국 부동산 항목은 요청에서 제외했던 FRED 부동산 3개 코드를 엑셀 SUM 수식으로 합산, 단위는 백만 USD",
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
