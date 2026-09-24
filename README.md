# Correlation Lab (Streamlit)

An app for people who are not statisticians. Upload spreadsheets from different tools, and it
lines them up by name and by date, builds the extra measures you need (Share of Search, Share of
Conversation, Share of Voice), measures which numbers move together, and explains every result in
plain English.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

It opens at http://localhost:8501 with a clearly labelled fictional example loaded, so you can see
how it works before uploading anything. Your own files replace the example.

## What it does

**Step 1 – Bring your data.** CSV, TSV and Excel (each tab read separately). It finds the date
column on its own, copes with headers that span several rows, and understands dates written as
`2026-08-31`, `8/31/26`, `Apr'23`, `Apr 2023` or `2026-Q3`. Summary tabs (like MyTelescope's "Pie
Chart") are skipped with a reason. Long tables — one row per brand, channel or market — are split
into separate series; you choose what to split by and what to filter.

**Step 2 – Line it up.** Everything is rolled up to one calendar (weekly, monthly, quarterly).
Counts and money are added up, rates and scores averaged. Half-covered periods at the edges are
dropped, and unfinished/forecast periods are left out. A running log explains each step, and a
coverage chart shows when each series has data.

**Step 3 – Create new series.** One-click suggestions for Share of Search / Conversation / Voice,
plus a builder for any group you pick.

**Step 4 – Choose and rename.** Tick the series to include and rename them so names match across
files ("Hellman's" = "Hellmann's"). You can also switch a series between adding up and averaging.

**Step 5 – Goal and findings.** Pick the number you care about; everything else is ranked by how
closely it moves with it, with plain-English cards about early signals, trends, shared trends and
small samples.

**Step 6 – Matrix and pair detail.** A clickable correlation matrix, then for the selected pair:
r, r², p-value and n explained in words, a scatter plot, both series over time, and a lead/lag
check. Everything downloads as CSV or one Excel workbook.

## Files

| File | What's in it |
|---|---|
| `app.py` | The Streamlit interface and all charts (Plotly). |
| `corrlab.py` | The engine: file reading, date parsing, alignment, shares, correlation, findings. No Streamlit imports, so it's easy to test or reuse in a notebook. |
| `requirements.txt` | Dependencies. |
| `.streamlit/config.toml` | Theme and a 500 MB upload limit. |

## Using the engine on its own

```python
import corrlab as cl

tables = []
for file, sheet, grid in cl.read_upload("spend.xlsx", open("spend.xlsx", "rb").read()):
    tables.append(cl.analyze_grid("t1", file, sheet, grid))

series  = cl.build_series(tables)
names   = {s.key: s.base for s in series}
aggs    = {s.key: cl.default_agg(s.base) for s in series}
include = {s.key: True for s in series}

res = cl.align_and_correlate(series, names, aggs, include, groups=[])
print(res.matrix.round(2))          # correlation matrix
print(res.nmat, res.pmat)           # periods used, p-values
for card in cl.findings(res, target=None, method="pearson", mode="level"):
    print(card["kind"], card["text"])
```

## Sharing it with other people

- **Streamlit Community Cloud** (free): push this folder to a GitHub repo and deploy it. Good for
  non-confidential data, since anyone with the link can use the app.
- **Internally**: run it on a server with `streamlit run app.py --server.port 8501`, or containerise
  it. Behind a VPN or SSO this keeps client data inside your network.
- **Locally**: each person runs it on their own machine; nothing leaves the laptop.

Uploaded data lives only in that user's session and is never written to disk.

## Known limits

- Very wide exports (hundreds of series) load with the first 24 switched on, to keep the matrix
  readable. Turn others on in step 4.
- Tables where several dimensions are stacked without a "Total" row (local *and* national spend in
  one file, say) can double-count. Set a filter in step 1.
- Reading a large Excel file (10 MB+) takes several seconds; it is parsed once per upload.
- Correlation is not causation, and the app says so — it is for finding leads worth testing.
