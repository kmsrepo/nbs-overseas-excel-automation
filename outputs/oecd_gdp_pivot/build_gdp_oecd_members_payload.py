#!/usr/bin/env python3
"""Filter OECD GDP pivot payload to current OECD member countries."""

from __future__ import annotations

import json
import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "outputs" / "oecd_gdp_pivot"
INPUT_PAYLOAD = OUT_DIR / "gdp_pivot_payload.json"
OUTPUT_PAYLOAD = OUT_DIR / "gdp_oecd_members_pivot_payload.json"

OECD_MEMBER_CODES = [
    "AUS",
    "AUT",
    "BEL",
    "CAN",
    "CHL",
    "COL",
    "CRI",
    "CZE",
    "DNK",
    "EST",
    "FIN",
    "FRA",
    "DEU",
    "GRC",
    "HUN",
    "ISL",
    "IRL",
    "ISR",
    "ITA",
    "JPN",
    "KOR",
    "LVA",
    "LTU",
    "LUX",
    "MEX",
    "NLD",
    "NZL",
    "NOR",
    "POL",
    "PRT",
    "SVK",
    "SVN",
    "ESP",
    "SWE",
    "CHE",
    "TUR",
    "GBR",
    "USA",
]


def main() -> int:
    payload = json.loads(INPUT_PAYLOAD.read_text(encoding="utf-8"))
    member_set = set(OECD_MEMBER_CODES)
    member_order = {code: index for index, code in enumerate(OECD_MEMBER_CODES)}

    payload["pivot_rows"] = sorted(
        [row for row in payload["pivot_rows"] if row["국가코드"] in member_set],
        key=lambda row: member_order[row["국가코드"]],
    )
    payload["notes"] = [note for note in payload["notes"] if note["국가코드"] in member_set]
    payload["fallback_cells"] = [cell for cell in payload["fallback_cells"] if cell["국가코드"] in member_set]
    payload["missing_cells"] = [cell for cell in payload["missing_cells"] if cell["국가코드"] in member_set]

    payload["summary"]["필터"] = "OECD current member countries only"
    payload["summary"]["OECD회원국수"] = len(OECD_MEMBER_CODES)
    payload["summary"]["행수"] = len(payload["pivot_rows"])
    payload["summary"]["메모수"] = len(payload["notes"])
    payload["summary"]["지출접근보강셀수"] = len(payload["fallback_cells"])
    payload["summary"]["결측셀수"] = len(payload["missing_cells"])
    payload["summary"]["회원국코드"] = ", ".join(OECD_MEMBER_CODES)
    payload["summary"]["회원국출처"] = "OECD Members and partners; OECD accession process"

    OUTPUT_PAYLOAD.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"member_countries={len(OECD_MEMBER_CODES)}")
    print(f"pivot_rows={len(payload['pivot_rows'])}")
    print(f"fallback_cells={len(payload['fallback_cells'])}")
    print(f"missing_cells={len(payload['missing_cells'])}")
    print(f"notes={len(payload['notes'])}")
    print(f"payload={OUTPUT_PAYLOAD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
