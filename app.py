"""
Correlation Lab - a Streamlit app that lines up messy marketing data and
explains which numbers move together, in plain English.

Run it with:  streamlit run app.py
"""
from __future__ import annotations

import io
import uuid

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import corrlab as cl

BLUE, ORANGE, INK = "#2a78d6", "#eb6834", "#434a59"

st.set_page_config(page_title="Correlation Lab", page_icon="📈", layout="wide")

st.markdown("""
<style>
  .block-container {padding-top: 2.2rem; max-width: 1400px;}
  h1, h2, h3 {letter-spacing: -0.01em;}
  .step-no {font-family: ui-monospace, monospace; font-size: 0.72rem; letter-spacing: .12em;
            text-transform: uppercase; color: #6b7280;}
  .why {color: #434a59; max-width: 78ch;}
  .card {border: 1px solid #e3e6ec; border-radius: 10px; padding: .7rem .9rem; margin-bottom: .6rem;
         background: var(--background-color);}
  .card .k {font-family: ui-monospace, monospace; font-size: .68rem; letter-spacing: .08em;
            text-transform: uppercase; color: #6b7280; margin-bottom: .2rem;}
  .card.warn {background: #fff6e2; border-color: #f0dcb0;}
  .card.accent {border-color: #c9cbf5;}
  .stat {background: #f1f3f7; border-radius: 9px; padding: .5rem .7rem;}
  .stat .l {font-size: .7rem; text-transform: uppercase; letter-spacing: .06em; color: #6b7280;}
  .stat .v {font-family: ui-monospace, monospace; font-size: 1.35rem;}
  .stat .d {font-size: .76rem; color: #434a59; line-height: 1.25;}
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
        S.target = cl.build_series(S.tables) and S.names.get(orders.key, orders.base)


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
    st.title("Find out which of your numbers move together")
    st.markdown("<p class='why'>Drop in spreadsheets from different tools. The app lines them up by name and by "
                "date, builds the extra measures you need (like Share of Search), and explains every result in "
                "plain English. No statistics background needed.</p>", unsafe_allow_html=True)
with right:
    rng = np.random.default_rng(3)
    demo = go.Figure()
    for k, (rho, title) in enumerate([(0.9, "r ≈ +0.9<br>rise together"), (0.0, "r ≈ 0<br>no pattern"),
                                      (-0.85, "r ≈ −0.85<br>one up, one down")]):
        x = rng.standard_normal(34)
        y = rho * x + np.sqrt(1 - rho ** 2) * rng.standard_normal(34)
        demo.add_trace(go.Scatter(x=x + k * 8, y=y, mode="markers", marker=dict(size=6, color=BLUE, opacity=.85),
                                  hoverinfo="skip", showlegend=False))
        demo.add_annotation(x=k * 8, y=-4.4, text=title, showarrow=False, font=dict(size=11, color=INK))
    demo.update_layout(height=190, margin=dict(l=0, r=0, t=6, b=0), plot_bgcolor="rgba(0,0,0,0)",
                       paper_bgcolor="rgba(0,0,0,0)", xaxis=dict(visible=False), yaxis=dict(visible=False, range=[-5.6, 3.4]))
    st.plotly_chart(demo, width="stretch", config={"displayModeBar": False})

# ---------------------------------------------------------------- step 1: data
st.markdown("<div class='step-no'>Step 1</div>", unsafe_allow_html=True)
st.header("Bring your data")
st.markdown("<p class='why'>Upload as many CSV or Excel files as you like; each Excel tab is read separately. Every "
            "table needs a date column and some number columns. Tables with one row per brand or channel "
            "(long format) are fine too - they get split into separate series.</p>", unsafe_allow_html=True)

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
        with st.spinner("Reading files…"):
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
    st.info("**You're looking at example data** for a made-up granola brand, Harbor Crunch, and three made-up "
            "competitors. Upload your own files and the example is replaced.")

if not S.tables:
    st.warning("No data yet. Upload files or load the example.")

for t in S.tables:
    if t.skip:
        with st.expander(f"⏭️ {t.label} — skipped", expanded=False):
            st.caption(t.skip)
            if st.button("Remove", key=f"rm{t.tid}"):
                S.tables.remove(t)
                st.rerun()
        continue
    head = (f"**{t.label}** · {'Long format' if t.long else 'Wide format'} · {cl.FREQ_WORD[t.freq]} · "
            f"{len(t.frame):,} rows · {t.frame['__date'].min():%b %Y} – {t.frame['__date'].max():%b %Y}"
            f"{' · example' if t.sample else ''}")
    with st.expander(head, expanded=False):
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

series = cl.build_series(S.tables)
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

res = cl.align_and_correlate(series, S.names, S.aggs, S.include, S.groups,
                             grain=grain, mode=mode, method=method, overlap=overlap,
                             exclude_future=exclude_future)
labels = list(res.matrix.columns)
G = cl.GRAIN_NOUN[res.grain]

log_col, cov_col = st.columns([1, 1])
with log_col:
    st.subheader("What I did to your data")
    icon = {"info": "ℹ️", "did": "✅", "warn": "⚠️"}
    for entry in res.log:
        st.markdown(f"{icon[entry['kind']]} {entry['text']}")
with cov_col:
    st.subheader("When each series has data")
    st.caption("Each bar shows when a series has data. Correlation only uses periods where both series have values.")
    if labels:
        rows = []
        for lab in labels[:40]:
            s = res.levels[lab].dropna()
            if len(s):
                rows.append(dict(Series=cl.fmt_num and lab[:38], Start=s.index[0].start_time,
                                 End=s.index[-1].end_time, Kind="Created" if res.meta[lab].get("share") else "Uploaded"))
        cov = go.Figure()
        for i, r in enumerate(rows):
            cov.add_trace(go.Scatter(x=[r["Start"], r["End"]], y=[i, i], mode="lines",
                                     line=dict(color=ORANGE if r["Kind"] == "Created" else BLUE, width=9),
                                     hovertemplate=f"{r['Series']}<br>%{{x|%b %Y}}<extra></extra>", showlegend=False))
        if res.common:
            cov.add_vrect(x0=res.common[0].start_time, x1=res.common[1].end_time,
                          fillcolor="#3a3fb3", opacity=0.07, line_width=0)
        cov.update_layout(height=max(180, 22 * len(rows) + 40), margin=dict(l=0, r=10, t=10, b=10),
                          yaxis=dict(tickmode="array", tickvals=list(range(len(rows))),
                                     ticktext=[r["Series"] for r in rows], autorange="reversed"),
                          xaxis=dict(showgrid=True, gridcolor="#eceef3"),
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
            if st.button(f"➕ Share of {g['label']}", key=f"sg{i}", help=f"{len(g['members'])} series from {g['from']}"):
                S.groups.append(cl.ShareGroup(f"g{uuid.uuid4().hex[:6]}", g["label"], g["members"]))
                st.rerun()

for g in S.groups:
    c1, c2, c3 = st.columns([2, 5, 1])
    with c1:
        g.label = st.text_input("Share of", g.label, key=f"gl{g.gid}", label_visibility="collapsed")
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
st.header("Choose what to compare, and name things consistently")
st.markdown("<p class='why'>Tick the series to include, and <b>rename them so names match across files</b> - if one "
            "file says “Hellman's” and another “Hellmann's”, give them the same name. Counts and money are added up "
            "when rolling periods together; rates, scores and percentages are averaged.</p>", unsafe_allow_html=True)

editor_df = pd.DataFrame([{
    "Use": S.include.get(s.key, False),
    "Name": S.names[s.key],
    "Combine by": "Average" if S.aggs.get(s.key, "sum") == "mean" else "Add up",
    "Source": s.table.label,
    "Values": f"{len(s.data)} {cl.FREQ_WORD[s.freq]}",
    "Covers": f"{s.data.index.min():%b %Y} – {s.data.index.max():%b %Y}",
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
        }, key="series_editor")
    changed = False
    for _, row in edited.iterrows():
        k = row["_key"]
        if S.include.get(k) != bool(row["Use"]):
            S.include[k] = bool(row["Use"])
            changed = True
        new_name = str(row["Name"]).strip()
        if new_name and S.names.get(k) != new_name:
            S.names[k] = new_name
            changed = True
        agg = "mean" if row["Combine by"] == "Average" else "sum"
        if S.aggs.get(k) != agg:
            S.aggs[k] = agg
            changed = True
    if changed:
        st.rerun()
    n_on = sum(1 for x in series if S.include.get(x.key))
    n_created = sum(1 for l in labels if res.meta.get(l, {}).get("share"))
    st.caption(f"{n_on} of {len(series)} uploaded series included"
               + (f", plus {n_created} created in step 3." if n_created else "."))

# ---------------------------------------------------------------- step 5: goal & findings
st.divider()
st.markdown("<div class='step-no'>Step 5</div>", unsafe_allow_html=True)
st.header("What do you want to find out?")
st.markdown("<p class='why'>Pick the number you care about most (sales, sign-ups, awareness) and everything else is "
            "ranked by how closely it moves with it. Or leave it open and see what stands out.</p>",
            unsafe_allow_html=True)

target = st.selectbox("My goal", ["Just show me what's interesting"] + labels,
                      index=(labels.index(S.target) + 1) if S.target in labels else 0)
S.target = "" if target.startswith("Just show me") else target
target_key = S.target or None

rank_col, card_col = st.columns([1.2, 1])
items = cl.ranked_pairs(res, target_key) if labels else []
with rank_col:
    st.subheader(f"What moves with {target_key}" if target_key else "Strongest links in your data")
    st.caption("Longer bars mean a closer link. Blue moves the same way, red the opposite way. "
               "Faded bars could be chance (p ≥ 0.05).")
    top = items[:12]
    if top:
        names_ = [(it["a"] if target_key else f"{it['a']} × {it['b']}") for it in top][::-1]
        vals = [it["r"] for it in top][::-1]
        ps = [it["p"] for it in top][::-1]
        ns = [it["n"] for it in top][::-1]
        bar = go.Figure(go.Bar(
            x=vals, y=[f"{n[:52]} " for n in names_], orientation="h",
            marker=dict(color=[BLUE if v >= 0 else "#e34948" for v in vals],
                        opacity=[1 if p < 0.05 else 0.45 for p in ps]),
            text=[f"{v:+.2f}" for v in vals], textposition="outside",
            customdata=np.stack([ns, ps], axis=-1),
            hovertemplate="r = %{x:.2f}<br>%{customdata[0]} " + G + "s · p = %{customdata[1]:.3f}<extra></extra>"))
        bar.update_layout(height=max(240, 34 * len(top)), margin=dict(l=0, r=30, t=6, b=6),
                          xaxis=dict(range=[-1.15, 1.15], zeroline=True, zerolinecolor="#c6ccd8",
                                     gridcolor="#eceef3", title="correlation (r)"),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(bar, width="stretch", config={"displayModeBar": False})
    else:
        st.info("Select at least two series with overlapping dates.")
with card_col:
    for card in (cl.findings(res, target_key, method, mode) if labels else []):
        with st.container(border=True):
            st.markdown(f"<div class='k'>{card['kind']}</div>", unsafe_allow_html=True)
            if card["tone"] == "warn":
                st.warning(card["text"])
            else:
                st.markdown(card["text"])

# ---------------------------------------------------------------- step 6: matrix
st.divider()
st.markdown("<div class='step-no'>Step 6</div>", unsafe_allow_html=True)
st.header("The correlation matrix")
st.markdown("<p class='why'>A grid comparing every series with every other. Each square is the <b>r</b> for that "
            "pair: blue means they rise together, red means one rises as the other falls, pale means no clear link. "
            "The grid is a mirror image, so only half is shown. <b>Click a square</b> to open that pair.</p>",
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
        colorscale="RdBu", zmid=0, zmin=-1, zmax=1, xgap=2, ygap=2,
        text=text.values, texttemplate="%{text}", textfont=dict(size=10),
        customdata=np.dstack([N.values, P.values]),
        hovertemplate="r = %{z:.2f}<br>%{y} × column %{x}<br>%{customdata[0]} " + G +
                      "s · p = %{customdata[1]:.3f}<extra></extra>",
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

    st.subheader("Look at one pair")
    if not S.pair or S.pair[0] not in labels or S.pair[1] not in labels:
        S.pair = (items[0]["a"], items[0]["b"]) if items else (labels[0], labels[1])
    pa, pb = st.columns(2)
    with pa:
        a = st.selectbox("Series A", labels, index=labels.index(S.pair[0]))
    with pb:
        b = st.selectbox("Series B", labels, index=labels.index(S.pair[1]))
    S.pair = (a, b)

    r, n, p = cl.corr_pair(res.values[a], res.values[b], method=method)
    if not np.isfinite(r):
        st.warning(f"These two only overlap for {n} {G}s, which isn't enough to compare.")
    else:
        alt_a, alt_b = (res.levels, res.levels) if mode == "pct" else (res.pct, res.pct)
        r_alt, _, _ = cl.corr_pair(alt_a[a], alt_b[b], method=method)
        s1, s2, s3, s4 = st.columns(4)
        for col, l, v, d in [
            (s1, "r", f"{r:+.2f}", f"{cl.strength_word(r).replace('a ', '').replace('an ', '')}"
                                   f"{', same direction' if r > 0 else ', opposite directions' if abs(r) >= .1 else ''}"),
            (s2, "r²", f"{round(r*r*100)}%", "of the ups and downs line up"),
            (s3, "p-value", f"{p:.3f}" if p >= 0.001 else "<0.001",
             "probably not chance" if p < 0.05 else "could be chance"),
            (s4, "n", f"{n}", f"{G}s compared")]:
            col.markdown(f"<div class='stat'><div class='l'>{l}</div><div class='v'>{v}</div>"
                         f"<div class='d'>{d}</div></div>", unsafe_allow_html=True)

        plain = ("these two don't move together in any consistent way." if abs(r) < 0.1 else
                 f"when **{a}** is higher than usual, **{b}** tends to be higher too." if r > 0 else
                 f"when **{a}** is higher than usual, **{b}** tends to be lower.")
        st.markdown(f"\n**In plain English:** {plain} About **{round(r*r*100)}%** of the variation in one lines up "
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
                                      marker=dict(size=9, color=BLUE, line=dict(width=1.5, color="white")),
                                      text=[cl.period_label(i, res.grain) for i in d.index],
                                      hovertemplate="%{text}<br>" + a[:30] + ": %{x:,.4g}<br>" + b[:30] +
                                                    ": %{y:,.4g}<extra></extra>"))
            if method == "pearson" and len(d) >= 3:
                sl, ic = np.polyfit(d["x"], d["y"], 1)
                xs = np.array([d["x"].min(), d["x"].max()])
                sc.add_trace(go.Scatter(x=xs, y=sl * xs + ic, mode="lines", hoverinfo="skip",
                                        line=dict(color=INK, dash="dash", width=2), showlegend=False))
            sc.update_layout(height=340, margin=dict(l=0, r=6, t=30, b=0), showlegend=False,
                             title=dict(text=f"Each dot is one {G}", font=dict(size=14)),
                             xaxis=dict(title=a[:40], gridcolor="#eceef3"),
                             yaxis=dict(title=b[:40], gridcolor="#eceef3"),
                             plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(sc, width="stretch", config={"displayModeBar": False})
            st.caption("A band going up to the right means they rise together; down means opposite directions; "
                       "a shapeless cloud means no link.")
        with g2:
            z = lambda s: (s - s.mean()) / (s.std() or 1)
            t_idx = res.values.index.to_timestamp()
            tl = go.Figure()
            tl.add_trace(go.Scatter(x=t_idx, y=z(res.values[a]), name=a[:34], mode="lines",
                                    line=dict(color=BLUE, width=2),
                                    customdata=res.values[a], hovertemplate="%{customdata:,.4g}<extra>" + a[:30] + "</extra>"))
            tl.add_trace(go.Scatter(x=t_idx, y=z(res.values[b]), name=b[:34], mode="lines",
                                    line=dict(color=ORANGE, width=2),
                                    customdata=res.values[b], hovertemplate="%{customdata:,.4g}<extra>" + b[:30] + "</extra>"))
            tl.update_layout(height=340, margin=dict(l=0, r=6, t=30, b=0), hovermode="x unified",
                             title=dict(text="Both over time (rescaled to one axis)", font=dict(size=14)),
                             legend=dict(orientation="h", y=-0.18), yaxis=dict(title="vs average", gridcolor="#eceef3"),
                             xaxis=dict(gridcolor="#eceef3"),
                             plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(tl, width="stretch", config={"displayModeBar": False})
            st.caption("Each line is rescaled so both share one axis. Check whether the peaks and dips happen together.")

        lags = [(L,) + cl.corr_pair(res.values[a], res.values[b], lag=L, method=method) for L in range(-3, 4)]
        lab = [f"B {abs(L)} earlier" if L < 0 else "same " + G if L == 0 else f"A {L} earlier" for L, _, _, _ in lags]
        lg = go.Figure(go.Bar(x=lab, y=[x[1] for x in lags],
                              marker_color=[BLUE if (x[1] or 0) >= 0 else "#e34948" for x in lags],
                              text=[f"{x[1]:+.2f}" if np.isfinite(x[1]) else "" for x in lags],
                              textposition="outside",
                              hovertemplate="r = %{y:.2f}<extra></extra>"))
        lg.update_layout(height=240, margin=dict(l=0, r=6, t=30, b=0),
                         title=dict(text="Does one lead the other?", font=dict(size=14)),
                         yaxis=dict(range=[-1.2, 1.2], gridcolor="#eceef3", zerolinecolor="#c6ccd8"),
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
    st.subheader("Take it with you")
    d1, d2, d3 = st.columns(3)
    aligned = res.values.copy()
    aligned.index = [cl.period_label(p, res.grain) for p in aligned.index]
    aligned.index.name = "Period"
    d1.download_button("⬇️ Aligned data (CSV)", aligned.to_csv().encode(), "aligned_data.csv", "text/csv",
                       width="stretch")
    d2.download_button("⬇️ Correlation matrix (CSV)", res.matrix.round(3).to_csv().encode(),
                       "correlation_matrix.csv", "text/csv", width="stretch")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        aligned.to_excel(xw, sheet_name="Aligned data")
        res.matrix.round(3).to_excel(xw, sheet_name="r")
        res.nmat.to_excel(xw, sheet_name="n (periods)")
        res.pmat.round(4).to_excel(xw, sheet_name="p-values")
        pd.DataFrame([{"Pair": f"{i['a']} × {i['b']}", "r": round(i["r"], 3), "n": i["n"],
                       "p": round(i["p"], 4)} for i in items]).to_excel(xw, sheet_name="Ranked pairs", index=False)
    d3.download_button("⬇️ Everything (Excel)", buf.getvalue(), "correlation_lab.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
else:
    st.info("The matrix appears once at least two series are selected.")

# ---------------------------------------------------------------- glossary
st.divider()
st.header("Words you'll see")
gloss = {
    "Correlation": "How closely two numbers move together over time. It doesn't say *why* they move together.",
    "r (correlation coefficient)": "A score from −1 to +1. +1 means they always rise and fall together, 0 means no "
                                   "pattern, −1 means they always move in opposite directions. Roughly: 0.1 weak, "
                                   "0.3 moderate, 0.5 strong, 0.7+ very strong.",
    "r² (r-squared)": "r multiplied by itself, read as a percentage. r = 0.7 gives r² = 0.49, so about half of one "
                      "number's ups and downs line up with the other's.",
    "p-value": "How likely a pattern this strong would appear by pure luck if there were no real link. Below 0.05 is "
               "the usual bar for “probably real”. With few data points, even a big r can fail it.",
    "n": "How many periods were used for a pair. Under about 12, treat results as hints, not proof.",
    "Lag / lead": "One thing may affect another later, e.g. ad spend this month raising searches next month. A lead "
                  "shows up when the correlation gets stronger after shifting one series.",
    "Share of Search / Conversation / Voice": "A brand's number divided by the category total in each period: search "
                                              "volume, social mentions or ad spend.",
    "Trend": "A steady rise or fall over the whole period. Two things that both grow over time look correlated even "
             "when unrelated. Switching to % change tests this.",
    "Pearson vs Spearman": "Pearson measures straight-line relationships. Spearman ranks values first, so it catches "
                           "consistent but curved relationships and resists outliers.",
    "Aligning (taxonomy & time)": "Making names match across files (“Coke” = “Coca-Cola”) and putting every series on "
                                  "the same calendar over the same range.",
    "Correlation ≠ causation": "Things moving together doesn't prove one causes the other. A hidden third factor, "
                               "like the season, can drive both.",
}
gc = st.columns(3)
for i, (term, desc) in enumerate(gloss.items()):
    with gc[i % 3]:
        st.markdown(f"**{term}**  \n<span style='color:#434a59;font-size:.9rem'>{desc}</span>", unsafe_allow_html=True)
