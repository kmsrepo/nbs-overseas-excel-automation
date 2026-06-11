#!/usr/bin/env python3
"""Prepare OECD GDP output/expenditure pivot payload."""

from __future__ import annotations

import csv
import json
import pathlib
from collections import defaultdict


ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "overseas_source_collection" / "oecd_gdp_output_expenditure"
OUT_DIR = ROOT / "outputs" / "oecd_gdp_pivot"
LONG_CSV = SOURCE_DIR / "oecd_gdp_output_expenditure_2014_2025_장형.csv"
LOG_CSV = SOURCE_DIR / "oecd_gdp_output_expenditure_수집로그.csv"
YEARS = [str(year) for year in range(2014, 2026)]
NORMAL_STATUS = {"A"}


def parse_number(value: str) -> float | None:
    if value in {"", "."}:
        return None
    return float(value)


def is_estimated(row: dict[str, str]) -> bool:
    return row["관측상태코드"] == "E" or "estimated" in row["관측상태명"].lower()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with LONG_CSV.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    by_country_year: dict[tuple[str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    country_names: dict[str, str] = {}
    country_currency: dict[str, str] = {}
    for row in rows:
        country_code = row["국가코드"]
        country_names[country_code] = row["국가명"] or country_code
        if row["통화"] and row["통화"] != "_Z":
            country_currency[country_code] = row["통화"]
        elif country_code not in country_currency:
            country_currency[country_code] = row["통화"]
        by_country_year[(country_code, row["연도"])][row["접근법"]] = row

    pivot_rows: list[dict[str, object]] = []
    notes: list[dict[str, str]] = []
    fallback_cells: list[dict[str, str]] = []
    missing_cells: list[dict[str, str]] = []
    selected_output = 0
    selected_expenditure = 0
    korea_estimated_expenditure_priority = 0

    for country_code in sorted(country_names, key=lambda code: (country_names[code], code)):
        country = country_names[country_code]
        pivot_row: dict[str, object] = {
            "나라": country,
            "국가코드": country_code,
            "화폐단위": country_currency.get(country_code, ""),
            "단위": "백만 현지통화",
        }
        for year in YEARS:
            candidates = by_country_year.get((country_code, year), {})
            output_candidate = candidates.get("산출접근법")
            expenditure_candidate = candidates.get("지출접근법")
            chosen = output_candidate
            source = "산출접근법"
            if (
                country_code == "KOR"
                and output_candidate is not None
                and expenditure_candidate is not None
                and is_estimated(output_candidate)
            ):
                chosen = expenditure_candidate
                source = "지출접근법"
                korea_estimated_expenditure_priority += 1
            elif chosen is None:
                chosen = expenditure_candidate
                source = "지출접근법"
            if chosen is None:
                pivot_row[year] = None
                missing_cells.append({"나라": country, "국가코드": country_code, "연도": year})
                continue

            pivot_row[year] = parse_number(chosen["값_백만현지통화"])
            if source == "산출접근법":
                selected_output += 1
            else:
                selected_expenditure += 1
                fallback_cells.append(
                    {
                        "나라": country,
                        "국가코드": country_code,
                        "화폐단위": pivot_row["화폐단위"],
                        "연도": year,
                        "값_백만현지통화": chosen["값_백만현지통화"],
                        "관측상태코드": chosen["관측상태코드"],
                        "관측상태명": chosen["관측상태명"],
                    }
                )

            if chosen["관측상태코드"] not in NORMAL_STATUS:
                notes.append(
                    {
                        "나라": country,
                        "국가코드": country_code,
                        "화폐단위": str(pivot_row["화폐단위"]),
                        "연도": year,
                        "접근법": source,
                        "거래코드": chosen["거래코드"],
                        "거래명": chosen["거래명"],
                        "관측상태코드": chosen["관측상태코드"],
                        "관측상태명": chosen["관측상태명"],
                        "값_백만현지통화": chosen["값_백만현지통화"],
                        "원자료주소": chosen["원자료주소"],
                    }
                )
        pivot_rows.append(pivot_row)

    with LOG_CSV.open(newline="", encoding="utf-8-sig") as handle:
        log_row = next(csv.DictReader(handle))

    payload = {
        "years": YEARS,
        "pivot_rows": pivot_rows,
        "notes": notes,
        "fallback_cells": fallback_cells,
        "missing_cells": missing_cells,
        "summary": {
            "데이터셋": "OECD Annual GDP and components - output/expenditure approach",
            "값정의": "산출접근법 GDP(B1GQ)를 우선 사용하고, 산출접근 값이 없는 경우 지출접근법 GDP(B1GQ)로 보강. 단, 한국 산출접근 값이 Estimated value이면 지출접근법 후보를 우선 사용",
            "수집일시": log_row["수집일시"],
            "기간": "2014-2025",
            "단위": "백만 현지통화, current prices, national currency",
            "산출접근선택셀수": selected_output,
            "지출접근보강셀수": selected_expenditure,
            "한국추정값_지출접근우선셀수": korea_estimated_expenditure_priority,
            "결측셀수": len(missing_cells),
            "행수": len(pivot_rows),
            "연도수": len(YEARS),
            "메모수": len(notes),
            "원천파일": str(LONG_CSV.relative_to(ROOT)),
            "수집로그": str(LOG_CSV.relative_to(ROOT)),
            "산출접근원자료주소": log_row["산출접근원자료주소"],
            "지출접근원자료주소": log_row["지출접근원자료주소"],
        },
    }
    payload_path = OUT_DIR / "gdp_pivot_payload.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"rows={len(pivot_rows)}")
    print(f"output_cells={selected_output}")
    print(f"expenditure_fallback_cells={selected_expenditure}")
    print(f"missing_cells={len(missing_cells)}")
    print(f"notes={len(notes)}")
    print(f"payload={payload_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
