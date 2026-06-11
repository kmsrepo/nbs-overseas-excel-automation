#!/usr/bin/env python3
"""Collect OECD financial net worth (old LBF90NC), 2007-2025."""

from __future__ import annotations

import csv
import datetime as dt
import decimal
import pathlib
import subprocess
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "oecd_financial_net_worth"
RAW_DIR = OUT_DIR / "raw"
START_YEAR = "2007"
END_YEAR = "2025"
DATAFLOW_ID = "OECD.SDD.NAD:DSD_NASEC20@DF_T720R_A(1.1)"
DATASET = "Annual Financial Balance Sheets (stocks), non-consolidated"
LEGACY_CODE = "LBF90NC"
NEW_INSTR_ASSET = "BF90"
DATA_URL = (
    "https://sdmx.oecd.org/public/rest/v1/data/"
    "OECD.SDD.NAD,DSD_NASEC20@DF_T720R_A/"
    "A.N..W.S1.S1.N.N.LE.BF90._Z.XDC._T.S.V.N.T0720._Z"
    f"?startPeriod={START_YEAR}&endPeriod={END_YEAR}"
)
DSD_URL = (
    "https://sdmx.oecd.org/public/rest/v1/datastructure/"
    "OECD.SDD.NAD/DSD_NASEC20/1.1?references=all"
)
EXPLORER_URL = (
    "https://data-explorer.oecd.org/vis?"
    "df%5Bag%5D=OECD.SDD.NAD&df%5Bds%5D=dsDisseminateFinalDMZ&"
    "df%5Bid%5D=DSD_NASEC20%40DF_T720R_A&lc=en"
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

    raw_csv_path = RAW_DIR / "oecd_financial_net_worth_lbf90nc_2007_2025_raw.csv"
    dsd_path = RAW_DIR / "oecd_dsd_nasec20_1_1_with_codelists.xml"
    raw_csv_path.write_bytes(fetch_bytes(DATA_URL, "text/csv"))
    dsd_path.write_bytes(fetch_bytes(DSD_URL))
    codelists = load_codelists(dsd_path)

    rows: list[dict[str, str]] = []
    with raw_csv_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if row["SECTOR"] != "S1":
                continue
            if row["INSTR_ASSET"] != NEW_INSTR_ASSET:
                continue
            if row["UNIT_MEASURE"] != "XDC":
                continue
            if not (START_YEAR <= row["TIME_PERIOD"] <= END_YEAR):
                continue

            rows.append(
                {
                    "수집일시": collected_at,
                    "출처기관": "OECD",
                    "데이터셋": DATASET,
                    "데이터플로우": row["DATAFLOW"],
                    "구OECD코드": LEGACY_CODE,
                    "지표코드": row["INSTR_ASSET"],
                    "지표명": label(codelists, "OECD.SDD.NAD", "CL_INSTR_ASSET", row["INSTR_ASSET"]),
                    "국가코드": row["REF_AREA"],
                    "국가명": label(codelists, "OECD", "CL_AREA", row["REF_AREA"]),
                    "섹터코드": row["SECTOR"],
                    "섹터명": label(codelists, "OECD", "CL_SECTOR", row["SECTOR"]),
                    "연도": row["TIME_PERIOD"],
                    "값_백만현지통화": row["OBS_VALUE"],
                    "값_현지통화_승수반영": scaled_value(row["OBS_VALUE"], row["UNIT_MULT"]),
                    "단위코드": row["UNIT_MEASURE"],
                    "단위명": label(codelists, "OECD", "CL_UNIT_MEASURE", row["UNIT_MEASURE"]),
                    "단위승수": row["UNIT_MULT"],
                    "통화": row["CURRENCY"],
                    "회계항목코드": row["ACCOUNTING_ENTRY"],
                    "회계항목명": label(codelists, "OECD", "CL_ACCOUNTING_ENTRY", row["ACCOUNTING_ENTRY"]),
                    "거래코드": row["TRANSACTION"],
                    "거래명": label(codelists, "OECD.SDD.NAD", "CL_TRANSACTION", row["TRANSACTION"]),
                    "관측상태코드": row["OBS_STATUS"],
                    "관측상태명": label(codelists, "SDMX", "CL_OBS_STATUS", row["OBS_STATUS"]),
                    "기밀상태코드": row["CONF_STATUS"],
                    "소수자리": row["DECIMALS"],
                    "원자료주소": DATA_URL,
                    "탐색기주소": EXPLORER_URL,
                    "원본파일": str(raw_csv_path.relative_to(ROOT)),
                }
            )

    fields = [
        "수집일시",
        "출처기관",
        "데이터셋",
        "데이터플로우",
        "구OECD코드",
        "지표코드",
        "지표명",
        "국가코드",
        "국가명",
        "섹터코드",
        "섹터명",
        "연도",
        "값_백만현지통화",
        "값_현지통화_승수반영",
        "단위코드",
        "단위명",
        "단위승수",
        "통화",
        "회계항목코드",
        "회계항목명",
        "거래코드",
        "거래명",
        "관측상태코드",
        "관측상태명",
        "기밀상태코드",
        "소수자리",
        "원자료주소",
        "탐색기주소",
        "원본파일",
    ]
    write_csv(OUT_DIR / "oecd_financial_net_worth_lbf90nc_2007_2025_장형.csv", fields, rows)

    country_rows = sorted({(row["국가코드"], row["국가명"], row["통화"]) for row in rows})
    write_csv(
        OUT_DIR / "oecd_financial_net_worth_lbf90nc_국가_메타데이터.csv",
        ["수집일시", "국가코드", "국가명", "통화"],
        [{"수집일시": collected_at, "국가코드": c, "국가명": n, "통화": cur} for c, n, cur in country_rows],
    )

    log_rows = [
        {
            "수집일시": collected_at,
            "출처기관": "OECD",
            "데이터셋": DATASET,
            "구OECD코드": LEGACY_CODE,
            "새지표코드": NEW_INSTR_ASSET,
            "요청기간": f"{START_YEAR}-{END_YEAR}",
            "필터": "FREQ=A; ADJUSTMENT=N; SECTOR=S1; ACCOUNTING_ENTRY=N; TRANSACTION=LE; INSTR_ASSET=BF90; UNIT_MEASURE=XDC; TABLE_IDENTIFIER=T0720",
            "행수": str(len(rows)),
            "국가수": str(len({row["국가코드"] for row in rows})),
            "상태": "완료",
            "원자료주소": DATA_URL,
            "탐색기주소": EXPLORER_URL,
            "원본파일": str(raw_csv_path.relative_to(ROOT)),
            "코드리스트파일": str(dsd_path.relative_to(ROOT)),
        }
    ]
    write_csv(
        OUT_DIR / "oecd_financial_net_worth_lbf90nc_수집로그.csv",
        [
            "수집일시",
            "출처기관",
            "데이터셋",
            "구OECD코드",
            "새지표코드",
            "요청기간",
            "필터",
            "행수",
            "국가수",
            "상태",
            "원자료주소",
            "탐색기주소",
            "원본파일",
            "코드리스트파일",
        ],
        log_rows,
    )

    print(f"data_rows={len(rows)}")
    print(f"countries={len({row['국가코드'] for row in rows})}")
    print(f"years={min(row['연도'] for row in rows)}-{max(row['연도'] for row in rows)}")
    print(f"obs_status={sorted({row['관측상태코드'] for row in rows})}")
    print(f"output_dir={OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

