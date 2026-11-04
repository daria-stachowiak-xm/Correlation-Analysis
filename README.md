# Correlation Lab

A Streamlit app for comparing marketing data from different tools. Upload spreadsheets and it
lines the series up by date, builds share metrics (Share of Search, Share of Conversation,
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
can be in formats such as `2026-08-31`, `8/31/26`, `31/08/2026`, `Apr'23`, `Apr 2023` or `2026-Q3`.
For dates like `05/01/2026`, the app decides once per column whether the day or the month comes
first. If every date fits both readings, it assumes month first and lets you switch. Summary
tabs (for example MyTelescope's "Pie Chart") are skipped, and the app says why. Long tables, with
one row per brand, channel or market, are split into separate series. You choose the split and any
filters.

**2. Align.** All series are rolled up to one calendar (weekly, monthly or quarterly). Counts and
spend are summed; rates and scores are averaged. When weekly data is rolled up to months or
quarters, each week is spread over its 7 days first, so a week that crosses a month boundary is
split between the two and 5-week months don't look bigger than 4-week ones. Partly covered periods
are dropped, as are unfinished or forecast periods. A processing log records each step, and
a coverage chart shows the date range of every series.

**3. Create share series.** One-click suggestions for Share of Search, Conversation and Voice,
plus a builder for any group of series.

**4. Select and rename.** Choose which series to include and give them clear names, for example
the same brand spelling in every file ("Hellmann's" everywhere, rather than "Hellman's" in one
file). Series are never merged, so each needs its own name; if a name is taken, the source is
added in brackets. You can also switch a series between summing and averaging.

**5. Goal metric and findings.** Pick the metric you care about. Every other series is ranked by
its correlation with it, and summary cards flag leading indicators, trends, shared trends and
small samples.

**6. Matrix and pair detail.** A clickable correlation matrix. For the selected pair the app
shows r, r², the p-value and n with a short explanation of each, plus a scatter plot, both series
over time and a lead/lag check. Results download as CSV files or a single Excel workbook.

**About the p-values.** Marketing series carry over from one period to the next, so n months hold
less information than n independent points, and textbook p-values look too good. The app reduces
n to an effective sample size before computing p, using each series' correlation with its own
previous value. The pair detail shows roughly how many independent periods a pair is worth. When
many pairs are checked, a findings card estimates how many could pass p < 0.05 by luck, and a
leading indicator must clear a stricter bar because three lags are tried.

## Files

| File | Contents |
|---|---|
| `app.py` | Streamlit interface and Plotly charts. |
| `corrlab.py` | Engine: file reading, date parsing, alignment, shares, correlation, findings. It has no Streamlit imports, so it can be tested or used from a notebook. |
| `requirements.txt` | Dependencies. |
| `.streamlit/config.toml` | Theme colors and a 500 MB upload limit. |

## Colors

The app uses the Crossmedia palette: red `#E4002B` as the accent and for positive correlations,
charcoal `#2B2B2B` for text and uploaded series, and slate `#6B7178` for negative correlations.
The colors are set in three places, which should be kept in sync:

- the constants at the top of `app.py` (charts)
- the `<style>` block in `app.py` (labels and stat tiles)
- `.streamlit/config.toml` (buttons, checkboxes and other Streamlit widgets)

## Using the engine without the UI

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

## Deployment

- **Streamlit Community Cloud** (free): push this folder to a GitHub repo and deploy it. Anyone
  with the link can use the app, so only use it for non-confidential data.
- **Internal server**: run `streamlit run app.py --server.port 8501` on a server, or in a
  container. Behind a VPN or SSO, client data stays on your network.
- **Local**: each person runs the app on their own machine, and no data leaves it.

Uploaded data is held only in the user's session and is never written to disk.

## Known limitations

- Very wide exports (hundreds of series) load with only the first 24 series selected, to keep the
  matrix readable. You can select others in step 4.
- Tables that stack several dimensions without a "Total" row (local and national spend in one
  file, for example) can double-count. Set a filter in step 1 to avoid this.
- Large Excel files (10 MB and up) take several seconds to read. Each file is parsed once per
  upload, and results are reused until a setting or selection changes.
- Weekly dates are treated as the first day of the week. Exports labelled by week ending are
  shifted by up to six days, which matters little at monthly grain.
- Correlation does not show causation. Use the results to decide what to test.
