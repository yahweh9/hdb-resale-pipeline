"""The dashboard's look: page styles and the small HTML pieces Streamlit has no widget for.

Streamlit draws the charts, tables and filters. Everything else a reader sees -- the page
header, the headline figures, the labels under each card, the loading, empty and error
states -- is plain HTML from this module, so app.py reads as a list of what is on each
page rather than how it is drawn.

Streamlit renders markdown before HTML, so every fragment here is built on one line:
an indented or blank line inside it would be read as a markdown code block.
"""

import html

import streamlit as st

ACCENT = "#2a78d6"

_FONTS = (
    "https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700"
    "&family=Geist+Mono:wght@400;500&display=swap"
)

_CSS = f"""
@import url('{_FONTS}');

:root {{
  --page: #fafafa;
  --card: #ffffff;
  --ink: #18181b;
  --ink-2: #52525b;
  --ink-3: #71717a;
  --hairline: #e4e4e7;
  --line: rgba(228, 228, 231, 0.7);
  --accent: {ACCENT};
  --ease: cubic-bezier(0.16, 1, 0.3, 1);
  --shadow: 0 20px 40px -15px rgba(24, 24, 27, 0.07);
  --shadow-lift: 0 28px 48px -18px rgba(24, 24, 27, 0.12);
  --sans: 'Geist', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif;
  --mono: 'Geist Mono', ui-monospace, 'SFMono-Regular', Consolas, monospace;
}}

.stApp {{ background: var(--page); color: var(--ink); }}
.stApp *:not([data-testid="stIconMaterial"]):not(code):not(code *) {{ font-family: var(--sans); }}
.stApp code, .stApp code * {{ font-family: var(--mono); }}

[data-testid="stDecoration"], [data-testid="stAppDeployButton"], .stDeployButton {{ display: none; }}
header[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ max-width: 1400px; padding-top: 2.5rem; padding-bottom: 4rem; }}

section[data-testid="stSidebar"] {{ background: var(--card); border-right: 1px solid var(--hairline); }}
section[data-testid="stSidebar"] h2 {{ font-size: 0.78rem; font-weight: 500; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--ink-3); }}
.stApp button {{ transition: transform 0.2s var(--ease); }}
.stApp button:active {{ transform: scale(0.98); }}

/* Motion: every block rises into place once, in order. Nothing loops except the live dot. */
@keyframes rise {{ from {{ opacity: 0; transform: translateY(14px); }} to {{ opacity: 1; transform: none; }} }}
@keyframes breathe {{ 0% {{ transform: scale(1); opacity: 0.5; }} 70% {{ transform: scale(2.8); opacity: 0; }} 100% {{ opacity: 0; }} }}
@keyframes shimmer {{ from {{ background-position: 100% 0; }} to {{ background-position: 0 0; }} }}
.reveal {{ animation: rise 0.8s var(--ease) both; animation-delay: calc(var(--i, 0) * 90ms); }}

/* Header: copy on the left, the edition on the right. */
.hero {{ display: grid; grid-template-columns: minmax(0, 1.75fr) minmax(250px, 1fr); gap: 3rem;
  align-items: end; margin-bottom: 2.5rem; }}
.eyebrow {{ margin: 0 0 1rem; font-size: 0.78rem; font-weight: 500; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--ink-3); }}
.eyebrow span {{ color: var(--hairline); margin: 0 0.4rem; }}
.hero h1 {{ margin: 0; padding: 0; font-size: clamp(2rem, 3.2vw, 2.9rem); font-weight: 600; line-height: 1.05;
  letter-spacing: -0.035em; color: var(--ink); max-width: 22ch; text-wrap: balance; }}
.lede {{ margin: 1.1rem 0 0; font-size: 1.02rem; line-height: 1.65; color: var(--ink-2); max-width: 62ch; }}
.edition {{ border-top: 1px solid var(--hairline); padding-top: 1.1rem; display: grid; gap: 0.85rem; }}
.edition-status {{ display: flex; align-items: center; gap: 0.7rem; font-size: 0.92rem; color: var(--ink-2); }}
.edition-status b {{ color: var(--ink); font-weight: 600; }}
.live-dot {{ position: relative; width: 8px; height: 8px; border-radius: 50%; background: var(--accent); flex: none; }}
.live-dot::after {{ content: ""; position: absolute; inset: 0; border-radius: 50%; background: var(--accent);
  animation: breathe 2.6s var(--ease) infinite; }}
.edition dl {{ margin: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem; }}
.edition dt {{ font-size: 0.74rem; color: var(--ink-3); }}
.edition dd {{ margin: 0.15rem 0 0; font-size: 0.95rem; font-weight: 500; color: var(--ink); }}
.edition p {{ margin: 0; font-size: 0.82rem; color: var(--ink-3); }}
.chips {{ display: flex; flex-wrap: wrap; gap: 0.4rem; }}
.chip {{ font-size: 0.8rem; color: var(--ink-2); background: var(--page); border: 1px solid var(--hairline);
  border-radius: 999px; padding: 0.2rem 0.65rem; }}

/* Headline figures: one hero number, two supporting ones. */
.tiles {{ display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr) minmax(0, 1fr); gap: 1.25rem;
  margin-bottom: 1.75rem; }}
.tile {{ background: var(--card); border: 1px solid var(--line); border-radius: 2rem; box-shadow: var(--shadow);
  padding: 1.75rem 2rem; display: flex; flex-direction: column; justify-content: space-between; gap: 1rem; min-width: 0;
  transition: transform 0.5s var(--ease), box-shadow 0.5s var(--ease); }}
.tile:hover {{ transform: translateY(-3px); box-shadow: var(--shadow-lift); }}
.tile-label {{ margin: 0; font-size: 0.88rem; color: var(--ink-2); }}
.tile-value {{ margin: 0; font-size: 2.1rem; font-weight: 600; letter-spacing: -0.03em; line-height: 1; color: var(--ink);
  white-space: nowrap; }}
.tile-note {{ margin: 0; font-size: 0.82rem; line-height: 1.5; color: var(--ink-3); }}
.tile-hero {{ display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); align-items: end; gap: 1.5rem; }}
.tile-hero .tile-value {{ font-size: clamp(2.75rem, 4vw, 3.75rem); letter-spacing: -0.045em; }}
.spark {{ width: 100%; height: auto; display: block; }}

/* Chart cards: Streamlit's bordered containers, found by the marker each one carries. */
[data-testid="stVerticalBlockBorderWrapper"]:has(.card-marker):not(:has([data-testid="stVerticalBlockBorderWrapper"] .card-marker)) {{
  background: var(--card); border: 1px solid var(--line) !important; border-radius: 2rem !important;
  box-shadow: var(--shadow); padding: 1.25rem 1.5rem 0.75rem;
  animation: rise 0.8s var(--ease) both; animation-delay: 120ms;
  transition: transform 0.5s var(--ease), box-shadow 0.5s var(--ease);
}}
[data-testid="stVerticalBlockBorderWrapper"]:has(.card-marker):not(:has([data-testid="stVerticalBlockBorderWrapper"] .card-marker)):hover {{
  transform: translateY(-3px); box-shadow: var(--shadow-lift);
}}
[data-testid="stColumn"]:nth-child(2) [data-testid="stVerticalBlockBorderWrapper"]:has(.card-marker) {{ animation-delay: 220ms; }}
.card-marker {{ display: none; }}

/* The title and description sit under the card, not inside it. */
.card-label {{ margin: 0.9rem 0.5rem 2.25rem; }}
.card-label h3 {{ margin: 0; padding: 0; font-size: 1.02rem; font-weight: 600; letter-spacing: -0.01em; color: var(--ink); }}
.card-label p {{ margin: 0.35rem 0 0; font-size: 0.88rem; line-height: 1.55; color: var(--ink-3); max-width: 62ch; }}

.footnote {{ margin-top: 1rem; padding-top: 1.25rem; border-top: 1px solid var(--hairline); font-size: 0.82rem;
  color: var(--ink-3); }}

/* Loading, empty and error states. */
.skeleton {{ display: grid; gap: 1.25rem; }}
.skel {{ border-radius: 2rem; background: linear-gradient(90deg, #f4f4f5 25%, #ebebed 45%, #f4f4f5 65%);
  background-size: 300% 100%; animation: shimmer 1.4s ease-in-out infinite; }}
.skel-row {{ display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); gap: 1.25rem; }}
.state {{ background: var(--card); border: 1px solid var(--line); border-radius: 2rem; box-shadow: var(--shadow);
  padding: 2.5rem; display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 1.25rem; align-items: start;
  max-width: 720px; }}
.state svg {{ width: 28px; height: 28px; color: var(--ink-3); }}
.state h3 {{ margin: 0; padding: 0; font-size: 1.1rem; font-weight: 600; color: var(--ink); }}
.state p {{ margin: 0.4rem 0 0; font-size: 0.92rem; line-height: 1.6; color: var(--ink-2); }}
.state.error svg {{ color: #d03b3b; }}

/* Chart tooltips (Vega's own element). */
#vg-tooltip-element {{ font-family: var(--sans); background: var(--card); color: var(--ink);
  border: 1px solid var(--hairline); border-radius: 12px; box-shadow: var(--shadow-lift); padding: 0.55rem 0.75rem; }}
#vg-tooltip-element td.key {{ color: var(--ink-3); }}
#vg-tooltip-element td.value {{ font-family: var(--mono); }}

@media (max-width: 768px) {{
  .hero, .tiles, .tile-hero, .skel-row {{ grid-template-columns: minmax(0, 1fr); gap: 1.25rem; }}
  .block-container {{ padding-top: 3.75rem; }}
}}
@media (prefers-reduced-motion: reduce) {{
  .stApp *, .stApp *::after {{ animation: none !important; transition: none !important; }}
}}
"""


