#!/usr/bin/env python3
"""Collect OECD GDP by output approach with expenditure fallback, 2014-2025."""

from __future__ import annotations

import csv
import datetime as dt
import decimal
import pathlib
import subprocess
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "oecd_gdp_output_expenditure"
RAW_DIR = OUT_DIR / "raw"
START_YEAR = "2014"
END_YEAR = "2025"
DSD_URL = (
    "https://sdmx.oecd.org/public/rest/v1/datastructure/"
    "OECD.SDD.NAD/DSD_NAMAIN10/2.0?references=all"
)
OUTPUT_URL = (
    "https://sdmx.oecd.org/public/rest/v1/data/"
    "OECD.SDD.NAD,DSD_NAMAIN10@DF_TABLE1_OUTPUT/"
    "A..S1.S1.B1GQ....XDC.V.N.T0101"
    f"?startPeriod={START_YEAR}&endPeriod={END_YEAR}"
)
EXPENDITURE_URL = (
    "https://sdmx.oecd.org/public/rest/v1/data/"
    "OECD.SDD.NAD,DSD_NAMAIN10@DF_TABLE1_EXPENDITURE/"
    "A..S1.S1.B1GQ....XDC.V.N.T0102"
    f"?startPeriod={START_YEAR}&endPeriod={END_YEAR}"
)
EXPLORER_URL = (
    "https://data-explorer.oecd.org/vis?"
    "df%5Bag%5D=OECD.SDD.NAD&df%5Bds%5D=dsDisseminateFinalDMZ&"
    "df%5Bid%5D=DSD_NAMAIN10%40DF_TABLE1_OUTPUT&lc=en"
)


def fetch_bytes(url: str, accept: str | None = None) -> bytes:
    command = ["curl", "-L", "--fail", "--silent", "--show-error", "--max-time", "180"]
    command += ["--retry", "3", "--retry-delay", "2"]
    if accept:
        command += ["-H", f"Accept: {accept}"]
    command.append(url)
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if not result.stdout.strip():
        raise RuntimeError(f"empty response: {url}")
    return result.stdout


