"""
Correlation Lab: Streamlit front end. Aligns marketing data from different
sources and shows which series move together.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import html
import io
import uuid

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import corrlab as cl

# Crossmedia palette. To re-theme, change these, the CSS below and .streamlit/config.toml.
RED = "#E4002B"        # Crossmedia red: accents, positive correlation, created series
CHARCOAL = "#2B2B2B"   # headings, uploaded series
SLATE = "#6B7178"      # negative correlation
GRID = "#E6E6E6"       # chart gridlines

st.set_page_config(page_title="Correlation Lab", layout="wide")

st.markdown("""
<style>
  .block-container {padding-top: 3.6rem; max-width: 1400px;}
  h1, h2, h3 {letter-spacing: -0.01em; color: #2B2B2B;}
  .step-no {font-size: 0.72rem; font-weight: 700; letter-spacing: .12em;
            text-transform: uppercase; color: #E4002B;}
  .why {color: #4A4A4A; max-width: 78ch;}
  .k {font-size: .68rem; font-weight: 700; letter-spacing: .08em;
      text-transform: uppercase; color: #E4002B; margin-bottom: .2rem;}
  .tag {display: inline-block; min-width: 3.2rem; font-size: .64rem; font-weight: 700; letter-spacing: .06em;
        text-transform: uppercase; text-align: center; padding: 0 .35rem; margin-right: .5rem;
        border-radius: 3px; border: 1px solid currentColor; vertical-align: 1px;}
  .tag.info {color: #6B7178;}
  .tag.did {color: #2B2B2B;}
  .tag.warn {color: #E4002B;}
  .note {background: #F4F4F4; border-left: 3px solid #E4002B; border-radius: 4px; padding: .7rem 1rem;
         margin-bottom: 1rem; color: #2B2B2B;}
  .stat {background: #F4F4F4; border-left: 3px solid #E4002B; border-radius: 4px; padding: .5rem .7rem; margin-bottom: 1rem;}
  .stat .l {font-size: .7rem; text-transform: uppercase; letter-spacing: .06em; color: #6B7178;}
  .stat .v {font-family: ui-monospace, monospace; font-size: 1.35rem; color: #2B2B2B;}
  .stat .d {font-size: .76rem; color: #4A4A4A; line-height: 1.25;}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------- state
S = st.session_state
S.setdefault("tables", [])
S.setdefault("seen_files", set())
S.setdefault("names", {})
S.setdefault("aggs", {})
S.setdefault("include", {})
S.setdefault("groups", [])
S.setdefault("target", "")
S.setdefault("pair", None)
S.setdefault("sample_loaded", False)


def load_sample():
    S.tables, S.seen_files, S.names, S.aggs, S.include, S.groups = [], set(), {}, {}, {}, []
    S.target, S.pair = "", None
    for file, sheet, grid in cl.make_sample():
        t = cl.analyze_grid(f"t{uuid.uuid4().hex[:6]}", file, sheet, grid, sample=True)
        S.tables.append(t)
    S.sample_loaded = True
    series = cl.build_series(S.tables)
    init_meta(series)
    search = [s.key for s in series if s.table.file == "search_trends.xlsx"]
    if search:
        S.groups.append(cl.ShareGroup(f"g{uuid.uuid4().hex[:6]}", "Search", search))
    orders = next((s for s in series if s.base == "Orders"), None)
    if orders:
        S.target = S.names.get(orders.key, orders.base)


def memo(slot: str, sig, fn):
    """Reuse the last result in `slot` while `sig` is unchanged.

    Streamlit reruns the whole script on every click, so without this the
    alignment, correlations and Excel file would be rebuilt each time.
    """
    box = S.setdefault("_memo", {})
    hit = box.get(slot)
    if hit is not None and hit[0] == sig:
        return hit[1]
    val = fn()
    box[slot] = (sig, val)
    return val


def init_meta(series):
    """Give any new series a display name, a way to combine it, and an on/off switch."""
    on = sum(1 for v in S.include.values() if v)
    for s in series:
        if s.key not in S.names:
            S.names[s.key] = s.base
            S.aggs[s.key] = cl.default_agg(s.base)
            S.include[s.key] = on < 24
            on += 1
    # names must stay unique, otherwise columns collide when lined up
    seen = {}
    for s in series:
        nm = S.names[s.key]
        if nm in seen and seen[nm] != s.key:
            S.names[s.key] = f"{nm} ({s.table.tag})"
        seen[S.names[s.key]] = s.key


if not S.tables and not S.sample_loaded:
    load_sample()

# ---------------------------------------------------------------- header
left, right = st.columns([1.35, 1])
with left:
    st.markdown("<div class='step-no'>Correlation Lab</div>", unsafe_allow_html=True)
    st.title("Which metrics move together")
    st.markdown("<p class='why'>Upload exports from different tools. The app lines the series up by date, "
                "builds share metrics such as Share of Search, and reports which series are correlated and how "
                "strongly.</p>", unsafe_allow_html=True)
with right:
    rng = np.random.default_rng(3)
    demo = go.Figure()
    for k, (rho, title) in enumerate([(0.9, "r = +0.9<br>rise together"), (0.0, "r = 0<br>no pattern"),
                                      (-0.85, "r = -0.85<br>move opposite")]):
        x = rng.standard_normal(34)
        y = rho * x + np.sqrt(1 - rho ** 2) * rng.standard_normal(34)
        demo.add_trace(go.Scatter(x=x + k * 8, y=y, mode="markers", marker=dict(size=6, color=RED, opacity=.85),
                                  hoverinfo="skip", showlegend=False))
        demo.add_annotation(x=k * 8, y=-4.4, text=title, showarrow=False, font=dict(size=11, color=CHARCOAL))
    demo.update_layout(height=190, margin=dict(l=0, r=0, t=6, b=0), plot_bgcolor="rgba(0,0,0,0)",
                       paper_bgcolor="rgba(0,0,0,0)", xaxis=dict(visible=False), yaxis=dict(visible=False, range=[-5.6, 3.4]))
    st.plotly_chart(demo, width="stretch", config={"displayModeBar": False})

# ---------------------------------------------------------------- step 1: data
st.markdown("<div class='step-no'>Step 1</div>", unsafe_allow_html=True)
st.header("Bring your data")
st.markdown("<p class='why'>Upload as many CSV or Excel files as you like; each Excel tab is read separately. Every "
            "table needs a date column and at least one numeric column. Long tables (one row per brand or "
            "channel) are split into separate series.</p>", unsafe_allow_html=True)

up_col, btn_col = st.columns([3, 1])
with up_col:
    uploads = st.file_uploader("Upload files", type=["csv", "tsv", "txt", "xlsx", "xlsm", "xls"],
                               accept_multiple_files=True, label_visibility="collapsed")
with btn_col:
    if st.button("Load the example", width="stretch"):
        load_sample()
        st.rerun()
    if st.button("Clear all", width="stretch"):
        S.tables, S.seen_files, S.names, S.aggs, S.include, S.groups = [], set(), {}, {}, {}, []
        S.target, S.pair, S.sample_loaded = "", None, True
        st.rerun()

if uploads:
    fresh = [u for u in uploads if u.file_id not in S.seen_files]
    if fresh:
        if any(t.sample for t in S.tables):        # first real upload replaces the example
            S.tables, S.names, S.aggs, S.include, S.groups = [], {}, {}, {}, []
            S.target, S.pair = "", None
        with st.spinner("Reading files..."):
            for u in fresh:
                S.seen_files.add(u.file_id)
                try:
                    for file, sheet, grid in cl.read_upload(u.name, u.getvalue()):
                        S.tables.append(cl.analyze_grid(f"t{uuid.uuid4().hex[:6]}", file, sheet, grid))
                except Exception as exc:                       # noqa: BLE001
                    t = cl.Table(tid=f"t{uuid.uuid4().hex[:6]}", file=u.name, sheet=None)
                    t.skip = f"This file couldn't be read: {exc}"
                    S.tables.append(t)
        st.rerun()

if any(t.sample for t in S.tables):
    st.markdown("<div class='note'><b>Example data.</b> A fictional granola brand, Harbor Crunch, and three "
                "fictional competitors. Uploading your own files replaces it.</div>", unsafe_allow_html=True)

if not S.tables:
    st.warning("No data yet. Upload files or load the example.")

for t in S.tables:
    if t.skip:
        with st.expander(f"{t.label} (skipped)", expanded=False):
            st.caption(t.skip)
            if st.button("Remove", key=f"rm{t.tid}"):
                S.tables.remove(t)
                st.rerun()
        continue
    head = (f"**{t.label}** | {'long' if t.long else 'wide'} format | {cl.FREQ_WORD[t.freq]} | "
            f"{len(t.frame):,} rows | {t.frame['__date'].min():%b %Y} to {t.frame['__date'].max():%b %Y}"
            f"{' | example' if t.sample else ''}")
    with st.expander(head, expanded=False):
        if t.date_order == "mdy-assumed":
            opts = ["Month first (05/01 = May 1)", "Day first (05/01 = 5 January)"]
            pick = st.radio("Dates like 05/01/2026 mean", opts, index=1 if t.day_first else 0,
                            key=f"do{t.tid}", horizontal=True,
                            help="Every date in this table fits both readings, so the app can't tell which one "
                                 "the export uses.")
            if (pick == opts[1]) != t.day_first:
                cl.set_day_first(t, pick == opts[1])
                st.rerun()
        if t.long and t.text_cols:
            names = [c["name"] for c in t.text_cols]
            picked = st.multiselect("Split into separate series by", names,
                                    default=[names[i] for i in t.split if i < len(names)], key=f"sp{t.tid}")
            t.split = [names.index(p) for p in picked]
            rest = [i for i in range(len(t.text_cols)) if i not in t.split]
            if rest:
                st.caption("For the other columns, use")
                cols = st.columns(min(3, len(rest)))
                for n, i in enumerate(rest):
                    opts = ["All rows, added together"] + t.text_cols[i]["values"][:300]
                    cur = t.filters.get(i, "__all")
                    idx = 0 if cur == "__all" else (opts.index(cur) if cur in opts else 0)
                    with cols[n % len(cols)]:
                        choice = st.selectbox(t.text_cols[i]["name"], opts, index=idx, key=f"f{t.tid}_{i}")
                    t.filters[i] = "__all" if choice == opts[0] else choice
        if len(t.num_cols) > 1:
            nnames = [c["name"] for c in t.num_cols]
            picked = st.multiselect("Number columns to use", nnames,
                                    default=[nnames[i] for i in t.use_num if i < len(nnames)], key=f"nc{t.tid}")
            t.use_num = [nnames.index(p) for p in picked]
        if st.button("Remove this table", key=f"rm{t.tid}"):
            S.tables.remove(t)
            st.rerun()

table_sig = tuple((t.tid, t.skip, tuple(t.split), tuple(sorted(t.filters.items())), tuple(t.use_num), t.day_first)
                  for t in S.tables)
series = memo("series", table_sig, lambda: cl.build_series(S.tables))
init_meta(series)
key_of = {S.names[s.key]: s.key for s in series}

# ---------------------------------------------------------------- step 2: settings
st.divider()
st.markdown("<div class='step-no'>Step 2</div>", unsafe_allow_html=True)
st.header("Line it up")
st.markdown("<p class='why'>You can only compare two numbers if they describe the same stretch of time. These "
            "settings put everything on one shared calendar.</p>", unsafe_allow_html=True)

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    grain = st.selectbox("Time grain", ["auto", "week", "month", "quarter"], index=0,
                         format_func=lambda g: "Auto" if g == "auto" else cl.FREQ_WORD[g].title(),
                         help="Weekly and monthly data can't be compared directly, so everything is rolled up to one "
                              "speed. Auto picks the slowest one you have.")
with c2:
    mode = st.selectbox("Compare", ["level", "pct"], index=0,
                        format_func=lambda m: "Levels" if m == "level" else "% change",
                        help="Levels compares the raw numbers. % change compares how much each moved from one period "
                             "to the next, which removes long-term trends that can make unrelated things look linked.")
with c3:
    method = st.selectbox("Method", ["pearson", "spearman"], index=0, format_func=str.title,
                          help="Pearson looks for straight-line relationships. Spearman ranks the values first, so "
                               "outliers matter less and it catches curved but consistent relationships.")
with c4:
    overlap = st.selectbox("Which periods", ["pair", "common"], index=0,
                           format_func=lambda o: "Each pair's overlap" if o == "pair" else "Shared window",
                           help="Each pair's overlap uses the most data per pair. Shared window uses only periods "
                                "where every series has a value.")
with c5:
    exclude_future = st.checkbox("Leave out unfinished periods", value=True,
                                 help="Some exports include forecasts for future months. Those aren't real data.")

res_sig = (table_sig, tuple(sorted(S.names.items())), tuple(sorted(S.aggs.items())),
           tuple(sorted(S.include.items())), tuple((g.gid, g.label, tuple(g.members)) for g in S.groups),
           grain, mode, method, overlap, exclude_future, pd.Timestamp.now().date())
res = memo("res", res_sig, lambda: cl.align_and_correlate(
    series, S.names, S.aggs, S.include, S.groups, grain=grain, mode=mode, method=method,
    overlap=overlap, exclude_future=exclude_future))
labels = list(res.matrix.columns)
G = cl.GRAIN_NOUN[res.grain]

log_col, cov_col = st.columns([1, 1])
with log_col:
    st.subheader("Processing log")
    tag = {"info": "Note", "did": "Done", "warn": "Check"}
    for entry in res.log:
        # log lines contain file, sheet and column names from uploads, so escape them
        st.markdown(f"<span class='tag {entry['kind']}'>{tag[entry['kind']]}</span>"
                    f"{html.escape(entry['text'], quote=False)}", unsafe_allow_html=True)
with cov_col:
    st.subheader("When each series has data")
    st.caption("Dark bars are uploaded series; red bars are shares created in step 3. The shaded band is the "
               "window where every series has data.")
    if labels:
        rows = []
        for lab in labels[:40]:
            s = res.levels[lab].dropna()
            if len(s):
                rows.append(dict(Series=lab[:38], Start=s.index[0].start_time,
                                 End=s.index[-1].end_time, Kind="Created" if res.meta[lab].get("share") else "Uploaded"))
        cov = go.Figure()
        for i, r in enumerate(rows):
            cov.add_trace(go.Scatter(x=[r["Start"], r["End"]], y=[i, i], mode="lines",
                                     line=dict(color=RED if r["Kind"] == "Created" else CHARCOAL, width=9),
                                     hovertemplate=f"{r['Series']}<br>%{{x|%b %Y}}<extra></extra>", showlegend=False))
        if res.common:
            cov.add_vrect(x0=res.common[0].start_time, x1=res.common[1].end_time,
                          fillcolor=RED, opacity=0.06, line_width=0)
        cov.update_layout(height=max(180, 22 * len(rows) + 40), margin=dict(l=0, r=10, t=10, b=10),
                          yaxis=dict(tickmode="array", tickvals=list(range(len(rows))),
                                     ticktext=[r["Series"] for r in rows], autorange="reversed"),
                          xaxis=dict(showgrid=True, gridcolor=GRID),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(cov, width="stretch", config={"displayModeBar": False})

# ---------------------------------------------------------------- step 3: shares
st.divider()
st.markdown("<div class='step-no'>Step 3</div>", unsafe_allow_html=True)
st.header("Create new series")
st.markdown("<p class='why'>Some useful measures aren't in the raw data. The most common is a <b>share</b>: one "
            "brand's number divided by the total for all brands in the same period. Share of Search, Share of "
            "Conversation and Share of Voice (spend) are all built this way, and they cancel out things that affect "
            "everyone, like seasons and holidays.</p>", unsafe_allow_html=True)

sugg = cl.suggest_shares(series, S.names, S.groups)
if sugg:
    st.caption("Suggested from your data")
    cols = st.columns(min(4, len(sugg[:8])))
    for i, g in enumerate(sugg[:8]):
        with cols[i % len(cols)]:
            if st.button(f"Add Share of {g['label']}", key=f"sg{i}", help=f"{len(g['members'])} series from {g['from']}"):
                S.groups.append(cl.ShareGroup(f"g{uuid.uuid4().hex[:6]}", g["label"], g["members"]))
                st.rerun()

for g in S.groups:
    c1, c2, c3 = st.columns([2, 5, 1])
    with c1:
        new_label = st.text_input("Share of", g.label, key=f"gl{g.gid}", label_visibility="collapsed")
        if new_label != g.label:           # the results above were built with the old label
            g.label = new_label
            st.rerun()
    with c2:
        st.caption(f"{len(g.members)} series: " + ", ".join(S.names.get(k, k) for k in g.members)[:110])
    with c3:
        if st.button("Remove", key=f"gr{g.gid}"):
            S.groups = [x for x in S.groups if x.gid != g.gid]
            st.rerun()

with st.expander("Build a share from any series you pick"):
    label = st.text_input("What is it a share of? (e.g. Conversation)", key="blabel")
    picked = st.multiselect("Series in this group", [S.names[s.key] for s in series], key="bpick")
    if st.button("Create share series") and len(picked) >= 2:
        S.groups.append(cl.ShareGroup(f"g{uuid.uuid4().hex[:6]}", label or "Total", [key_of[p] for p in picked]))
        st.rerun()

# ---------------------------------------------------------------- step 4: series
st.divider()
st.markdown("<div class='step-no'>Step 4</div>", unsafe_allow_html=True)
st.header("Choose and rename series")
st.markdown("<p class='why'>Tick the series to include and <b>give them clear, consistent names</b>. If one file "
            "says \"Hellman's\" and another says \"Hellmann's\", use the same spelling in both so related series are "
            "easy to spot in the charts. Each series keeps its own name: series are never merged, so if you choose "
            "a name that's already taken, the source is added in brackets. When periods are rolled up, counts and "
            "spend are summed; rates, scores and percentages are averaged.</p>", unsafe_allow_html=True)

editor_df = pd.DataFrame([{
    "Use": S.include.get(s.key, False),
    "Name": S.names[s.key],
    "Combine by": "Average" if S.aggs.get(s.key, "sum") == "mean" else "Add up",
    "Source": s.table.label,
    "Values": f"{len(s.data)} {cl.FREQ_WORD[s.freq]}",
    "Covers": f"{s.data.index.min():%b %Y} to {s.data.index.max():%b %Y}",
    "_key": s.key,
} for s in series])

if len(editor_df):
    edited = st.data_editor(
        editor_df, hide_index=True, width="stretch", height=min(430, 60 + 36 * len(editor_df)),
        column_config={
            "Use": st.column_config.CheckboxColumn(width="small"),
            "Name": st.column_config.TextColumn(width="large"),
            "Combine by": st.column_config.SelectboxColumn(options=["Add up", "Average"], width="small"),
            "Source": st.column_config.TextColumn(disabled=True),
            "Values": st.column_config.TextColumn(disabled=True, width="small"),
            "Covers": st.column_config.TextColumn(disabled=True),
            "_key": None,
        }, key=f"series_editor{S.get('editor_ver', 0)}")
    changed = False
    owner = {S.names[s.key]: s.key for s in series}
    tag_of = {s.key: s.table.tag for s in series}
    for _, row in edited.iterrows():
        k = row["_key"]
        if S.include.get(k) != bool(row["Use"]):
            S.include[k] = bool(row["Use"])
            changed = True
        new_name = str(row["Name"]).strip()
        if new_name and S.names.get(k) != new_name:
            if owner.get(new_name, k) != k:          # another series already has this name
                typed, new_name = new_name, f"{new_name} ({tag_of[k]})"
                if S.names.get(k) != new_name:
                    S.flash = (f"\"{typed}\" is already used by another series, so this one was named "
                               f"\"{new_name}\". Series are never merged; each one needs its own name.")
                    S.editor_ver = S.get("editor_ver", 0) + 1     # redraw the table with the real names
            if S.names.get(k) != new_name:
                owner.pop(S.names.get(k), None)
                owner[new_name] = k
                S.names[k] = new_name
                changed = True
        agg = "mean" if row["Combine by"] == "Average" else "sum"
        if S.aggs.get(k) != agg:
            S.aggs[k] = agg
            changed = True
    if changed:
        st.rerun()
    if S.get("flash"):
        st.warning(S.pop("flash"))
    n_on =sum(1 for x in series if S.include.get(x.key))
    n_created = sum(1 for l in labels if res.meta.get(l, {}).get("share"))
    st.caption(f"{n_on} of {len(series)} uploaded series included"
               + (f", plus {n_created} created in step 3." if n_created else "."))

# ---------------------------------------------------------------- step 5: goal & findings
st.divider()
st.markdown("<div class='step-no'>Step 5</div>", unsafe_allow_html=True)
st.header("Goal metric and findings")
st.markdown("<p class='why'>Pick the metric you care about most (sales, sign-ups, awareness) to rank every other "
            "series by how closely it tracks it. With no goal set, the strongest pairs overall are shown.</p>",
            unsafe_allow_html=True)

NO_GOAL = "None (show strongest pairs)"
target = st.selectbox("Goal metric", [NO_GOAL] + labels,
                      index=(labels.index(S.target) + 1) if S.target in labels else 0)
S.target = "" if target == NO_GOAL else target
target_key = S.target or None

rank_col, card_col = st.columns([1.2, 1])
items = cl.ranked_pairs(res, target_key) if labels else []
with rank_col:
    st.subheader(f"Correlation with {target_key}" if target_key else "Strongest pairs")
    st.caption("Longer bars mean a closer link. Red bars move in the same direction, grey bars in opposite "
               "directions. Faded bars may be chance (p ≥ 0.05).")
    top = items[:12]
    if top:
        names_ = [(it["a"] if target_key else f"{it['a']} vs {it['b']}") for it in top][::-1]
        vals = [it["r"] for it in top][::-1]
        ps = [it["p"] for it in top][::-1]
        ns = [it["n"] for it in top][::-1]
        bar = go.Figure(go.Bar(
            x=vals, y=[f"{n[:52]} " for n in names_], orientation="h",
            marker=dict(color=[RED if v >= 0 else SLATE for v in vals],
                        opacity=[1 if p < 0.05 else 0.45 for p in ps]),
            text=[f"{v:+.2f}" for v in vals], textposition="outside",
            customdata=np.stack([ns, ps], axis=-1),
            hovertemplate="r = %{x:.2f}<br>%{customdata[0]} " + G + "s, p = %{customdata[1]:.3f}<extra></extra>"))
        bar.update_layout(height=max(240, 34 * len(top)), margin=dict(l=0, r=30, t=6, b=6),
                          xaxis=dict(range=[-1.15, 1.15], zeroline=True, zerolinecolor="#BDBDBD",
                                     gridcolor=GRID, title="correlation (r)"),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(bar, width="stretch", config={"displayModeBar": False})
    else:
        st.info("Select at least two series with overlapping dates.")
with card_col:
    cards = memo("cards", (res_sig, target_key),
                 lambda: cl.findings(res, target_key, method, mode) if labels else [])
    for card in cards:
        with st.container(border=True):
            st.markdown(f"<div class='k'>{card['kind']}</div>", unsafe_allow_html=True)
            if card["tone"] == "warn":
                st.warning(card["text"])
            else:
                st.markdown(card["text"])

# ---------------------------------------------------------------- step 6: matrix
st.divider()
st.markdown("<div class='step-no'>Step 6</div>", unsafe_allow_html=True)
st.header("Correlation matrix")
st.markdown("<p class='why'>Every series compared with every other. Each cell is the <b>r</b> for that pair: red "
            "means they rise together, grey means one rises as the other falls, white means no clear link. The "
            "grid is symmetric, so only the lower half is shown. <b>Click a cell</b> to open that pair below.</p>",
            unsafe_allow_html=True)

if len(labels) >= 2:
    order = labels
    if target_key:
        order = [target_key] + sorted([l for l in labels if l != target_key],
                                      key=lambda l: -abs(res.matrix.at[l, target_key]
                                                         if np.isfinite(res.matrix.at[l, target_key]) else 0))
    M = res.matrix.loc[order, order].copy()
    N = res.nmat.loc[order, order]
    P = res.pmat.loc[order, order]
    tri = np.triu(np.ones(M.shape, dtype=bool), 1)      # hide the repeated half
    Z = M.mask(tri)
    text = Z.map(lambda v: "" if pd.isna(v) else f"{v:.2f}")
    short = [f"{i+1}. {l[:34]}" for i, l in enumerate(order)]
    heat = go.Figure(go.Heatmap(
        z=Z.values, x=[str(i + 1) for i in range(len(order))], y=short,
        colorscale=[[0, SLATE], [0.5, "#FFFFFF"], [1, RED]], zmid=0, zmin=-1, zmax=1, xgap=2, ygap=2,
        text=text.values, texttemplate="%{text}", textfont=dict(size=10),
        customdata=np.dstack([N.values, P.values]),
        hovertemplate="r = %{z:.2f}<br>%{y} vs column %{x}<br>%{customdata[0]} " + G +
                      "s, p = %{customdata[1]:.3f}<extra></extra>",
        colorbar=dict(title="r", thickness=12)))
    heat.update_layout(height=max(360, 30 * len(order) + 120), margin=dict(l=0, r=0, t=10, b=10),
                       xaxis=dict(side="top", tickfont=dict(size=10)), yaxis=dict(autorange="reversed"),
                       plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    ev = st.plotly_chart(heat, width="stretch", on_select="rerun", key="mx",
                         config={"displayModeBar": False})
    try:
        pts = ev["selection"]["points"]
        if pts:
            row = int(pts[0]["y"].split(".")[0]) - 1
            col = int(pts[0]["x"]) - 1
            if row != col:
                S.pair = (order[col], order[row])
    except Exception:                                    # noqa: BLE001
        pass

    st.subheader("Pair detail")
    if not S.pair or S.pair[0] not in labels or S.pair[1] not in labels:
        S.pair = (items[0]["a"], items[0]["b"]) if items else (labels[0], labels[1])
    pa, pb = st.columns(2)
    with pa:
        a = st.selectbox("Series A", labels, index=labels.index(S.pair[0]))
    with pb:
        b = st.selectbox("Series B", labels, index=labels.index(S.pair[1]))
    S.pair = (a, b)

    r, n, p, n_eff = cl.corr_pair(res.values[a], res.values[b], method=method, full=True)
    if not np.isfinite(r):
        st.warning(f"These two only overlap for {n} {G}s, which isn't enough to compare.")
    else:
        alt_a, alt_b = (res.levels, res.levels) if mode == "pct" else (res.pct, res.pct)
        r_alt, _, _ = cl.corr_pair(alt_a[a], alt_b[b], method=method)
        s1, s2, s3, s4 = st.columns(4)
        for col, l, v, d in [
            (s1, "r", f"{r:+.2f}", f"{cl.strength_word(r).replace('a ', '').replace('an ', '')}"
                                   f"{', same direction' if r > 0 else ', opposite directions' if abs(r) >= .1 else ''}"),
            (s2, "r²", f"{round(r*r*100)}%", "of the variation is shared"),
            (s3, "p-value", "-" if not np.isfinite(p) else f"{p:.3f}" if p >= 0.001 else "<0.001",
             "too little data to judge" if not np.isfinite(p) else
             "probably not chance" if p < 0.05 else "could be chance"),
            (s4, "n", f"{n}", f"{G}s compared"
             + (f", worth about {n_eff:.0f} independent ones" if np.isfinite(n_eff) and n_eff < n - 0.5 else ""))]:
            col.markdown(f"<div class='stat'><div class='l'>{l}</div><div class='v'>{v}</div>"
                         f"<div class='d'>{d}</div></div>", unsafe_allow_html=True)

        plain = ("These two don't move together in any consistent way." if abs(r) < 0.1 else
                 f"When **{a}** is higher than usual, **{b}** tends to be higher too." if r > 0 else
                 f"When **{a}** is higher than usual, **{b}** tends to be lower.")
        st.markdown(f"\n**Summary:** {plain} About **{round(r*r*100)}%** of the variation in one lines up "
                    f"with the other; the other {100-round(r*r*100)}% comes from things not in this pair. "
                    f"With {n} {G}s, this result is {cl.p_words(p, n)}."
                    + (f"\n\nCheck: comparing {'raw levels' if mode == 'pct' else '% changes'} instead gives "
                       f"r = {r_alt:+.2f}."
                       f"{' Much of the link may come from a shared trend rather than moves that line up.' if mode == 'level' and np.isfinite(r_alt) and abs(r_alt) < abs(r) - 0.3 else ''}"
                       if np.isfinite(r_alt) else ""))

        g1, g2 = st.columns(2)
        with g1:
            d = cl.pair_points(res, a, b)
            sc = go.Figure(go.Scatter(x=d["x"], y=d["y"], mode="markers",
                                      marker=dict(size=9, color=RED, line=dict(width=1.5, color="white")),
                                      text=[cl.period_label(i, res.grain) for i in d.index],
                                      hovertemplate="%{text}<br>" + a[:30] + ": %{x:,.4g}<br>" + b[:30] +
                                                    ": %{y:,.4g}<extra></extra>"))
            if method == "pearson" and len(d) >= 3:
                sl, ic = np.polyfit(d["x"], d["y"], 1)
                xs = np.array([d["x"].min(), d["x"].max()])
                sc.add_trace(go.Scatter(x=xs, y=sl * xs + ic, mode="lines", hoverinfo="skip",
                                        line=dict(color=CHARCOAL, dash="dash", width=2), showlegend=False))
            sc.update_layout(height=340, margin=dict(l=0, r=6, t=30, b=0), showlegend=False,
                             title=dict(text=f"Each dot is one {G}", font=dict(size=14)),
                             xaxis=dict(title=a[:40], gridcolor=GRID),
                             yaxis=dict(title=b[:40], gridcolor=GRID),
                             plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(sc, width="stretch", config={"displayModeBar": False})
            st.caption("A band going up to the right means they rise together; down means opposite directions; "
                       "a shapeless cloud means no link.")
        with g2:
            z = lambda s: (s - s.mean()) / (s.std() or 1)
            t_idx = res.values.index.to_timestamp()
            tl = go.Figure()
            tl.add_trace(go.Scatter(x=t_idx, y=z(res.values[a]), name=a[:34], mode="lines",
                                    line=dict(color=CHARCOAL, width=2),
                                    customdata=res.values[a], hovertemplate="%{customdata:,.4g}<extra>" + a[:30] + "</extra>"))
            tl.add_trace(go.Scatter(x=t_idx, y=z(res.values[b]), name=b[:34], mode="lines",
                                    line=dict(color=RED, width=2),
                                    customdata=res.values[b], hovertemplate="%{customdata:,.4g}<extra>" + b[:30] + "</extra>"))
            tl.update_layout(height=340, margin=dict(l=0, r=6, t=30, b=0), hovermode="x unified",
                             title=dict(text="Both over time (rescaled to one axis)", font=dict(size=14)),
                             legend=dict(orientation="h", y=-0.18), yaxis=dict(title="vs average", gridcolor=GRID),
                             xaxis=dict(gridcolor=GRID),
                             plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(tl, width="stretch", config={"displayModeBar": False})
            st.caption("Each line is rescaled so both share one axis. Check whether the peaks and dips happen together.")

        lags = [(L,) + cl.corr_pair(res.values[a], res.values[b], lag=L, method=method) for L in range(-3, 4)]
        lab = [f"B {abs(L)} earlier" if L < 0 else "same " + G if L == 0 else f"A {L} earlier" for L, _, _, _ in lags]
        lg = go.Figure(go.Bar(x=lab, y=[x[1] for x in lags],
                              marker_color=[RED if np.isfinite(x[1]) and x[1] >= 0 else SLATE for x in lags],
                              text=[f"{x[1]:+.2f}" if np.isfinite(x[1]) else "" for x in lags],
                              textposition="outside",
                              hovertemplate="r = %{y:.2f}<extra></extra>"))
        lg.update_layout(height=240, margin=dict(l=0, r=6, t=30, b=0),
                         title=dict(text="Does one lead the other?", font=dict(size=14)),
                         yaxis=dict(range=[-1.2, 1.2], gridcolor=GRID, zerolinecolor="#BDBDBD"),
                         plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(lg, width="stretch", config={"displayModeBar": False})
        best = max((x for x in lags if np.isfinite(x[1]) and x[2] >= 6), key=lambda x: abs(x[1]), default=None)
        if best and best[0] != 0 and abs(best[1]) > abs(r) + 0.1:
            who = a if best[0] > 0 else b
            st.caption(f"The strongest link comes when **{who}** is shifted **{abs(best[0])} {G}"
                       f"{'s' if abs(best[0]) > 1 else ''} earlier** (r = {best[1]:+.2f}), so it may be a leading indicator.")
        rel = cl.related(res, a, b)
        notes = []
        if rel == "share":
            notes.append("One of these is calculated from the other, so they are linked by construction.")
        if rel == "sib":
            notes.append("These are shares of the same total, so they are partly forced to move in opposite directions.")
        if n < 12:
            notes.append(f"Only {n} {G}s overlap, so a few unusual periods can swing this result a lot.")
        if notes:
            st.warning(" ".join(notes))

    # ------------------------------------------------------------ downloads
    st.subheader("Downloads")
    d1, d2, d3 = st.columns(3)
    aligned = res.values.copy()
    aligned.index = [cl.period_label(p, res.grain) for p in aligned.index]
    aligned.index.name = "Period"
    d1.download_button("Aligned data (CSV)", aligned.to_csv().encode(), "aligned_data.csv", "text/csv",
                       width="stretch")
    d2.download_button("Correlation matrix (CSV)", res.matrix.round(3).to_csv().encode(),
                       "correlation_matrix.csv", "text/csv", width="stretch")
    def workbook() -> bytes:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            aligned.to_excel(xw, sheet_name="Aligned data")
            res.matrix.round(3).to_excel(xw, sheet_name="r")
            res.nmat.to_excel(xw, sheet_name="n (periods)")
            res.pmat.round(4).to_excel(xw, sheet_name="p-values")
            pd.DataFrame([{"Pair": f"{i['a']} vs {i['b']}", "r": round(i["r"], 3), "n": i["n"],
                           "p": round(i["p"], 4)} for i in items]).to_excel(xw, sheet_name="Ranked pairs", index=False)
        return buf.getvalue()

    d3.download_button("All results (Excel)", memo("xlsx", (res_sig, target_key), workbook), "correlation_lab.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
else:
    st.info("The matrix appears once at least two series are selected.")

# ---------------------------------------------------------------- glossary
st.divider()
st.header("Glossary")
gloss = {
    "Correlation": "How closely two numbers move together over time. It doesn't say *why* they move together.",
    "r (correlation coefficient)": "A score from -1 to +1. +1 means they always rise and fall together, 0 means no "
                                   "pattern, -1 means they always move in opposite directions. Roughly: 0.1 weak, "
                                   "0.3 moderate, 0.5 strong, 0.7+ very strong.",
    "r² (r-squared)": "r multiplied by itself, read as a percentage. r = 0.7 gives r² = 0.49, so about half of one "
                      "number's ups and downs line up with the other's.",
    "p-value": "How likely a pattern this strong would appear by pure luck if there were no real link. Below 0.05 is "
               "the usual bar for \"probably real\". With few data points, even a big r can fail it. Marketing "
               "numbers carry over from one period to the next, which makes ordinary p-values look too good, so "
               "the app adjusts for that. When many pairs are checked, about 1 in 20 unrelated ones still pass "
               "by luck.",
    "n": "How many periods were used for a pair. Under about 12, treat results as hints, not proof. When a series "
         "carries over from one period to the next, its periods are worth fewer independent points; the pair "
         "detail shows roughly how many.",
    "Lag / lead": "One thing may affect another later, e.g. ad spend this month raising searches next month. A lead "
                  "shows up when the correlation gets stronger after shifting one series.",
    "Share of Search / Conversation / Voice": "A brand's number divided by the category total in each period: search "
                                              "volume, social mentions or ad spend.",
    "Trend": "A steady rise or fall over the whole period. Two things that both grow over time look correlated even "
             "when unrelated. Switching to % change tests this.",
    "Pearson vs Spearman": "Pearson measures straight-line relationships. Spearman ranks values first, so it catches "
                           "consistent but curved relationships and resists outliers.",
    "Aligning (taxonomy & time)": "Making names match across files (\"Coke\" and \"Coca-Cola\") and putting every series on "
                                  "the same calendar over the same range.",
    "Correlation vs causation": "Things moving together doesn't prove one causes the other. A hidden third factor, "
                               "like the season, can drive both.",
}
gc = st.columns(3)
for i, (term, desc) in enumerate(gloss.items()):
    with gc[i % 3]:
        st.markdown(f"**{term}**  \n<span style='color:#4A4A4A;font-size:.9rem'>{desc}</span>", unsafe_allow_html=True)
