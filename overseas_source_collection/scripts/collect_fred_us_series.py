#!/usr/bin/env python3
"""Collect selected FRED series for 2000-2025 in pivot-friendly Korean CSVs."""

from __future__ import annotations

import csv
import datetime as dt
import html
import pathlib
import re
import subprocess
import time


ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "fred_us"
RAW_DIR = OUT_DIR / "raw"
START_DATE = "2000-01-01"
END_DATE = "2025-12-31"
SERIES_IDS = [
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


def fetch_text(url: str) -> str:
    result = subprocess.run(
        [
            "curl",
            "-L",
            "--silent",
            "--show-error",
            "--max-time",
            "30",
            "--retry",
            "3",
            "--retry-delay",
            "2",
            url,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    text = result.stdout.decode("utf-8-sig")
    if not text.strip():
        raise RuntimeError(f"empty response: {url}")
    return text


def clean_html(value: str) -> str:
    value = re.sub(r"<br\s*/?>", " ", value)
    value = re.sub(r"<.*?>", "", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def parse_data_page(series_id: str) -> tuple[dict[str, str], list[dict[str, str]]]:
    url = f"https://fred.stlouisfed.org/data/{series_id}"
    text = fetch_text(url)
    raw_path = RAW_DIR / f"{series_id}_fred_data_page.html"
    raw_path.write_text(text, encoding="utf-8")

    pairs = re.findall(
        r'<th[^>]*scope="row"[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>',
        text,
        flags=re.S,
    )
    metadata_table = {clean_html(key): clean_html(value) for key, value in pairs}
    date_range = metadata_table.get("Date Range", "")
    first_observation, last_observation = "", ""
    if " to " in date_range:
        first_observation, last_observation = date_range.split(" to ", 1)

    return {
        "코드": series_id,
        "항목명": metadata_table.get("Title", ""),
        "출처기관": metadata_table.get("Source", "Federal Reserve Bank of St. Louis"),
        "릴리스": metadata_table.get("Release", ""),
        "빈도": metadata_table.get("Frequency", ""),
        "빈도약어": "A" if metadata_table.get("Frequency", "").startswith("Annual") else "",
        "단위": metadata_table.get("Units", ""),
        "단위약어": "",
        "계절조정": metadata_table.get("Seasonal Adjustment", ""),
        "계절조정약어": "NSA" if metadata_table.get("Seasonal Adjustment") == "Not Seasonally Adjusted" else "",
        "최초관측일": first_observation,
        "최종관측일": last_observation,
        "자료갱신일시": metadata_table.get("Last Updated", ""),
        "빈티지일": "",
        "메타데이터주소": f"https://fred.stlouisfed.org/series/{series_id}",
        "원자료주소": url,
        "원본파일": str(raw_path.relative_to(ROOT)),
    }, parse_observations(text, raw_path)


def parse_observations(text: str, raw_path: pathlib.Path) -> list[dict[str, str]]:
    rows = []
    matches = re.findall(
        r'<th[^>]*scope="row"[^>]*>\s*(\d{4}-\d{2}-\d{2})\s*</th>\s*<td[^>]*>\s*([^<]*)\s*</td>',
        text,
        flags=re.S,
    )
    for observation_date, value in matches:
        value = clean_html(value)
        if observation_date < START_DATE or observation_date > END_DATE:
            continue
        rows.append(
            {
                "관측일": observation_date,
                "연도": observation_date[:4],
                "값": "" if value == "." else value,
                "원본값": value,
                "원본파일": str(raw_path.relative_to(ROOT)),
            }
        )
    return rows


def write_csv(path: pathlib.Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    collected_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")

    data_rows: list[dict[str, str]] = []
    metadata_rows: list[dict[str, str]] = []
    log_rows: list[dict[str, str]] = []

    for order, series_id in enumerate(SERIES_IDS, start=1):
        print(f"[{order}/{len(SERIES_IDS)}] collecting {series_id}", flush=True)
        metadata, observations = parse_data_page(series_id)

        metadata_rows.append(
            {
                "수집일시": collected_at,
                "순번": str(order),
                **metadata,
                "수집시작일": START_DATE,
                "수집종료일": END_DATE,
                "수집행수": str(len(observations)),
            }
        )

        for observation in observations:
            data_rows.append(
                {
                    "수집일시": collected_at,
                    "출처기관": metadata["출처기관"],
                    "데이터베이스": "FRED",
                    "국가": "미국",
                    "코드": series_id,
                    "항목명": metadata["항목명"],
                    "빈도": metadata["빈도"],
                    "빈도약어": metadata["빈도약어"],
                    "단위": metadata["단위"],
                    "단위약어": metadata["단위약어"],
                    "계절조정": metadata["계절조정"],
                    "관측일": observation["관측일"],
                    "연도": observation["연도"],
                    "값": observation["값"],
                    "원본값": observation["원본값"],
                    "기간시작일": START_DATE,
                    "기간종료일": END_DATE,
                    "원본파일": observation["원본파일"],
                    "원자료주소": metadata["원자료주소"],
                    "메타데이터주소": metadata["메타데이터주소"],
                    "자료갱신일시": metadata["자료갱신일시"],
                    "비고": "",
                }
            )

        log_rows.append(
            {
                "수집일시": collected_at,
                "코드": series_id,
                "항목명": metadata["항목명"],
                "수집시작일": START_DATE,
                "수집종료일": END_DATE,
                "수집행수": str(len(observations)),
                "상태": "완료",
                "원자료주소": metadata["원자료주소"],
                "원본파일": metadata["원본파일"],
            }
        )

        time.sleep(0.25)

    data_fields = [
        "수집일시",
        "출처기관",
        "데이터베이스",
        "국가",
        "코드",
        "항목명",
        "빈도",
        "빈도약어",
        "단위",
        "단위약어",
        "계절조정",
        "관측일",
        "연도",
        "값",
        "원본값",
        "기간시작일",
        "기간종료일",
        "원본파일",
        "원자료주소",
        "메타데이터주소",
        "자료갱신일시",
        "비고",
    ]
    metadata_fields = [
        "수집일시",
        "순번",
        "코드",
        "항목명",
        "빈도",
        "빈도약어",
        "단위",
        "단위약어",
        "계절조정",
        "계절조정약어",
        "출처기관",
        "릴리스",
        "최초관측일",
        "최종관측일",
        "자료갱신일시",
        "빈티지일",
        "수집시작일",
        "수집종료일",
        "수집행수",
        "원자료주소",
        "메타데이터주소",
        "원본파일",
    ]
    log_fields = [
        "수집일시",
        "코드",
        "항목명",
        "수집시작일",
        "수집종료일",
        "수집행수",
        "상태",
        "원자료주소",
        "원본파일",
    ]

    write_csv(OUT_DIR / "fred_미국_2000_2025_긴형식.csv", data_fields, data_rows)
    write_csv(OUT_DIR / "fred_미국_시리즈_메타데이터.csv", metadata_fields, metadata_rows)
    write_csv(OUT_DIR / "fred_미국_수집로그.csv", log_fields, log_rows)

    print(f"data_rows={len(data_rows)}")
    print(f"metadata_rows={len(metadata_rows)}")
    print(f"collection_log_rows={len(log_rows)}")
    print(f"output_dir={OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