def code_name(code: ET.Element) -> str:
    ns = {"common": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common"}
    names = code.findall("common:Name", ns)
    for name in names:
        if name.attrib.get("{http://www.w3.org/XML/1998/namespace}lang") == "en":
            return " ".join((name.text or "").split())
    if names:
        return " ".join((names[0].text or "").split())
    return ""


def load_codelists(path: pathlib.Path) -> dict[tuple[str, str], dict[str, str]]:
    ns = {"structure": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"}
    root = ET.parse(path).getroot()
    codelists: dict[tuple[str, str], dict[str, str]] = {}
    for codelist in root.findall(".//structure:Codelist", ns):
        agency = codelist.attrib.get("agencyID", "")
        codelist_id = codelist.attrib.get("id", "")
        values = {}
        for code in codelist.findall("structure:Code", ns):
            values[code.attrib["id"]] = code_name(code)
        codelists[(agency, codelist_id)] = values
    return codelists


def label(codelists: dict[tuple[str, str], dict[str, str]], agency: str, codelist_id: str, code: str) -> str:
    return codelists.get((agency, codelist_id), {}).get(code, "")


def scaled_value(raw_value: str, unit_mult: str) -> str:
    if raw_value in {"", "."}:
        return ""
    multiplier = decimal.Decimal(10) ** int(unit_mult or "0")
    value = decimal.Decimal(raw_value) * multiplier
    return format(value, "f")


def write_csv(path: pathlib.Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def normalise_rows(
    *,
    raw_csv_path: pathlib.Path,
    codelists: dict[tuple[str, str], dict[str, str]],
    collected_at: str,
    approach: str,
    dataset: str,
    source_url: str,
    explorer_url: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with raw_csv_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if not (START_YEAR <= row["TIME_PERIOD"] <= END_YEAR):
                continue
            if row["UNIT_MEASURE"] != "XDC" or row["PRICE_BASE"] != "V" or row["UNIT_MULT"] != "6":
                continue
            rows.append(
                {
                    "수집일시": collected_at,
                    "출처기관": "OECD",
                    "데이터셋": dataset,
                    "접근법": approach,
                    "데이터플로우": row["DATAFLOW"],
                    "국가코드": row["REF_AREA"],
                    "국가명": label(codelists, "OECD", "CL_AREA", row["REF_AREA"]),
                    "섹터코드": row["SECTOR"],
                    "섹터명": label(codelists, "OECD", "CL_SECTOR", row["SECTOR"]),
                    "연도": row["TIME_PERIOD"],
                    "거래코드": row["TRANSACTION"],
                    "거래명": label(codelists, "OECD.SDD.NAD", "CL_TRANSACTION", row["TRANSACTION"]),
                    "값_백만현지통화": row["OBS_VALUE"],
                    "값_현지통화_승수반영": scaled_value(row["OBS_VALUE"], row["UNIT_MULT"]),
                    "단위코드": row["UNIT_MEASURE"],
                    "단위명": label(codelists, "OECD", "CL_UNIT_MEASURE", row["UNIT_MEASURE"]),
                    "단위승수": row["UNIT_MULT"],
                    "통화": row["CURRENCY"],
                    "가격기준코드": row["PRICE_BASE"],
                    "가격기준명": label(codelists, "OECD.SDD.NAD", "CL_PRICE_BASE", row["PRICE_BASE"]),
                    "변환코드": row["TRANSFORMATION"],
                    "변환명": label(codelists, "OECD", "CL_TRANSFORMATION", row["TRANSFORMATION"]),
                    "관측상태코드": row["OBS_STATUS"],
                    "관측상태명": label(codelists, "SDMX", "CL_OBS_STATUS", row["OBS_STATUS"]),
                    "기밀상태코드": row["CONF_STATUS"],
                    "소수자리": row["DECIMALS"],
                    "원자료주소": source_url,
                    "탐색기주소": explorer_url,
                    "원본파일": str(raw_csv_path.relative_to(ROOT)),
                }
            )
    return rows


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    collected_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")

    output_raw_path = RAW_DIR / "oecd_gdp_output_2014_2025_raw.csv"
    expenditure_raw_path = RAW_DIR / "oecd_gdp_expenditure_2014_2025_raw.csv"
    dsd_path = RAW_DIR / "oecd_dsd_namain10_2_0_with_codelists.xml"

    output_raw_path.write_bytes(fetch_bytes(OUTPUT_URL, "text/csv"))
    expenditure_raw_path.write_bytes(fetch_bytes(EXPENDITURE_URL, "text/csv"))
    dsd_path.write_bytes(fetch_bytes(DSD_URL))
    codelists = load_codelists(dsd_path)

    output_rows = normalise_rows(
        raw_csv_path=output_raw_path,
        codelists=codelists,
        collected_at=collected_at,
        approach="산출접근법",
        dataset="Annual GDP and components - output approach",
        source_url=OUTPUT_URL,
        explorer_url=EXPLORER_URL,
    )
    expenditure_rows = normalise_rows(
        raw_csv_path=expenditure_raw_path,
        codelists=codelists,
        collected_at=collected_at,
        approach="지출접근법",
        dataset="Annual GDP and components - expenditure approach",
        source_url=EXPENDITURE_URL,
        explorer_url=EXPLORER_URL.replace("DF_TABLE1_OUTPUT", "DF_TABLE1_EXPENDITURE"),
    )
    rows = sorted(output_rows + expenditure_rows, key=lambda r: (r["국가코드"], r["연도"], r["접근법"]))

    fields = [
        "수집일시",
        "출처기관",
        "데이터셋",
        "접근법",
        "데이터플로우",
        "국가코드",
        "국가명",
        "섹터코드",
        "섹터명",
        "연도",
        "거래코드",
        "거래명",
        "값_백만현지통화",
        "값_현지통화_승수반영",
        "단위코드",
        "단위명",
        "단위승수",
        "통화",
        "가격기준코드",
        "가격기준명",
        "변환코드",
        "변환명",
        "관측상태코드",
        "관측상태명",
        "기밀상태코드",
        "소수자리",
        "원자료주소",
        "탐색기주소",
        "원본파일",
    ]
    write_csv(OUT_DIR / "oecd_gdp_output_expenditure_2014_2025_장형.csv", fields, rows)

    countries = sorted({(row["국가코드"], row["국가명"], row["통화"]) for row in rows})
    write_csv(
        OUT_DIR / "oecd_gdp_output_expenditure_국가_메타데이터.csv",
        ["수집일시", "국가코드", "국가명", "통화"],
        [{"수집일시": collected_at, "국가코드": c, "국가명": n, "통화": cur} for c, n, cur in countries],
    )

    log_rows = [
        {
            "수집일시": collected_at,
            "출처기관": "OECD",
            "데이터셋": "Annual GDP and components - output/expenditure approach",
            "요청기간": f"{START_YEAR}-{END_YEAR}",
            "단위조건": "UNIT_MEASURE=XDC; PRICE_BASE=V; UNIT_MULT=6",
            "산출접근필터": "FREQ=A; SECTOR=S1; COUNTERPART_SECTOR=S1; TRANSACTION=B1GQ; UNIT_MEASURE=XDC; PRICE_BASE=V; TRANSFORMATION=N; TABLE_IDENTIFIER=T0101",
            "지출접근필터": "FREQ=A; SECTOR=S1; COUNTERPART_SECTOR=S1; TRANSACTION=B1GQ; UNIT_MEASURE=XDC; PRICE_BASE=V; TRANSFORMATION=N; TABLE_IDENTIFIER=T0102",
            "산출접근행수": str(len(output_rows)),
            "지출접근행수": str(len(expenditure_rows)),
            "전체행수": str(len(rows)),
            "국가수": str(len({row["국가코드"] for row in rows})),
            "상태": "완료",
            "산출접근원자료주소": OUTPUT_URL,
            "지출접근원자료주소": EXPENDITURE_URL,
            "산출접근원본파일": str(output_raw_path.relative_to(ROOT)),
            "지출접근원본파일": str(expenditure_raw_path.relative_to(ROOT)),
            "코드리스트파일": str(dsd_path.relative_to(ROOT)),
        }
    ]
    write_csv(
        OUT_DIR / "oecd_gdp_output_expenditure_수집로그.csv",
        [
            "수집일시",
            "출처기관",
            "데이터셋",
            "요청기간",
            "단위조건",
            "산출접근필터",
            "지출접근필터",
            "산출접근행수",
            "지출접근행수",
            "전체행수",
            "국가수",
            "상태",
            "산출접근원자료주소",
            "지출접근원자료주소",
            "산출접근원본파일",
            "지출접근원본파일",
            "코드리스트파일",
        ],
        log_rows,
    )

    print(f"output_rows={len(output_rows)}")
    print(f"expenditure_rows={len(expenditure_rows)}")
    print(f"total_rows={len(rows)}")
    print(f"countries={len({row['국가코드'] for row in rows})}")
    print(f"years={min(row['연도'] for row in rows)}-{max(row['연도'] for row in rows)}")
    print(f"obs_status={sorted({row['관측상태코드'] for row in rows})}")
    print(f"output_dir={OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