def _html(fragment):
    st.markdown(fragment, unsafe_allow_html=True)


def apply():
    """Page-wide styles. Call once per page, before anything else is drawn."""
    _html(f"<style>{_CSS}</style>")


def esc(text):
    return html.escape(str(text))


def header(eyebrow, title, lede, aside):
    _html(
        '<section class="hero">'
        f'<div class="reveal" style="--i:0"><p class="eyebrow">HDB resale prices<span>/</span>{esc(eyebrow)}</p>'
        f'<h1>{esc(title)}</h1><p class="lede">{esc(lede)}</p></div>'
        f'<aside class="edition reveal" style="--i:1">{aside}</aside>'
        "</section>"
    )


def edition_aside(stamp, note):
    through = _month_name(stamp["data_through"])
    return (
        f'<div class="edition-status"><span class="live-dot"></span><span>Data through <b>{esc(through)}</b></span></div>'
        f'<dl><div><dt>Sales</dt><dd>{stamp["sales"]:,}</dd></div>'
        f'<div><dt>Published</dt><dd>{esc(_date_name(stamp["published_on"]))}</dd></div></dl>'
        f"<p>{esc(note)}</p>"
    )


def filter_aside(chips, note):
    chip_html = "".join(f'<span class="chip">{esc(c)}</span>' for c in chips)
    return f'<div class="edition-status">Showing</div><div class="chips">{chip_html}</div><p>{esc(note)}</p>'


