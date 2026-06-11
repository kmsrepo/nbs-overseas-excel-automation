#!/usr/bin/env python3
"""Collect OECD annual balance sheets for non-financial assets, 2000-2025."""

from __future__ import annotations

import csv
import datetime as dt
import decimal
import pathlib
import subprocess
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "oecd_table9b_nonfinancial_assets"
RAW_DIR = OUT_DIR / "raw"
START_YEAR = "2000"
END_YEAR = "2025"
INSTR_ASSETS = ["NN", "N1N", "N111N", "N112N", "N1121N", "N211N"]
DATAFLOW = "OECD.SDD.NAD:DSD_NASEC10@DF_TABLE9B(1.1)"
DATA_URL = (
    "https://sdmx.oecd.org/public/rest/v1/data/"
    "OECD.SDD.NAD,DSD_NASEC10@DF_TABLE9B/"
    f"A....A._Z.{'+'.join(INSTR_ASSETS)}._Z.XDC._Z.V.N.T2600"
    f"?startPeriod={START_YEAR}&endPeriod={END_YEAR}"
)
DSD_URL = (
    "https://sdmx.oecd.org/public/rest/v1/datastructure/"
    "OECD.SDD.NAD/DSD_NASEC10/1.1?references=all"
)
EXPLORER_URL = (
    "https://data-explorer.oecd.org/vis?"
    "df%5Bag%5D=OECD.SDD.NAD&df%5Bds%5D=dsDisseminateFinalDMZ&"
    "df%5Bid%5D=DSD_NASEC10%40DF_TABLE9B&lc=en"
)


