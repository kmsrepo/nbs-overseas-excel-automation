# Overseas Source Excel Automation

This repository collects the requested FRED/OECD source data, rebuilds the requested pivot-style Excel workbook, and publishes the result through GitHub Releases.

## Weekly GitHub Actions Run

`.github/workflows/weekly-overseas-excel-release.yml` runs once a week:

- Schedule: every Monday 09:00 KST
- Manual trigger: `workflow_dispatch`
- Release title format: `해외자료 수집 YYYY-MM-DD_HH-MM-SS_KST`

The release includes:

- `요청사항반영_피벗통합_메모포함_<수집시각>.xlsx`
- `요청사항반영_엑셀생성로그_<수집시각>.csv`
- `source_materials_<수집시각>.zip`: 결과물 생성에 사용한 FRED/OECD 원본자료, 정규화 CSV, 메타데이터, 수집 로그
  - ABS 520410 최신 National Balance Sheet 원본 xlsx 및 순금융자산 산출 CSV 포함

## Local Run

```bash
python overseas_source_collection/scripts/build_requested_excel_outputs_actions.py
```

For a local rebuild from already-normalized CSV files:

```bash
python overseas_source_collection/scripts/build_requested_excel_outputs_actions.py --skip-normalizers
```

The workbook is written to:

```text
outputs/requested_pivot_workbook/요청사항반영_피벗통합_메모포함.xlsx
```

## Workbook Content

- `FRED_피벗`: requested FRED codes, code order preserved, years as columns
- `비금융자산_피벗`: OECD Table 9B, Total economy, requested transaction order, non-final values commented. The missing `NN / United States` row is supplemented with Excel `SUM` formulas over the six requested FRED non-financial asset series and highlighted in light red. A separate FRED real-estate row, also formula-based and light red, is placed directly below it. Formula cached values are stored so read-only viewers can display the calculated numbers before recalculation.
- `비금융자산_코드`: transaction code reference
- `금융순자산_피벗`: financial net worth by country/year, non-final values commented. The derived `Australia (ABS 520410)` row is calculated from latest ABS 520410 current-price financial assets minus liabilities and highlighted in light purple.
- `GDP_OECD회원국`: OECD member countries only, output approach first, expenditure approach fallback in purple, non-final values commented. For Korea, expenditure approach is preferred when the output approach value is estimated.
- `수집정보`: build summary
