"""
Correlation Lab - engine.

Everything that is not user interface lives here: reading messy spreadsheets,
working out which column holds the dates, lining several tables up on one
calendar, building share-of series, and measuring correlation.

The UI (app.py) only calls the functions in this file.
"""
from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime

import numpy as np
import pandas as pd
from scipy import stats

# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

MONTHS = {m.lower(): i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}
MONTHS.update({m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], start=1)})
MONTHS["sept"] = 9

DATEISH = re.compile(r"date|week|month|period|time|day|quarter|year|wk\b", re.I)
TOTALISH = re.compile(r"^(total|all|total us|us total|grand total|all markets|national|overall)$", re.I)
BRANDISH = re.compile(r"brand|advertiser|company|competitor|topic|bank|player", re.I)
METRICISH = re.compile(r"^(metric|measure|kpi|indicator)s?$", re.I)
MEANISH = re.compile(
    r"rate|%|pct|percent|share|score|index|aware|consider|recommend|likely|avg|average|mean|"
    r"ratio|nps|price|cpm|cpc|ctr|satisf|buzz|reputation|quality|positives|negatives|neutrals", re.I)

GRAIN_ORDER = ["day", "week", "month", "quarter", "year"]
FREQ_WORD = {"day": "daily", "week": "weekly", "month": "monthly", "quarter": "quarterly", "year": "yearly"}
GRAIN_NOUN = {"day": "day", "week": "week", "month": "month", "quarter": "quarter", "year": "year"}
PANDAS_FREQ = {"day": "D", "week": "W-SUN", "month": "M", "quarter": "Q", "year": "Y"}


