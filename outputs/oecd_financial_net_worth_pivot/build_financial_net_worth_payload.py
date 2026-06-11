#!/usr/bin/env python3
"""Build OECD financial net worth pivot payload."""

from __future__ import annotations

import csv
import json
import pathlib
from collections import defaultdict


ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "overseas_source_collection" / "oecd_financial_net_worth"
ABS_SOURCE_DIR = ROOT / "overseas_source_collection" / "abs_520410_national_balance_sheet"
OUT_DIR = ROOT / "outputs" / "oecd_financial_net_worth_pivot"
LONG_CSV = SOURCE_DIR / "oecd_financial_net_worth_lbf90nc_2007_2025_장형.csv"
LOG_CSV = SOURCE_DIR / "oecd_financial_net_worth_lbf90nc_수집로그.csv"
ABS_LONG_CSV = ABS_SOURCE_DIR / "abs_520410_순금융자산_2007_2025.csv"
ABS_LOG_CSV = ABS_SOURCE_DIR / "abs_520410_수집로그.csv"
NORMAL_STATUS = {"A"}


def parse_number(value: str) -> float | None:
    if value in {"", "."}:
        return None
    return float(value)


def load_abs_row(years: list[str]) -> tuple[dict[str, object] | None, dict[str, str] | None]:
    if not ABS_LONG_CSV.exists():
        return None, None
    with ABS_LONG_CSV.open(newline="", encoding="utf-8-sig") as handle:
        abs_rows = list(csv.DictReader(handle))
    if not abs_rows:
        return None, None
    abs_by_year = {row["연도"]: row for row in abs_rows}
    pivot_row: dict[str, object] = {
        "나라": "Australia (ABS 520410)",
        "국가코드": "AUS_ABS",
        "화폐단위": "AUD",
        "지표코드": "LBF90NC",
        "새지표코드": "ABS520410_NET_FINANCIAL_WORTH",
        "지표명": "Net financial worth derived from ABS 5204.0 Table 10",
        "단위": "백만 현지통화",
        "행강조": "ABS_520410",
    }
    for year in years:
        row = abs_by_year.get(year)
        pivot_row[year] = parse_number(row["순금융자산_백만AUD"]) if row else None
    abs_log = None
    if ABS_LOG_CSV.exists():
        with ABS_LOG_CSV.open(newline="", encoding="utf-8-sig") as handle:
            abs_log_rows = list(csv.DictReader(handle))
        abs_log = abs_log_rows[0] if abs_log_rows else None
    return pivot_row, abs_log


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with LONG_CSV.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    with LOG_CSV.open(newline="", encoding="utf-8-sig") as handle:
        log_rows = list(csv.DictReader(handle))
    log_row = log_rows[0]

    years = sorted({row["연도"] for row in rows}, key=int)
    by_country_year: dict[tuple[str, str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    countries: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (row["국가코드"], row["국가명"], row["통화"])
        by_country_year[key][row["연도"]] = row
        countries[key] = row

    pivot_rows = []
    notes = []
    for key in sorted(countries, key=lambda k: (k[1], k[0], k[2])):
        row0 = countries[key]
        pivot_row = {
            "나라": row0["국가명"],
            "국가코드": row0["국가코드"],
            "화폐단위": row0["통화"],
            "지표코드": "LBF90NC",
            "새지표코드": row0["지표코드"],
            "지표명": row0["지표명"],
            "단위": "백만 현지통화",
        }
        for year in years:
            row = by_country_year[key].get(year)
            if row is None:
                pivot_row[year] = None
                continue
            value = parse_number(row["값_백만현지통화"])
            pivot_row[year] = value
            if row["관측상태코드"] not in NORMAL_STATUS:
                notes.append(
                    {
                        "나라": row["국가명"],
                        "국가코드": row["국가코드"],
                        "화폐단위": row["통화"],
                        "연도": year,
                        "값_백만현지통화": value,
                        "관측상태코드": row["관측상태코드"],
                        "관측상태명": row["관측상태명"],
                        "지표코드": "LBF90NC",
                        "새지표코드": row["지표코드"],
                        "지표명": row["지표명"],
                    }
                )
        pivot_rows.append(pivot_row)

    abs_row, abs_log = load_abs_row(years)
    if abs_row:
        pivot_rows.append(abs_row)
        pivot_rows.sort(key=lambda row: (str(row["나라"]).replace(" (ABS 520410)", ""), str(row["나라"]), str(row["화폐단위"])))

    payload = {
        "years": years,
        "pivot_rows": pivot_rows,
        "notes": notes,
        "summary": {
            "원천파일": str(LONG_CSV),
            "수집로그": str(LOG_CSV),
            "수집일시": log_row["수집일시"],
            "데이터셋": log_row["데이터셋"],
            "원자료주소": log_row["원자료주소"],
            "탐색기주소": log_row["탐색기주소"],
            "지표": "LBF90NC / BF90 Net financial worth",
            "필터": "전체 경제주체 S1, Financial net worth BF90, XDC National currency, UNIT_MULT=6",
            "값정의": "피벗 셀 값 = OECD OBS_VALUE, 단위는 백만 현지통화",
            "행수": len(pivot_rows),
            "연도수": len(years),
            "메모수": len(notes),
            "ABS_520410_보강행수": 1 if abs_row else 0,
            "ABS_520410_원천파일": str(ABS_LONG_CSV) if abs_row else "",
            "ABS_520410_수집로그": str(ABS_LOG_CSV) if abs_row else "",
            "ABS_520410_원자료주소": abs_log.get("원자료주소", "") if abs_log else "",
            "ABS_520410_값정의": "A2421138R Financial assets with the rest of the world - A2421145L Liabilities to the rest of the world, billion AUD * 1000",
        },
        "collection_log": log_rows,
    }
    payload_path = OUT_DIR / "financial_net_worth_pivot_payload.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"rows={len(pivot_rows)}")
    print(f"notes={len(notes)}")
    print(f"payload={payload_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