def fetch_bytes(url: str, accept: str | None = None) -> bytes:
    command = ["curl", "-L", "--fail", "--silent", "--show-error", "--max-time", "120"]
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


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    collected_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")

    raw_csv_path = RAW_DIR / "oecd_table9b_nonfinancial_assets_2000_2025_raw.csv"
    dsd_path = RAW_DIR / "oecd_dsd_nasec10_1_1_with_codelists.xml"
    raw_csv_path.write_bytes(fetch_bytes(DATA_URL, "text/csv"))
    dsd_path.write_bytes(fetch_bytes(DSD_URL))

    codelists = load_codelists(dsd_path)
    data_rows: list[dict[str, str]] = []
    with raw_csv_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if row["UNIT_MEASURE"] != "XDC":
                continue
            if row["INSTR_ASSET"] not in INSTR_ASSETS:
                continue
            if not (START_YEAR <= row["TIME_PERIOD"] <= END_YEAR):
                continue

            data_rows.append(
                {
                    "수집일시": collected_at,
                    "출처기관": "OECD",
                    "데이터셋": "Annual balance sheets for non-financial assets",
                    "데이터플로우": row["DATAFLOW"],
                    "국가코드": row["REF_AREA"],
                    "국가명": label(codelists, "OECD", "CL_AREA", row["REF_AREA"]),
                    "섹터코드": row["SECTOR"],
                    "섹터명": label(codelists, "OECD", "CL_SECTOR", row["SECTOR"]),
                    "상대섹터코드": row["COUNTERPART_SECTOR"],
                    "상대섹터명": label(codelists, "OECD", "CL_SECTOR", row["COUNTERPART_SECTOR"]),
                    "회계항목코드": row["ACCOUNTING_ENTRY"],
                    "회계항목명": label(codelists, "OECD", "CL_ACCOUNTING_ENTRY", row["ACCOUNTING_ENTRY"]),
                    "원본TRANSACTION코드": row["TRANSACTION"],
                    "Transact코드": row["INSTR_ASSET"],
                    "Transact명": label(codelists, "OECD.SDD.NAD", "CL_INSTR_ASSET", row["INSTR_ASSET"]),
                    "연도": row["TIME_PERIOD"],
                    "값": row["OBS_VALUE"],
                    "값_현지통화_승수반영": scaled_value(row["OBS_VALUE"], row["UNIT_MULT"]),
                    "단위코드": row["UNIT_MEASURE"],
                    "단위명": label(codelists, "OECD", "CL_UNIT_MEASURE", row["UNIT_MEASURE"]),
                    "단위승수": row["UNIT_MULT"],
                    "통화": row["CURRENCY"],
                    "가격기준코드": row["PRICE_BASE"],
                    "가격기준명": label(codelists, "OECD", "CL_PRICES", row["PRICE_BASE"]),
                    "변환코드": row["TRANSFORMATION"],
                    "변환명": label(codelists, "OECD", "CL_TRANSFORMATION", row["TRANSFORMATION"]),
                    "관측상태코드": row["OBS_STATUS"],
                    "관측상태명": label(codelists, "SDMX", "CL_OBS_STATUS", row["OBS_STATUS"]),
                    "기밀상태코드": row["CONF_STATUS"],
                    "소수자리": row["DECIMALS"],
                    "원자료주소": DATA_URL,
                    "탐색기주소": EXPLORER_URL,
                    "원본파일": str(raw_csv_path.relative_to(ROOT)),
                }
            )

    data_fields = [
        "수집일시",
        "출처기관",
        "데이터셋",
        "데이터플로우",
        "국가코드",
        "국가명",
        "섹터코드",
        "섹터명",
        "상대섹터코드",
        "상대섹터명",
        "회계항목코드",
        "회계항목명",
        "원본TRANSACTION코드",
        "Transact코드",
        "Transact명",
        "연도",
        "값",
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
    write_csv(OUT_DIR / "oecd_비금융자산_대차대조표_2000_2025_현지통화_긴형식.csv", data_fields, data_rows)

    code_rows = []
    for code in INSTR_ASSETS:
        code_rows.append(
            {
                "수집일시": collected_at,
                "Transact코드": code,
                "Transact명": label(codelists, "OECD.SDD.NAD", "CL_INSTR_ASSET", code),
            }
        )
    write_csv(OUT_DIR / "oecd_비금융자산_Transact코드_메타데이터.csv", ["수집일시", "Transact코드", "Transact명"], code_rows)

    country_rows = sorted(
        {
            (row["국가코드"], row["국가명"], row["통화"])
            for row in data_rows
        }
    )
    write_csv(
        OUT_DIR / "oecd_비금융자산_국가_메타데이터.csv",
        ["수집일시", "국가코드", "국가명", "통화"],
        [
            {"수집일시": collected_at, "국가코드": code, "국가명": name, "통화": currency}
            for code, name, currency in country_rows
        ],
    )

    sector_rows = sorted({(row["섹터코드"], row["섹터명"]) for row in data_rows})
    write_csv(
        OUT_DIR / "oecd_비금융자산_섹터_메타데이터.csv",
        ["수집일시", "섹터코드", "섹터명"],
        [{"수집일시": collected_at, "섹터코드": code, "섹터명": name} for code, name in sector_rows],
    )

    log_rows = [
        {
            "수집일시": collected_at,
            "출처기관": "OECD",
            "데이터셋": "Annual balance sheets for non-financial assets",
            "요청기간": f"{START_YEAR}-{END_YEAR}",
            "요청Transact코드": "|".join(INSTR_ASSETS),
            "필터": "FREQ=A; ACCOUNTING_ENTRY=A; TRANSACTION=_Z; UNIT_MEASURE=XDC; PRICE_BASE=V; TRANSFORMATION=N; TABLE_IDENTIFIER=T2600",
            "행수": str(len(data_rows)),
            "국가수": str(len({row["국가코드"] for row in data_rows})),
            "섹터수": str(len({row["섹터코드"] for row in data_rows})),
            "상태": "완료",
            "원자료주소": DATA_URL,
            "탐색기주소": EXPLORER_URL,
            "원본파일": str(raw_csv_path.relative_to(ROOT)),
            "코드리스트파일": str(dsd_path.relative_to(ROOT)),
        }
    ]
    write_csv(
        OUT_DIR / "oecd_비금융자산_수집로그.csv",
        [
            "수집일시",
            "출처기관",
            "데이터셋",
            "요청기간",
            "요청Transact코드",
            "필터",
            "행수",
            "국가수",
            "섹터수",
            "상태",
            "원자료주소",
            "탐색기주소",
            "원본파일",
            "코드리스트파일",
        ],
        log_rows,
    )

    print(f"data_rows={len(data_rows)}")
    print(f"countries={len({row['국가코드'] for row in data_rows})}")
    print(f"sectors={len({row['섹터코드'] for row in data_rows})}")
    print(f"transact_codes={','.join(sorted({row['Transact코드'] for row in data_rows}))}")
    print(f"output_dir={OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