def parse_date(v, allow_num: bool = False):
    """Turn almost anything that looks like a date into a pandas Timestamp."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, (pd.Timestamp, datetime, date)):
        try:
            ts = pd.Timestamp(v)
        except Exception:
            return None
        return None if pd.isna(ts) else ts.normalize().tz_localize(None)
    if isinstance(v, (int, float, np.integer, np.floating)):
        if allow_num and 25000 < float(v) < 80000:  # Excel serial number
            return pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(v))
        if allow_num and 1990 <= float(v) <= 2100 and float(v).is_integer():
            return pd.Timestamp(year=int(v), month=1, day=1)
        return None

    s = str(v).strip()
    if not s:
        return None

    def mk(y, m, d):
        y = int(y) + 2000 if int(y) < 100 else int(y)
        if not (1990 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31):
            return None
        try:
            return pd.Timestamp(year=y, month=int(m), day=int(d))
        except ValueError:
            return None

    m = re.match(r"^(\d{4})[-/.](\d{1,2})(?:[-/.](\d{1,2}))?(?:[T ].*)?$", s)
    if m:
        return mk(m.group(1), int(m.group(2)), int(m.group(3) or 1))
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})(?: .*)?$", s)
    if m:                                   # US style month/day/year
        a, b = int(m.group(1)), int(m.group(2))
        if a > 12:
            a, b = b, a
        return mk(m.group(3), a, b)
    m = re.match(r"^([A-Za-z]{3,9})\.?[\s'’\-_.,]*(\d{2}|\d{4})$", s)   # Apr'23, Apr 2023
    if m and m.group(1).lower() in MONTHS:
        return mk(m.group(2), MONTHS[m.group(1).lower()], 1)
    m = re.match(r"^(\d{1,2})[\s\-]([A-Za-z]{3,9})[\s\-,']*(\d{2,4})$", s)   # 5-Apr-2023
    if m and m.group(2).lower() in MONTHS:
        return mk(m.group(3), MONTHS[m.group(2).lower()], int(m.group(1)))
    m = re.match(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})$", s)         # Apr 5, 2023
    if m and m.group(1).lower() in MONTHS:
        return mk(m.group(3), MONTHS[m.group(1).lower()], int(m.group(2)))
    m = re.match(r"^(\d{4})\s*[-\s]?\s*Q([1-4])$", s, re.I)
    if m:
        return mk(m.group(1), (int(m.group(2)) - 1) * 3 + 1, 1)
    m = re.match(r"^Q([1-4])[\s\-']*(\d{2,4})$", s, re.I)
    if m:
        return mk(m.group(2), (int(m.group(1)) - 1) * 3 + 1, 1)
    return None


def to_num(v):
    """Turn '1,234', '$1.2', '(45)' or 12 into a float. Anything else -> None."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float, np.integer, np.floating)):
        return float(v)
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return None
    s = str(v).strip()
    if not s:
        return None
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    s = re.sub(r"[$€£¥,\s%]", "", s)
    if not re.match(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$", s):
        return None
    return -float(s) if neg else float(s)


def period_label(p, grain: str) -> str:
    """'Week of Sep 28, 2026', 'Aug 2026', 'Q3 2026' - never pandas' raw period text."""
    if p is None:
        return "–"
    try:
        start = p.start_time
    except AttributeError:
        return str(p)
    if grain == "week":
        return f"Week of {start:%b %-d, %Y}"
    if grain == "day":
        return f"{start:%b %-d, %Y}"
    if grain == "month":
        return f"{start:%b %Y}"
    if grain == "quarter":
        return f"Q{start.quarter} {start.year}"
    return f"{start.year}"


def detect_freq(dates: list) -> str:
    ds = sorted(set(pd.Timestamp(d) for d in dates))
    if len(ds) < 2:
        return "month"
    gaps = np.diff(np.array([d.value for d in ds])) / 86_400_000_000_000
    med = float(np.median(gaps))
    return ("day" if med <= 1.5 else "week" if med <= 8 else
            "month" if med <= 40 else "quarter" if med <= 100 else "year")


def fmt_num(v) -> str:
    if v is None or not np.isfinite(v):
        return "–"
    a = abs(v)
    if a >= 1e9:
        return f"{v/1e9:.1f}B"
    if a >= 1e6:
        return f"{v/1e6:.1f}M"
    if a >= 1e4:
        return f"{v/1e3:.0f}K"
    if a >= 1e3:
        return f"{v/1e3:.1f}K"
    if a >= 100:
        return f"{v:.0f}"
    return f"{v:.2f}"


def strength_word(r: float) -> str:
    a = abs(r)
    return ("no real" if a < 0.1 else "a weak" if a < 0.3 else
            "a moderate" if a < 0.5 else "a strong" if a < 0.7 else "a very strong")


def p_words(p: float, n: int) -> str:
    if p is None or not np.isfinite(p):
        return "not enough data to judge"
    if p < 0.01:
        return "very unlikely to be a fluke"
    if p < 0.05:
        return "unlikely to be a fluke"
    if p < 0.1:
        return "borderline: it could be chance"
    return "could easily be chance, especially with so few points" if n < 12 else "could easily be chance"


# --------------------------------------------------------------------------
# reading files
# --------------------------------------------------------------------------

@dataclass
class Table:
    """One sheet or CSV, after we have worked out its shape."""
    tid: str
    file: str
    sheet: str | None
    sample: bool = False
    skip: str | None = None
    date_name: str = "Date"
    num_cols: list = field(default_factory=list)     # [{'name':..}]
    text_cols: list = field(default_factory=list)    # [{'name':.., 'values':[..]}]
    frame: pd.DataFrame | None = None                # date | text cols | num cols
    long: bool = False
    freq: str = "month"
    suffix_note: str | None = None
    # user settings
    split: list = field(default_factory=list)        # indices into text_cols
    filters: dict = field(default_factory=dict)      # text col index -> value or '__all'
    use_num: list = field(default_factory=list)      # indices into num_cols

    @property
    def label(self) -> str:
        return f"{self.file} › {self.sheet}" if self.sheet else self.file

    @property
    def tag(self) -> str:
        return self.sheet if self.sheet else re.sub(r"\.[^.]+$", "", self.file)


def read_upload(name: str, data: bytes) -> list[tuple[str, str | None, list[list]]]:
    """Return [(file, sheet, grid)] for one uploaded file. A grid is rows of cells."""
    out = []
    if re.search(r"\.(xlsx|xlsm|xls|ods)$", name, re.I):
        book = pd.read_excel(io.BytesIO(data), sheet_name=None, header=None, dtype=object)
        multi = len(book) > 1
        for sheet, df in book.items():
            out.append((name, sheet if multi else None, df.where(pd.notna(df), None).values.tolist()))
    else:
        text = data.decode("utf-8", errors="replace")
        first = text.split("\n", 1)[0]
        sep = "\t" if first.count("\t") > first.count(",") else (";" if first.count(";") > first.count(",") else ",")
        df = pd.read_csv(io.StringIO(text), sep=sep, header=None, dtype=object,
                         skip_blank_lines=True, on_bad_lines="skip", engine="python")
        out.append((name, None, df.where(pd.notna(df), None).values.tolist()))
    return out


def analyze_grid(tid: str, file: str, sheet: str | None, grid: list[list], sample=False) -> Table:
    """Work out where the dates are, which columns are numbers, and what each series is called."""
    t = Table(tid=tid, file=file, sheet=sheet, sample=sample)
    rows = [r for r in grid if r is not None and any(c is not None and c != "" for c in r)]
    if len(rows) < 4:
        t.skip = "Too few rows to form a time series."
        return t
    ncol = min(400, max(len(r) for r in rows[:300]))
    rows = [list(r) + [None] * (ncol - len(r)) for r in rows]

    # 1. which column holds the dates?
    best = None
    for c in range(ncol):
        head_text = " ".join(str(r[c]) for r in rows[:10] if isinstance(r[c], str))
        allow_num = bool(DATEISH.search(head_text))
        cnt = tot = 0
        first = -1
        for i, r in enumerate(rows[:3000]):
            v = r[c]
            if v is None or v == "":
                continue
            tot += 1
            if parse_date(v, allow_num) is not None:
                cnt += 1
                if first < 0:
                    first = i
        if cnt >= 3 and cnt / tot >= 0.5:
            score = cnt + (5 if allow_num else 0) - c * 0.01
            if best is None or score > best[0]:
                best = (score, c, first, allow_num)
    if best is None:
        t.skip = "I couldn't find a column of dates, so this table can't be lined up in time."
        return t
    _, dc, start, allow_num = best

    data_rows, dates = [], []
    for r in rows[start:]:
        d = parse_date(r[dc], allow_num)
        if d is not None:
            data_rows.append(r)
            dates.append(d)
    if len(set(dates)) < 3:
        n = len(set(dates))
        t.skip = f"Only {n} distinct date{'' if n == 1 else 's'}, so this looks like a summary table rather than a time series."
        return t

    # 2. classify the other columns
    header_rows = rows[max(0, start - 8):start]
    num_idx, text_idx, text_vals = [], [], {}
    for c in range(ncol):
        if c == dc:
            continue
        ne = nn = nd = 0
        vals = {}
        for r in data_rows:
            v = r[c]
            if v is None or v == "":
                continue
            ne += 1
            if to_num(v) is not None:
                nn += 1
            elif parse_date(v, False) is not None:
                nd += 1
            elif len(vals) <= 500:
                k = str(v).strip()
                vals[k] = vals.get(k, 0) + 1
        if ne < 3 or nd / ne > 0.6:
            continue
        if nn / ne >= 0.8:
            num_idx.append(c)
        elif vals and len(vals) <= 500 and (ne - nn) / ne >= 0.5:
            text_idx.append(c)
            text_vals[c] = sorted(vals, key=lambda k: -vals[k])
    if not num_idx:
        t.skip = "No number columns found next to the dates."
        return t

    # 3. column names, allowing for headers that span several rows
    def name_of(c):
        toks = []
        for i, hr in enumerate(header_rows):
            v = hr[c]
            if (v is None or v == "") and i < len(header_rows) - 1:
                for k in range(c - 1, dc, -1):       # merged cell: look left
                    if hr[k] not in (None, ""):
                        v = hr[k]
                        break
            if v not in (None, ""):
                s = v.strftime("%Y-%m-%d") if isinstance(v, (pd.Timestamp, datetime, date)) else str(v).strip()
                if s and s not in toks:
                    toks.append(s)
        return toks

    num_toks = {c: name_of(c) for c in num_idx}
    if len(header_rows) > 1 and len(num_idx) > 1:
        common = [x for x in num_toks[num_idx[0]] if all(x in num_toks[c] for c in num_idx)]
        for c in num_idx:
            if len(num_toks[c]) > 1:
                num_toks[c] = [x for x in num_toks[c] if x not in common] or num_toks[c]
    num_names = {c: " · ".join(num_toks[c]) or f"Column {c+1}" for c in num_idx}
    text_names = {c: " · ".join(name_of(c)) or f"Column {c+1}" for c in text_idx}
    date_toks = name_of(dc)
    t.date_name = date_toks[-1] if date_toks else "Date"

    long = bool(text_idx) and len(set(dates)) < len(data_rows) * 0.95

    # 4. wide tables often repeat the same ending in every header - trim it
    if not long and len(num_idx) >= 3:
        suf = num_names[num_idx[0]]
        for c in num_idx:
            while suf and not num_names[c].endswith(suf):
                suf = suf[1:]
        m = re.match(r"^[^\w(]*(\s[-–·|:]\s.*|\s\(.*)$", suf)
        if m and len(m.group(1).strip()) >= 4 and all(len(num_names[c]) > len(suf) for c in num_idx):
            cut = m.group(1)
            keep = re.search(r"(\([^()]*\))\s*$", cut)
            keep = keep.group(1) if keep else ""
            dropped = re.sub(r"\s*\(\d+\)\s*$", "", cut[:cut.rfind(keep)]) if keep else cut
            for c in num_idx:
                num_names[c] = (num_names[c][: len(num_names[c]) - len(cut)]).strip() + (f" {keep}" if keep else "")
            t.suffix_note = re.sub(r"^\s*[-–·|:]\s*", "", dropped).strip() or cut.strip()

    cols_out = {"__date": dates}
    for c in text_idx:
        cols_out[text_names[c]] = [str(r[c]).strip() if r[c] not in (None, "") else "(blank)" for r in data_rows]
    for c in num_idx:
        cols_out[num_names[c]] = [to_num(r[c]) for r in data_rows]
    frame = pd.DataFrame(cols_out)

    t.frame = frame
    t.num_cols = [{"name": num_names[c]} for c in num_idx]
    t.text_cols = ([{"name": text_names[c], "values": text_vals[c]} for c in text_idx] if long else [])
    t.long = long
    t.freq = detect_freq(dates)

    # 5. sensible defaults
    if long:
        split = []
        for i, tc in enumerate(t.text_cols):
            if BRANDISH.search(tc["name"]) and 1 < len(tc["values"]) <= 60:
                split = [i]
                break
        if not split:
            best_i, best_n = None, 10 ** 9
            for i, tc in enumerate(t.text_cols):
                has_total = any(TOTALISH.match(v) for v in tc["values"])
                if not has_total and 1 < len(tc["values"]) <= 30 and len(tc["values"]) < best_n:
                    best_i, best_n = i, len(tc["values"])
            split = [best_i] if best_i is not None else []
        for i, tc in enumerate(t.text_cols):
            if METRICISH.match(tc["name"]) and len(tc["values"]) > 1 and i not in split:
                split.append(i)
        t.split = split
        for i, tc in enumerate(t.text_cols):
            if i in t.split:
                continue
            total = next((v for v in tc["values"] if TOTALISH.match(v)), None)
            t.filters[i] = total if total else "__all"
    if long and len(t.num_cols) > 4:
        pref = re.compile(r"score|value|spend|sales|amount|revenue|orders|visits|\$|cost|units", re.I)
        t.use_num = [i for i, n in enumerate(t.num_cols) if pref.search(n["name"])] or [0, 1, 2][: len(t.num_cols)]
    else:
        t.use_num = list(range(len(t.num_cols)))
    return t


# --------------------------------------------------------------------------
# series
# --------------------------------------------------------------------------

@dataclass
class Series:
    key: str
    base: str
    table: Table
    col: str
    data: pd.Series            # index: dates, values: numbers
    freq: str


def build_series(tables: list[Table]) -> list[Series]:
    """Apply each table's settings and produce one time series per name."""
    out = []
    for t in tables:
        if t.skip or t.frame is None:
            continue
        df = t.frame
        for i, tc in enumerate(t.text_cols):
            v = t.filters.get(i, "__all")
            if i in t.split or v == "__all":
                continue
            df = df[df[tc["name"]] == v]
        if df.empty:
            continue
        split_names = [t.text_cols[i]["name"] for i in t.split if i < len(t.text_cols)]
        for j in t.use_num:
            if j >= len(t.num_cols):
                continue
            col = t.num_cols[j]["name"]
            sub = df[["__date"] + split_names + [col]].dropna(subset=[col])
            if sub.empty:
                continue
            if split_names:
                grouped = sub.groupby(split_names + ["__date"], dropna=False)[col].sum()
                for gkey, ser in grouped.groupby(level=list(range(len(split_names)))):
                    gname = " · ".join(str(x) for x in (gkey if isinstance(gkey, tuple) else (gkey,)))
                    s = ser.droplevel(list(range(len(split_names))))
                    base = f"{gname} · {col}"
                    out.append(Series(f"{t.tid}::{base}", base, t, col, s.sort_index(), detect_freq(list(s.index))))
            else:
                s = sub.groupby("__date")[col].sum().sort_index()
                out.append(Series(f"{t.tid}::{col}", col, t, col, s, detect_freq(list(s.index))))
    return out


def default_agg(name: str) -> str:
    return "mean" if MEANISH.search(name) else "sum"


@dataclass
class ShareGroup:
    gid: str
    label: str
    members: list[str]


@dataclass
class Result:
    grain: str
    periods: pd.PeriodIndex
    levels: pd.DataFrame          # one column per series, index = periods
    values: pd.DataFrame          # levels or % change, depending on mode
    pct: pd.DataFrame
    log: list                     # [{'kind': 'info'|'did'|'warn', 'text': str}]
    matrix: pd.DataFrame
    nmat: pd.DataFrame
    pmat: pd.DataFrame
    meta: dict                    # series name -> {'share':bool,'derived_from':str,'group':str,'trend_r':float,...}
    common: tuple | None


def align_and_correlate(series: list[Series], names: dict, aggs: dict, include: dict,
                        groups: list[ShareGroup], grain: str = "auto", mode: str = "level",
                        method: str = "pearson", overlap: str = "pair",
                        exclude_future: bool = True) -> Result:
    """The heart of it: put everything on one calendar, then correlate."""
    log = []
    live = [s for s in series if include.get(s.key, False)]
    needed = {k for g in groups for k in g.members}
    basis = live or [s for s in series if s.key in needed]

    tables = {s.table.tid: s.table for s in series}
    if tables:
        log.append({"kind": "info",
                    "text": f"Read **{len(tables)}** usable table{'' if len(tables) == 1 else 's'}."})
    for t in tables.values():
        if not t.long:
            continue
        dims = [t.date_name] + [c["name"] for c in t.text_cols]
        dim_txt = " × ".join(dims[:4]) + f" × {len(dims)-4} more columns" if len(dims) > 5 else " × ".join(dims)
        sp = [t.text_cols[i]["name"] for i in t.split if i < len(t.text_cols)]
        summed = [c["name"] for i, c in enumerate(t.text_cols) if i not in t.split and t.filters.get(i) == "__all"]
        totals = [c["name"] for i, c in enumerate(t.text_cols)
                  if i not in t.split and t.filters.get(i, "__all") != "__all" and TOTALISH.match(str(t.filters.get(i)))]
        txt = f"**{t.label}** has one row per {dim_txt} (called *long format*). I turned it into "
        txt += f"one series per **{' × '.join(sp)}**" if sp else "a single series"
        if summed:
            shown = ", ".join(summed[:3]) + (f" and {len(summed)-3} other columns" if len(summed) > 3 else "")
            txt += f", adding up all the **{shown}** rows"
        if totals:
            txt += f". I used only the **Total** rows for {', '.join(totals)} so nothing is counted twice"
        log.append({"kind": "did", "text": txt + "."})
    sufs = [t for t in tables.values() if t.suffix_note]
    if sufs:
        extra = f" (and similar in {len(sufs)-1} other table{'s' if len(sufs) > 2 else ''})" if len(sufs) > 1 else ""
        log.append({"kind": "did", "text": f"Shortened series names by removing the repeated ending “{sufs[0].suffix_note}”{extra}."})

    if grain == "auto":
        grain = max((s.freq for s in basis), key=GRAIN_ORDER.index) if basis else "month"
    pfreq = PANDAS_FREQ[grain]

    # roll every series up to the chosen grain
    now = pd.Timestamp.now().normalize()
    buckets: dict[str, pd.Series] = {}
    partial, future = [], set()
    for s in series:
        idx = s.data.index
        if grain == "week":
            per = (idx + pd.Timedelta(days=1)).to_period(pfreq)
        else:
            per = idx.to_period(pfreq)
        agg = aggs.get(s.key, default_agg(s.base))
        g = s.data.groupby(per)
        vals = g.mean() if agg == "mean" else g.sum()
        counts = g.size()
        if GRAIN_ORDER.index(s.freq) < GRAIN_ORDER.index(grain) and len(vals) >= 3:
            med = float(counts.median())
            for edge in (vals.index[0], vals.index[-1]):
                if counts[edge] < 0.75 * med:
                    vals = vals.drop(edge)
                    if include.get(s.key):
                        partial.append((s.key, edge))
        if exclude_future:
            late = [p for p in vals.index if p.end_time > now]
            if late:
                future.update(late)
                vals = vals.drop(late)
        buckets[s.key] = vals

    name_of = {s.key: names.get(s.key, s.base) for s in series}

    # share-of series
    share_meta = {}
    for g in groups:
        members = [k for k in g.members if k in buckets]
        if len(members) < 2:
            continue
        frame = pd.DataFrame({name_of[k]: buckets[k] for k in members}).dropna()
        total = frame.sum(axis=1).replace(0, np.nan)
        for k in members:
            label = f"Share of {g.label}: {name_of[k]}"
            buckets[label] = (frame[name_of[k]] / total * 100).dropna()
            name_of[label] = label
            include[label] = include.get(label, True)
            share_meta[label] = {"share": True, "derived_from": name_of[k], "group": g.gid}
        log.append({"kind": "did",
                    "text": f"Created **Share of {g.label}**: each of the {len(members)} series divided by their "
                            f"combined total, per {GRAIN_NOUN[grain]}, as a %."})

    freqs = sorted({s.freq for s in basis}, key=GRAIN_ORDER.index)
    if len(freqs) > 1:
        log.append({"kind": "did", "text":
                    f"Your data comes in {' and '.join('**'+FREQ_WORD[f]+'**' for f in freqs)} form. A week can't be "
                    f"lined up with a month, so everything was rolled up to a **{FREQ_WORD[grain]}** calendar. Counts "
                    f"and money are *added up* within each {GRAIN_NOUN[grain]}; rates and scores are *averaged*."})
    elif freqs:
        extra = f", and I rolled it up to **{FREQ_WORD[grain]}** as you asked" if grain != freqs[0] else ""
        log.append({"kind": "info", "text": f"Everything is already **{FREQ_WORD[freqs[0]]}**{extra}."})
    if grain == "week":
        log.append({"kind": "info", "text": "Weeks that start on a Sunday and weeks that start on a Monday are treated as the same week."})
    elif any(s.freq == "week" for s in basis):
        log.append({"kind": "info", "text": f"Each week counts toward the {GRAIN_NOUN[grain]} it starts in."})
    if partial:
        ex = "; ".join(f"{period_label(p, grain)} for {name_of[k][:40]}" for k, p in partial[:3])
        log.append({"kind": "warn", "text":
                    f"Dropped {len(partial)} half-covered period{'' if len(partial) == 1 else 's'} at the start or end "
                    f"of a series, where the data only covered part of the {GRAIN_NOUN[grain]}. Keeping them would make "
                    f"the total look falsely low. ({ex}{'…' if len(partial) > 3 else ''})"})
    if future:
        fs = sorted(future)
        log.append({"kind": "warn", "text":
                    f"Left out **{len(fs)}** period{'' if len(fs) == 1 else 's'} that haven't finished yet "
                    f"({period_label(fs[0], grain)}{' to ' + period_label(fs[-1], grain) if len(fs) > 1 else ''}). Values there are forecasts or incomplete."})

    # build the aligned table
    chosen = [s.key for s in live] + [k for k in share_meta if include.get(k, True)]
    cols, meta, dropped = {}, {}, []
    for key in chosen:
        vals = buckets.get(key)
        if vals is None or vals.empty:
            continue
        label = name_of[key]
        fin = vals.dropna()
        if len(fin) < 3:
            dropped.append((label, "fewer than 3 values"))
            continue
        if fin.max() - fin.min() < 1e-12:
            dropped.append((label, "it never changes"))
            continue
        counts = fin.value_counts()
        if len(counts) < 4 or counts.iloc[0] / len(fin) > 0.6:
            dropped.append((label, "it barely changes, mostly the same value"))
            continue
        cols[label] = fin
        meta[label] = {"share": False, "derived_from": None, "group": None, "agg": aggs.get(key, default_agg(label))}
        meta[label].update(share_meta.get(key, {}))
    if dropped:
        shown = ", ".join(f"**{d[0][:40]}** ({d[1]})" for d in dropped[:4])
        more = f" and {len(dropped)-4} more" if len(dropped) > 4 else ""
        log.append({"kind": "warn", "text": f"Left out {shown}{more}, because correlation needs numbers that vary."})

    if not cols:
        empty = pd.DataFrame()
        return Result(grain, pd.PeriodIndex([], freq=pfreq), empty, empty, empty,
                      log + [{"kind": "warn", "text": "No series are selected, or none have data left after the steps above."}],
                      empty, empty, empty, {}, None)

    levels = pd.DataFrame(cols).sort_index()
    levels = levels.reindex(pd.period_range(levels.index.min(), levels.index.max(), freq=pfreq))
    pct = levels.pct_change() * 100
    values = pct if mode == "pct" else levels

    mask = None
    both = values.dropna(how="any")
    common = (both.index[0], both.index[-1], len(both)) if len(both) else None
    if overlap == "common":
        if len(both) >= 3:
            mask = values.index.isin(both.index)
        else:
            log.append({"kind": "warn", "text":
                        f"Only {len(both)} period{' has' if len(both) == 1 else 's have'} data for every series, which is "
                        f"too few, so each pair's own overlap was used instead."})
    if len(values.columns) > 1:
        if common:
            log.append({"kind": "info", "text":
                        f"All {len(values.columns)} series overlap from **{period_label(common[0], grain)}** to "
                                f"**{period_label(common[1], grain)}** "
                        f"({common[2]} {GRAIN_NOUN[grain]}s). " +
                        ("Every pair is compared on exactly these periods."
                         if mask is not None else
                         "Each pair is compared on every period where *both* have data, so some pairs use more periods than others.")})
        else:
            log.append({"kind": "warn", "text":
                        "There's no single period where every series has data. Each pair is compared only where both "
                        "overlap, and some pairs may not overlap at all."})
    if mode == "pct":
        log.append({"kind": "did", "text":
                    f"Compared **% change** from one {GRAIN_NOUN[grain]} to the next instead of raw levels. This tests "
                    f"whether the *moves* line up, not just the long-term direction."})

    work = values[mask] if mask is not None else values
    labels = list(work.columns)
    m = pd.DataFrame(np.nan, index=labels, columns=labels)
    nn = pd.DataFrame(0, index=labels, columns=labels)
    pp = pd.DataFrame(np.nan, index=labels, columns=labels)
    for i, a in enumerate(labels):
        for j, b in enumerate(labels):
            if j < i:
                m.iat[i, j], nn.iat[i, j], pp.iat[i, j] = m.iat[j, i], nn.iat[j, i], pp.iat[j, i]
                continue
            if i == j:
                m.iat[i, j], nn.iat[i, j], pp.iat[i, j] = 1.0, int(work[a].notna().sum()), 0.0
                continue
            r, n, p = corr_pair(work[a], work[b], method=method)
            m.iat[i, j], nn.iat[i, j], pp.iat[i, j] = r, n, p

    # trend of each series over time
    for label in labels:
        s = levels[label].dropna()
        x = np.arange(len(s))
        meta[label]["trend_r"] = float(np.corrcoef(x, s.values)[0, 1]) if len(s) >= 3 and s.std() > 0 else np.nan
        meta[label]["change_pct"] = float((s.iloc[-1] / s.iloc[0] - 1) * 100) if len(s) and s.iloc[0] else np.nan
        meta[label]["first"], meta[label]["last"] = (s.index[0], s.index[-1]) if len(s) else (None, None)

    return Result(grain, levels.index, levels, values, pct, log, m, nn, pp, meta, common)


def corr_pair(a: pd.Series, b: pd.Series, lag: int = 0, method: str = "pearson"):
    """r, n and p for one pair. lag>0 shifts `a` earlier, i.e. a leads b."""
    x = a.shift(lag) if lag else a
    d = pd.concat([x, b], axis=1).dropna()
    d.columns = ["x", "y"]
    if len(d) < 3 or d["x"].std() == 0 or d["y"].std() == 0:
        return np.nan, len(d), np.nan
    fn = stats.spearmanr if method == "spearman" else stats.pearsonr
    try:
        r, p = fn(d["x"].values, d["y"].values)
    except Exception:
        return np.nan, len(d), np.nan
    return float(r), len(d), float(p)


def pair_points(res: Result, a: str, b: str):
    d = pd.concat([res.values[a], res.values[b]], axis=1).dropna()
    d.columns = ["x", "y"]
    return d


def related(res: Result, a: str, b: str) -> str | None:
    ma, mb = res.meta.get(a, {}), res.meta.get(b, {})
    if ma.get("share") and ma.get("derived_from") == b:
        return "share"
    if mb.get("share") and mb.get("derived_from") == a:
        return "share"
    if ma.get("share") and mb.get("share") and ma.get("group") == mb.get("group"):
        return "sib"
    return None


# --------------------------------------------------------------------------
# findings
# --------------------------------------------------------------------------

def ranked_pairs(res: Result, target: str | None):
    """The list behind the bar chart: either everything vs the target, or the strongest pairs."""
    labels = list(res.matrix.columns)
    items = []
    if target and target in labels:
        for a in labels:
            if a == target:
                continue
            r = res.matrix.at[a, target]
            if pd.isna(r):
                continue
            items.append({"a": a, "b": target, "r": float(r), "n": int(res.nmat.at[a, target]),
                          "p": float(res.pmat.at[a, target]), "rel": related(res, a, target)})
    else:
        for i, a in enumerate(labels):
            for b in labels[i + 1:]:
                r = res.matrix.at[a, b]
                if pd.isna(r) or res.nmat.at[a, b] < 4 or related(res, a, b):
                    continue
                items.append({"a": a, "b": b, "r": float(r), "n": int(res.nmat.at[a, b]),
                              "p": float(res.pmat.at[a, b]), "rel": None})
    items.sort(key=lambda d: -abs(d["r"]))
    return items


def findings(res: Result, target: str | None, method: str, mode: str) -> list[dict]:
    """Plain-English cards about what is in the data."""
    out = []
    G = GRAIN_NOUN[res.grain]
    items = ranked_pairs(res, target)
    top = items[:12]
    if top:
        it = top[0]
        out.append({"kind": "Closest link to your goal" if target else "Strongest link", "tone": "accent", "text":
                    f"**{it['a']}** and **{it['b']}** have {strength_word(it['r'])} "
                    f"{'positive' if it['r'] > 0 else 'negative'} link (r = {it['r']:.2f}). "
                    f"{'When one goes up, the other usually goes up too.' if it['r'] > 0 else 'When one goes up, the other usually goes down.'} "
                    f"About **{round(it['r']**2*100)}%** of the ups and downs line up (r²). With {it['n']} {G}s of data, "
                    f"it's {p_words(it['p'], it['n'])}."})

    if target and target in res.values.columns:
        leads = []
        for a in res.values.columns:
            if a == target or related(res, a, target):
                continue
            r0, n0, _ = corr_pair(res.values[a], res.values[target], method=method)
            if n0 < 6:
                continue
            best = None
            for L in (1, 2, 3):
                r, n, p = corr_pair(res.values[a], res.values[target], lag=L, method=method)
                if n >= 6 and np.isfinite(r) and (best is None or abs(r) > abs(best[0])):
                    best = (r, n, p, L)
            if best and abs(best[0]) >= 0.5 and best[2] < 0.05 and abs(best[0]) > abs(r0) + 0.15:
                leads.append((a, best, r0))
        leads.sort(key=lambda t: -abs(t[1][0]))
        for a, (r, n, p, L) in [(x[0], x[1]) for x in leads[:2]]:
            r0 = next(x[2] for x in leads if x[0] == a)
            out.append({"kind": f"Early signal · {L} {G}{'s' if L > 1 else ''} ahead", "tone": "accent", "text":
                        f"**{a}** lines up better with **{target}** **{L} {G}{'s' if L > 1 else ''} later** "
                        f"(r = {r:.2f}) than in the same {G} (r = {r0:.2f}). It may work as an early warning, or its "
                        f"effect may take time to show."})
        none = [i["a"] for i in items if abs(i["r"]) < 0.1]
        if none:
            shown = ", ".join(f"**{x}**" for x in none[:3])
            more = f" and {len(none)-3} more" if len(none) > 3 else ""
            out.append({"kind": "No clear link", "tone": "plain",
                        "text": f"{shown}{more} {'shows' if len(none) == 1 else 'show'} almost no relationship with your goal (|r| under 0.1)."})

    trends = sorted([(k, v) for k, v in res.meta.items()
                     if np.isfinite(v.get("trend_r", np.nan)) and abs(v["trend_r"]) >= 0.6],
                    key=lambda kv: -abs(kv[1]["trend_r"]))[:6]
    if trends:
        lines = []
        for k, v in trends:
            arrow = "↗" if v["trend_r"] > 0 else "↘"
            chg = (f"{v['change_pct']:+.0f}% from {period_label(v['first'], res.grain)} to "
                   f"{period_label(v['last'], res.grain)}") if np.isfinite(v.get("change_pct", np.nan)) else ""
            lines.append(f"- {arrow} **{k}** {chg}")
        out.append({"kind": "Clear trends over time", "tone": "plain",
                    "text": "These series rise or fall steadily across the whole period:\n" + "\n".join(lines)})

    if mode == "level":
        shared = []
        for it in top:
            if abs(it["r"]) < 0.5:
                continue
            ta = res.meta.get(it["a"], {}).get("trend_r", np.nan)
            tb = res.meta.get(it["b"], {}).get("trend_r", np.nan)
            if not (np.isfinite(ta) and np.isfinite(tb) and abs(ta) > 0.6 and abs(tb) > 0.6):
                continue
            rp, _, _ = corr_pair(res.pct[it["a"]], res.pct[it["b"]], method=method)
            if np.isfinite(rp) and abs(rp) < abs(it["r"]) - 0.3:
                shared.append(it)
        if shared:
            pairs = "; ".join(f"**{i['a']}** × **{i['b']}**" for i in shared[:3])
            out.append({"kind": "Watch out: shared trend", "tone": "warn", "text":
                        f"Some links may exist only because both numbers trend over time: {pairs}. When you compare % "
                        f"changes instead, the link mostly disappears. Try switching *Compare* to **% change**."})
    small = [i for i in top if i["n"] < 12]
    if small:
        out.append({"kind": "Watch out: little data", "tone": "warn",
                    "text": f"{len(small)} of these pairs overlap for fewer than 12 {G}s. Treat them as hints, not proof."})
    if any(v.get("share") for v in res.meta.values()):
        out.append({"kind": "About share series", "tone": "plain", "text":
                    "Shares in the same group add up to 100%, so when one brand's share goes up, another's must go "
                    "down. Negative links between them are built into the math."})
    out.append({"kind": "Remember", "tone": "plain", "text":
                "Correlation shows what moves together, not what causes what. Use these results to decide what to test next."})
    return out


def suggest_shares(series: list[Series], names: dict, existing: list[ShareGroup]) -> list[dict]:
    """Guess which groups of series are worth turning into shares."""
    by_group: dict[str, list[Series]] = {}
    for s in series:
        key = f"{s.table.tid}|{s.col}" if s.table.long else s.table.tid
        by_group.setdefault(key, []).append(s)
    out = []
    for key, members in by_group.items():
        if len(members) < 2:
            continue
        t = members[0].table
        if not t.long and len(members) < 3:
            continue
        if all(default_agg(names.get(m.key, m.base)) == "mean" for m in members):
            continue
        txt = f"{t.label} {members[0].col}".lower()
        label = ("Search" if re.search(r"search|google|bing|query", txt) else
                 "Voice (spend)" if re.search(r"spend|media|cost|radar|pathmatic|\$", txt) else
                 "Conversation" if re.search(r"\bx\b|twitter|tiktok|social|mention|conversation|buzz|reddit|instagram|facebook|pinterest", txt) else
                 "App Downloads" if re.search(r"app ?store|play ?store|download|install", txt) else
                 "AI Mentions" if re.search(r"perplexity|chatgpt|\bai\b|llm", txt) else
                 "Retail Search" if re.search(r"amazon|retail", txt) else t.tag)
        if t.long and len(t.num_cols) > 1:
            label += f" ({members[0].col})"
        keys = [m.key for m in members]
        if any(sorted(g.members) == sorted(keys) for g in existing):
            continue
        ch = re.search(r"google|bing|tiktok|pinterest|perplexity|amazon|app ?store|play ?store|\bx\b", txt)
        out.append({"label": label, "members": keys, "from": t.label,
                    "channel": (ch.group(0).title() if ch else t.tag)})
    counts: dict[str, int] = {}
    for o in out:
        counts[o["label"]] = counts.get(o["label"], 0) + 1
    for o in out:
        if counts[o["label"]] > 1:
            o["label"] = f"{o['label']} ({o['channel']})"
    return out


# --------------------------------------------------------------------------
# example data (entirely fictional)
# --------------------------------------------------------------------------

def make_sample() -> list[tuple[str, str | None, list[list]]]:
    """A made-up granola category: spend -> search -> visits -> orders, plus a brand tracker."""
    rng = np.random.default_rng(20260921)
    T = 49                                    # Jan 2023 .. Jan 2027
    brands = ["Harbor Crunch", "Summit Oats", "Meadow Bar", "Trailbrite"]
    base = [180, 220, 140, 60]
    spend = np.zeros((4, T))
    for bi in range(4):
        for t in range(T):
            m = t % 12
            burst = (1.1 if bi == 0 and m in (2, 3, 8, 9) else 0.9 if bi == 1 and m in (10, 11)
                     else 0.8 if bi == 2 and m == 5 else 0.7 if bi == 3 and m in (0, 6) else 0)
            grow = 1 + t * 0.012 if bi == 0 else 1 - t * 0.006 if bi == 2 else 1
            spend[bi, t] = max(4000, base[bi] * 1000 * grow * (1 + burst + 0.22 * rng.standard_normal()))
    s_base = [42000, 61000, 38000, 9000]
    search = np.zeros((4, T))
    for bi in range(4):
        for t in range(T):
            prev = spend[bi, max(0, t - 1)] / (base[bi] * 1000)
            trend = 1 + t * 0.016 if bi == 0 else 1 - t * 0.007 if bi == 2 else 1 + t * 0.002
            season = 1 + 0.2 * math.cos((t % 12) / 12 * 2 * math.pi)
            noise = 0 if t > 44 else 0.06 * rng.standard_normal()
            search[bi, t] = round(s_base[bi] * trend * season * (0.72 + 0.2 * prev) * (1 + noise))
    sos = search[0] / search.sum(axis=0)

    def month_end(t):
        y, m = 2023 + t // 12, t % 12 + 1
        return (pd.Timestamp(year=y, month=m, day=1) + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")

    g1 = [["Date"] + [f"{b} - United States (google)" for b in brands]]
    for t in range(T):
        g1.append([month_end(t)] + [int(search[bi, t]) for bi in range(4)])

    channels = ["TV", "Social", "Online Video", "Paid Search", "Audio"]
    weights = [[.35, .25, .2, .12, .08], [.5, .15, .15, .1, .1], [.2, .4, .2, .15, .05], [.1, .5, .2, .2, 0]]
    g2 = [["Month", "Brand", "Channel", "Spend ($)"]]
    for t in range(12, 44):
        y, m = 2023 + t // 12, t % 12
        stamp = f"{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][m]}'{str(y)[2:]}"
        for bi in range(4):
            for ci, ch in enumerate(channels):
                g2.append([stamp, brands[bi], ch,
                           int(max(0, spend[bi, t] * weights[bi][ci] * (1 + 0.1 * rng.standard_normal())))])

    g3 = [["Week Starting", "Site Visits", "Orders"]]
    d = pd.Timestamp("2024-01-07")
    while d <= pd.Timestamp("2026-09-13"):
        t = (d.year - 2023) * 12 + d.month - 1
        visits = int(search[0, t] * 0.52 / 4.33 * (0.85 + 0.9 * sos[t]) * (1 + 0.08 * rng.standard_normal()))
        orders = int(visits * (0.024 + 0.002 * rng.standard_normal()))
        g3.append([f"{d.month}/{d.day}/{d.year}", visits, orders])
        d += pd.Timedelta(days=7)

    g4 = [["Month", "Brand", "Awareness %", "Consideration %"]]
    for t in range(14, 44):
        y, m = 2023 + t // 12, t % 12 + 1
        aw = 16 + 62 * sos[t - 1] + 1.4 * rng.standard_normal()
        s1 = search[1, t - 1] / search[:, t - 1].sum()
        aw1 = 28 + 30 * s1 + 1.6 * rng.standard_normal()
        g4.append([f"{m}/1/{y}", "Harbor Crunch", round(aw, 1), round(0.44 * aw + 1.1 * rng.standard_normal(), 1)])
        g4.append([f"{m}/1/{y}", "Summit Oats", round(aw1, 1), round(0.4 * aw1 + 1.2 * rng.standard_normal(), 1)])

    return [("search_trends.xlsx", "Google", g1), ("media_spend.csv", None, g2),
            ("web_sales_weekly.csv", None, g3), ("brand_tracker.csv", None, g4)]