def tiles(hero, others):
    """One hero figure (label, value, note, optional sparkline SVG) and two smaller ones."""
    label, value, note, spark = hero
    parts = [
        f'<div class="tile tile-hero reveal" style="--i:2"><div><p class="tile-label">{esc(label)}</p>'
        f'<p class="tile-value" style="margin-top:1rem">{esc(value)}</p>'
        f'<p class="tile-note" style="margin-top:0.9rem">{esc(note)}</p></div>{spark}</div>'
    ]
    for i, (label, value, note) in enumerate(others, start=3):
        parts.append(
            f'<div class="tile reveal" style="--i:{i}"><p class="tile-label">{esc(label)}</p>'
            f'<div><p class="tile-value">{esc(value)}</p><p class="tile-note" style="margin-top:0.6rem">{esc(note)}</p></div></div>'
        )
    _html(f'<div class="tiles">{"".join(parts)}</div>')


def sparkline(values, description):
    """A single thin line in the accent, ending in a dot with a white ring."""
    values = [float(v) for v in values]
    if len(values) < 2:
        return ""
    w, h, pad = 320, 96, 8
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    xs = [pad + i * (w - 2 * pad) / (len(values) - 1) for i in range(len(values))]
    ys = [h - pad - (v - lo) * (h - 2 * pad) / span for v in values]
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    return (
        f'<svg class="spark" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(description)}">'
        f'<polyline points="{points}" fill="none" stroke="{ACCENT}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="4.5" fill="{ACCENT}" stroke="#ffffff" stroke-width="2"/></svg>'
    )


def card():
    """A chart card. Use as `with theme.card():`; the marker lets the styles find it."""
    box = st.container(border=True)
    box.markdown('<span class="card-marker"></span>', unsafe_allow_html=True)
    return box


def card_label(title, description):
    _html(f'<div class="card-label"><h3>{esc(title)}</h3><p>{esc(description)}</p></div>')


def edition_line(stamp):
    """The data cut in words: "240,074 sales through Sep 2026, published 14 Sep 2026"."""
    return (f"{stamp['sales']:,} sales through {_month_name(stamp['data_through'])}, "
            f"published {_date_name(stamp['published_on'])}")


def month_name(year_month):
    return _month_name(year_month)


def footnote(text):
    _html(f'<p class="footnote">{esc(text)}</p>')


def skeleton():
    """Placeholder shapes the size of the page that is loading."""
    return (
        '<div class="skeleton">'
        '<div class="skel" style="height:150px;border-radius:1rem"></div>'
        '<div class="skel-row"><div class="skel" style="height:190px"></div><div class="skel" style="height:190px"></div></div>'
        '<div class="skel-row"><div class="skel" style="height:360px"></div><div class="skel" style="height:360px"></div></div>'
        "</div>"
    )


_SEARCH_ICON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
    'aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>'
)
_ALERT_ICON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
    'aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5M12 16.5v.01"/></svg>'
)


def empty_state(title, body):
    _html(f'<div class="state reveal">{_SEARCH_ICON}<div><h3>{esc(title)}</h3><p>{esc(body)}</p></div></div>')


def error_state(title, body):
    _html(f'<div class="state error reveal">{_ALERT_ICON}<div><h3>{esc(title)}</h3><p>{esc(body)}</p></div></div>')


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _month_name(year_month):
    year, month = str(year_month).split("-")[:2]
    return f"{_MONTHS[int(month) - 1]} {year}"


def _date_name(iso_date):
    year, month, day = str(iso_date).split("-")[:3]
    return f"{int(day)} {_MONTHS[int(month) - 1]} {year}"
