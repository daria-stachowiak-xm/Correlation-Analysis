# Correlation Lab

A Streamlit app for comparing marketing data from different tools. Upload spreadsheets and it
matches series by name and date, builds share metrics (Share of Search, Share of Conversation,
Share of Voice), and shows which series move together and how strongly. Results are described in
everyday language, so you don't need a statistics background to use it.

## Running the app

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501 with a fictional example dataset loaded. Uploading your own
files replaces it.

## Workflow

**1. Upload data.** CSV, TSV and Excel files are supported, and each Excel tab is read separately.
The date column is detected automatically. Headers that span several rows are handled, and dates
can be in formats such as `2026-08-31`, `8/31/26`, `Apr'23`, `Apr 2023` or `2026-Q3`. Summary
tabs (for example MyTelescope's "Pie Chart") are skipped, and the app says why. Long tables, with
one row per brand, channel or market, are split into separate series. You choose the split and any
filters.
