"""
Cortex Database - Reporting.

One page, one file. Replaces the "Cortex Tracker" Power BI dashboard -
same questions Global Management asks every month/quarter, but read at a
glance instead of pieced together from dense pivot tables:

  - New projects shared to CBI (this month / YTD, by sector, by region)
  - Projects published to Cortex (this month / YTD, vs the 2026 quota)
  - Where every project sits in the pipeline right now, and where it gets stuck
  - Geographic coverage of the Cortex database
  - Which sectors have the most / least in Cortex
  - Sustainability (tracked separately - its own pipeline, its own bulk imports)

Everything is derived live from the projects + project_events tables. Main
pipeline (US / Global / UK) and Sustainability are reported separately,
matching how the old dashboard split them. Laid out as a page-navigator
(sidebar) report, one question per page, rather than one long scroll.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from db import get_connection, PROJECTS_TABLE, EVENTS_TABLE
from theme import apply_theme, page_header, PURPLE, PURPLE_LIGHT, PURPLE_PALE

st.set_page_config(page_title="Cortex Reporting", layout="wide", initial_sidebar_state="expanded")
apply_theme()

# ---------------------------------------------------------------------------
# Palette & constants
# ---------------------------------------------------------------------------

PLUM = PURPLE
INK = "#2c2c2c"
CREAM = "#f5f2ef"
GOOD = "#4c7a4c"
BELOW = "#a24a3c"

# Fixed hue per region - same everywhere, never reassigned by rank.
REGION_COLORS = {
    "AMERICAS": PURPLE,
    "UK & EUROPE": "#2c6e6b",
    "ME": "#b8862c",
    "APAC": "#5b7f5e",
    "LATAM": "#8a5a8f",
    "ANTARCTICA": "#7c8a9c",
}

MAIN_STAGES = [
    "PROJECT IN QUEUE",
    "PROJECT SELECTED",
    "TEMPLATE PENDING",
    "TEMPLATE COMPLETE/REVIEW PENDING",
    "REVIEW COMPLETE/IN CORTEX PENDING",
    "IN CORTEX COMPLETE",
]
MAIN_STAGE_SHORT = {
    "PROJECT IN QUEUE": "In Queue (projects not being worked on yet)",
    "PROJECT SELECTED": "Project Selected",
    "TEMPLATE PENDING": "Template Pending",
    "TEMPLATE COMPLETE/REVIEW PENDING": "Template Complete/Review Pending",
    "REVIEW COMPLETE/IN CORTEX PENDING": "Review Complete/Yet to Publish in Cortex",
    "IN CORTEX COMPLETE": "Published in Cortex",
}
SUS_STAGES = ["PROJECT ADDED", "IN PROGRESS", "IN REVIEW", "PUBLISHED TO CORTEX"]
FINAL_STAGES = ("IN CORTEX COMPLETE", "PUBLISHED TO CORTEX")

# The 2026 Countdown here is US + Global + UK combined - every STAGE
# ADVANCE event landing on "IN CORTEX COMPLETE" in 2026, same count as the
# "YTD published to Cortex" stat below (see published_e). This is wider
# than the Tracker app's Insights page, which is US + Global only and uses
# a project-state test rather than an event count - the two numbers are
# expected to differ, on purpose, per Krutika 2026-09-24.
QUOTA_GOAL = 150

MONTH_NAMES = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May", "06": "Jun",
    "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
}

# Our COUNTRY values -> names Plotly's country-name geocoder recognises.
# UK constituent countries all roll up to "United Kingdom" on the map.
COUNTRY_TO_MAP = {
    "USA": "United States",
    "ENGLAND": "United Kingdom", "SCOTLAND": "United Kingdom",
    "WALES": "United Kingdom", "NORTHERN IRELAND": "United Kingdom",
    "UAE": "United Arab Emirates", "KSA": "Saudi Arabia",
    "HONG KONG": "Hong Kong", "COSTA RICA": "Costa Rica",
}


def to_map_country(c):
    if not isinstance(c, str) or not c.strip() or c.strip().upper() == "LSE":
        return None
    return COUNTRY_TO_MAP.get(c.strip().upper(), c.strip().title())


def month_label(ym):
    y, m = ym.split("-")
    return f"{MONTH_NAMES[m]} {y}"


# ---------------------------------------------------------------------------
# Data - pulled once, sliced in pandas
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600)
def load_all():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(f"""
        SELECT HASH_ID, TRACKER, CURRENT_STAGE, SECTOR, REGION, COUNTRY, ARCHIVED
        FROM {PROJECTS_TABLE}
    """)
    projects = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])

    cur.execute(f"""
        SELECT e.EVENT_TYPE, e.OLD_VALUE, e.NEW_VALUE, e.EFFECTIVE_DATE,
               p.TRACKER, p.SECTOR, p.REGION, p.COUNTRY
        FROM {EVENTS_TABLE} e
        JOIN {PROJECTS_TABLE} p ON e.HASH_ID = p.HASH_ID
        WHERE e.VOIDED = false
          AND (p.ARCHIVED = false OR p.ARCHIVED IS NULL)
    """)
    events = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])

    cur.close()
    conn.close()

    projects["ARCHIVED"] = projects["ARCHIVED"].fillna(False).astype(bool)
    projects = projects[~projects["ARCHIVED"]].copy()
    projects["IS_SUS"] = projects["TRACKER"] == "SUSTAINABILITY"

    events["EFFECTIVE_DATE"] = pd.to_datetime(events["EFFECTIVE_DATE"], errors="coerce")
    events = events[events["EFFECTIVE_DATE"].notna()].copy()
    events["YM"] = events["EFFECTIVE_DATE"].dt.strftime("%Y-%m")
    events["IS_SUS"] = events["TRACKER"] == "SUSTAINABILITY"

    return projects, events


def sector_short(s):
    if not isinstance(s, str):
        return "Unknown"
    # "01. HIGH TECH" -> "High Tech"
    parts = s.split(".", 1)
    return (parts[1] if len(parts) == 2 else s).strip().title()


projects, events = load_all()

main_p = projects[~projects["IS_SUS"]]
sus_p = projects[projects["IS_SUS"]]
main_e = events[~events["IS_SUS"]]
sus_e = events[events["IS_SUS"]]

new_proj_e = main_e[main_e["EVENT_TYPE"] == "NEW PROJECT"]
published_e = main_e[
    (main_e["EVENT_TYPE"] == "STAGE ADVANCE") & (main_e["NEW_VALUE"].isin(FINAL_STAGES))
]

available_months = sorted(
    set(new_proj_e[new_proj_e["YM"] >= "2026-01"]["YM"])
    | set(published_e[published_e["YM"] >= "2026-01"]["YM"])
)
if not available_months:
    available_months = ["2026-08"]

# The "150 goal" number - every STAGE ADVANCE -> IN CORTEX COMPLETE event
# in 2026, across US + Global + UK. Same value as "YTD published to
# Cortex" below - one number, shown twice (gauge + KPI).
countdown_count = int((published_e["YM"].str.startswith("2026")).sum())


# ---------------------------------------------------------------------------
# Chart helpers - one consistent look
# ---------------------------------------------------------------------------

def _base_layout(fig, height=340, legend=True):
    # Charts with a legend get their title as a Streamlit heading above the
    # chart instead of Plotly's own title (see call sites) - the two don't
    # share space reliably, so keeping them as separate elements avoids any
    # overlap outright rather than tuning coordinates to avoid it.
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=40 if legend else 30, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Lato, sans-serif", color=INK, size=13),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hoverlabel=dict(font_size=13, font_family="Lato, sans-serif"),
    )
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(91,31,148,0.08)", zeroline=False)
    return fig


def ranked_bar(df, cat_col, val_col, title, height=360):
    """Horizontal bar, sorted by value, single sequential plum ramp -
    sector/country comparison is magnitude ranking, not identity."""
    d = df.sort_values(val_col, ascending=True)
    vmax = d[val_col].max() or 1
    fig = go.Figure(go.Bar(
        x=d[val_col], y=d[cat_col], orientation="h",
        marker=dict(
            color=d[val_col], colorscale=[[0, PURPLE_PALE], [1, PLUM]], cmin=0, cmax=vmax,
            line=dict(width=0),
        ),
        text=d[val_col], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: <b>%{x}</b><extra></extra>",
    ))
    _base_layout(fig, height=height, legend=False)
    fig.update_layout(title=dict(text=title, font_size=15, x=0))
    return fig


def region_bar(counts, title, height=320):
    """One bar per region, fixed hue per region. `counts` is a Series
    indexed by raw REGION value."""
    counts = counts.sort_values(ascending=True)
    fig = go.Figure(go.Bar(
        x=counts.values, y=[r.title() for r in counts.index], orientation="h",
        marker_color=[REGION_COLORS.get(r, "#999") for r in counts.index],
        text=counts.values, textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: <b>%{x}</b><extra></extra>",
    ))
    _base_layout(fig, height=height, legend=False)
    fig.update_layout(title=dict(text=title, font_size=15, x=0))
    return fig


def goal_gauge(height=250):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=countdown_count,
        number={"font": {"color": PLUM, "family": "Merriweather"}},
        gauge={
            "axis": {"range": [0, max(QUOTA_GOAL, countdown_count) * 1.05], "tickcolor": PURPLE_LIGHT},
            "bar": {"color": PLUM},
            "steps": [{"range": [0, QUOTA_GOAL], "color": PURPLE_PALE}],
            "threshold": {"line": {"color": "#b8862c", "width": 4}, "thickness": 0.85, "value": QUOTA_GOAL},
        },
    ))
    fig.update_layout(height=height, margin=dict(l=20, r=20, t=50, b=10), paper_bgcolor="rgba(0,0,0,0)")
    return fig


# ===========================================================================
# PAGE NAVIGATOR (sidebar)
# ===========================================================================

NAV_PAGES = [
    ("overview", "🏠", "Overview"),
    ("monthly", "📅", "Monthly Detail"),
    ("ytd", "📈", "YTD Trends"),
    ("pipeline", "🔀", "Pipeline Health"),
    ("geo", "🌍", "Geography"),
    ("sector", "🏗️", "By Sector"),
    ("sustainability", "🌱", "Sustainability"),
]
PAGE_TITLE = {key: label for key, _, label in NAV_PAGES}

if "report_page" not in st.session_state:
    st.session_state.report_page = "overview"

with st.sidebar:
    st.markdown(
        "<div class='cb-sidebar-brand'><h1>Cortex Reporting</h1>"
        "<p>Currie &amp; Brown &middot; CBI</p></div>",
        unsafe_allow_html=True,
    )
    for key, icon, label in NAV_PAGES:
        active = st.session_state.report_page == key
        if st.button(f"{icon}  {label}", key=f"nav_{key}", use_container_width=True,
                     type="primary" if active else "secondary"):
            st.session_state.report_page = key
            st.rerun()

page = st.session_state.report_page

page_header(
    PAGE_TITLE[page],
    subtitle="Live from the tracker &middot; main pipeline (US &middot; Global &middot; UK)"
    if page != "sustainability" else "Live from the tracker &middot; Sustainability pipeline",
)

# ===========================================================================
# OVERVIEW
# ===========================================================================
if page == "overview":
    in_cortex_all = int((main_p["CURRENT_STAGE"] == "IN CORTEX COMPLETE").sum())
    ytd_new = int((new_proj_e["YM"].str.startswith("2026")).sum())

    k = st.columns(3)
    k[0].metric("In Cortex — all time", f"{in_cortex_all:,}")
    k[1].metric("YTD new shared", ytd_new)
    k[2].metric("Countries covered", main_p["COUNTRY"].nunique())

    st.markdown("---")
    st.markdown('<p class="cb-eyebrow">2026 Cortex Countdown &middot; US + Global + UK</p>', unsafe_allow_html=True)
    goal_col1, goal_col2 = st.columns([1, 2])
    with goal_col1:
        st.plotly_chart(goal_gauge(), use_container_width=True, config={"displayModeBar": False})
    with goal_col2:
        remaining = QUOTA_GOAL - countdown_count
        pct = countdown_count / QUOTA_GOAL if QUOTA_GOAL else 0
        m1, m2, m3 = st.columns(3)
        m1.metric("In Cortex so far this year", countdown_count)
        m2.metric("Goal", QUOTA_GOAL)
        if remaining > 0:
            m3.metric("Still to go", remaining)
        else:
            m3.metric("Over goal by", -remaining)
        st.caption(
            f"{pct:.0%} of the 2026 goal reached, counting US, Global and UK projects "
            "published to Cortex ('In Cortex Complete') in 2026."
        )

    st.markdown("---")
    total_main = len(main_p)
    st.markdown(
        f'<p class="cb-eyebrow">Main pipeline — where every project stands right now &middot; {total_main:,} total</p>',
        unsafe_allow_html=True,
    )
    stage_counts = main_p["CURRENT_STAGE"].value_counts()
    stage_shades = ["#e4d6f2", "#d0b8e8", "#b78fd9", "#9a5fd1", "#7a3bb5", PLUM]
    max_n = max((int(stage_counts.get(s, 0)) for s in MAIN_STAGES), default=0) or 1

    rows_html = (
        "<div style='background:#fff;border-radius:8px;padding:1.5rem 1.8rem;"
        "box-shadow:0 1px 4px rgba(91,31,148,.10);'>"
    )
    for s, shade in zip(MAIN_STAGES, stage_shades):
        n = int(stage_counts.get(s, 0))
        pct = round(100 * n / total_main, 1) if total_main else 0
        width = round(100 * n / max_n, 1)
        rows_html += f"""
        <div style='margin-bottom:1.15rem;'>
          <div style='display:flex;justify-content:space-between;align-items:baseline;margin-bottom:.4rem;'>
            <span style='font-size:.78rem;font-weight:700;color:#5a4a6a;letter-spacing:.04em;text-transform:uppercase;'>{MAIN_STAGE_SHORT[s]}</span>
            <span><b style='color:{PLUM};font-size:1.2rem;font-family:Merriweather,serif;'>{n:,}</b>
              <span style='color:#9a8aa8;font-size:.78rem;'>&nbsp;&middot; {pct}%</span></span>
          </div>
          <div style='background:{PURPLE_PALE};border-radius:20px;height:11px;overflow:hidden;'>
            <div style='width:{width}%;height:100%;border-radius:20px;background:linear-gradient(90deg,{shade},{PLUM});'></div>
          </div>
        </div>"""
    rows_html += "</div>"
    st.markdown(rows_html, unsafe_allow_html=True)

# ===========================================================================
# MONTHLY DETAIL
# ===========================================================================
elif page == "monthly":
    pick_col, _ = st.columns([1, 3])
    sel_month = pick_col.selectbox(
        "Reporting month", available_months, index=len(available_months) - 1, format_func=month_label,
    )

    published_this_month = int((published_e["YM"] == sel_month).sum())
    new_this_month = int((new_proj_e["YM"] == sel_month).sum())

    st.markdown('<p class="cb-eyebrow">Overview</p>', unsafe_allow_html=True)
    mc = st.columns(3)
    mc[0].metric("New projects shared", new_this_month)
    mc[1].metric("Published to Cortex", published_this_month)
    advanced_this_month = int(((main_e["EVENT_TYPE"] == "STAGE ADVANCE") & (main_e["YM"] == sel_month)).sum())
    mc[2].metric("Stage advances (all steps)", advanced_this_month)

    m_new = new_proj_e[new_proj_e["YM"] == sel_month].copy()
    m_pub = published_e[published_e["YM"] == sel_month].copy()

    st.markdown("---")
    st.markdown("#### New projects shared this month")
    c1, c2 = st.columns(2)
    with c1:
        if m_new.empty:
            st.caption("No new projects recorded this month.")
        else:
            m_new["S"] = m_new["SECTOR"].map(sector_short)
            sd = m_new.groupby("S").size().rename("N").reset_index()
            st.plotly_chart(ranked_bar(sd, "S", "N", "New projects shared this month, by sector"),
                            use_container_width=True, config={"displayModeBar": False})
    with c2:
        if m_new.empty:
            st.caption(" ")
        else:
            st.plotly_chart(region_bar(m_new.groupby("REGION").size(), "New projects shared this month, by region"),
                            use_container_width=True, config={"displayModeBar": False})

    st.markdown("---")
    st.markdown("#### Published to Cortex this month")
    if m_pub.empty:
        st.caption("Nothing reached Cortex this month.")
    else:
        m_pub["S"] = m_pub["SECTOR"].map(sector_short)
        pd1, pd2 = st.columns(2)
        with pd1:
            sd = m_pub.groupby("S").size().rename("N").reset_index()
            st.plotly_chart(ranked_bar(sd, "S", "N", "Published this month, by sector", height=320),
                            use_container_width=True, config={"displayModeBar": False})
        with pd2:
            st.plotly_chart(region_bar(m_pub.groupby("REGION").size(), "Published this month, by region", height=320),
                            use_container_width=True, config={"displayModeBar": False})

# ===========================================================================
# YTD TRENDS
# ===========================================================================
elif page == "ytd":
    st.markdown('<p class="cb-eyebrow">Year to date &middot; 2026</p>', unsafe_allow_html=True)

    ytd_published = countdown_count
    ytd_new = int((new_proj_e["YM"].str.startswith("2026")).sum())

    by_month = pd.DataFrame({"YM": [f"2026-{m:02d}" for m in range(1, 13)]})
    pub_m = published_e[published_e["YM"].str.startswith("2026")].groupby("YM").size().rename("Published")
    new_m = new_proj_e[new_proj_e["YM"].str.startswith("2026")].groupby("YM").size().rename("New shared")
    by_month = by_month.merge(pub_m, on="YM", how="left").merge(new_m, on="YM", how="left").fillna(0)
    by_month = by_month[by_month["YM"] <= available_months[-1]]
    by_month["Month"] = by_month["YM"].map(month_label)

    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure()
        fig.add_bar(x=by_month["Month"], y=by_month["New shared"], name="New shared with CBI",
                    marker_color="#c0aad0", hovertemplate="%{x}: <b>%{y}</b> new<extra></extra>")
        fig.add_scatter(x=by_month["Month"], y=by_month["Published"], name="Published to Cortex",
                        mode="lines+markers+text", line=dict(color=PLUM, width=3),
                        marker=dict(size=8), text=by_month["Published"].astype(int),
                        textposition="top center",
                        hovertemplate="%{x}: <b>%{y}</b> published<extra></extra>")
        _base_layout(fig, height=380)
        st.markdown("##### Monthly flow: shared vs published")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with c2:
        ytd_new_p = new_proj_e[new_proj_e["YM"].str.startswith("2026")].copy()
        ytd_new_p["S"] = ytd_new_p["SECTOR"].map(sector_short)
        sd = ytd_new_p.groupby("S").size().rename("N").reset_index()
        st.plotly_chart(ranked_bar(sd, "S", "N", "YTD new projects shared, by sector", height=380),
                        use_container_width=True, config={"displayModeBar": False})

    g = st.columns(4)
    ratio = round(ytd_new / ytd_published, 2) if ytd_published else 0
    g[0].metric("YTD new shared", ytd_new)
    g[1].metric("YTD published", ytd_published)
    g[2].metric("New : published ratio", ratio)
    g[3].metric("Quota remaining", max(QUOTA_GOAL - countdown_count, 0))

# ===========================================================================
# PIPELINE HEALTH
# ===========================================================================
elif page == "pipeline":
    st.markdown('<p class="cb-eyebrow">Where projects sit &mdash; and where they get stuck</p>', unsafe_allow_html=True)

    mp = main_p.copy()
    mp["S"] = mp["SECTOR"].map(sector_short)
    mp["StageShort"] = mp["CURRENT_STAGE"].map(MAIN_STAGE_SHORT)

    order_stages = [MAIN_STAGE_SHORT[s] for s in MAIN_STAGES]
    piv = pd.crosstab(mp["S"], mp["StageShort"]).reindex(columns=order_stages, fill_value=0)
    piv = piv.loc[piv.sum(axis=1).sort_values().index]
    fig = go.Figure()
    shades = ["#e4d6f2", "#d0b8e8", "#b78fd9", "#9a5fd1", "#7a3bb5", PLUM]
    for stage, shade in zip(order_stages, shades):
        fig.add_bar(y=piv.index, x=piv[stage], name=stage, orientation="h", marker_color=shade,
                    hovertemplate="%{y} - " + stage + ": <b>%{x}</b><extra></extra>")
    _base_layout(fig, height=640)
    fig.update_layout(barmode="stack")
    st.markdown("##### Current backlog by sector and stage")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# ===========================================================================
# GEOGRAPHY
# ===========================================================================
elif page == "geo":
    st.markdown('<p class="cb-eyebrow">Geographic coverage of the Cortex database (main pipeline)</p>', unsafe_allow_html=True)
    stage_filter = st.selectbox(
        "Show projects that are…",
        ["In Cortex (complete)", "Anywhere in the pipeline"] + [MAIN_STAGE_SHORT[s] for s in MAIN_STAGES[:-1]],
    )
    gp = main_p.copy()
    if stage_filter == "In Cortex (complete)":
        gp = gp[gp["CURRENT_STAGE"] == "IN CORTEX COMPLETE"]
    elif stage_filter != "Anywhere in the pipeline":
        target = {v: k for k, v in MAIN_STAGE_SHORT.items()}[stage_filter]
        gp = gp[gp["CURRENT_STAGE"] == target]

    gp = gp.copy()
    gp["MAP_COUNTRY"] = gp["COUNTRY"].map(to_map_country)
    by_country = gp[gp["MAP_COUNTRY"].notna()].groupby("MAP_COUNTRY").size().rename("N").reset_index()

    k = st.columns(3)
    k[0].metric("Countries covered", by_country["MAP_COUNTRY"].nunique())
    if not by_country.empty:
        top_row = by_country.sort_values("N", ascending=False).iloc[0]
        k[1].metric("Top country", top_row["MAP_COUNTRY"], f"{int(top_row['N']):,} projects")
    else:
        k[1].metric("Top country", "—")
    k[2].metric("Regions represented", gp["REGION"].nunique())

    st.markdown("---")
    st.markdown("##### World coverage")
    fig = px.choropleth(
        by_country, locations="MAP_COUNTRY", locationmode="country names", color="N",
        color_continuous_scale=[[0, PURPLE_PALE], [1, PLUM]],
        hover_name="MAP_COUNTRY",
    )
    fig.update_geos(
        showframe=False, showcoastlines=True, coastlinecolor="#c9bdd6",
        showcountries=True, countrycolor="#d4cdd9",
        showland=True, landcolor="#f2eef6", showocean=True, oceancolor=CREAM,
        projection_type="natural earth", bgcolor="rgba(0,0,0,0)",
    )
    fig.update_layout(title=dict(text=""))
    _base_layout(fig, height=560, legend=False)
    fig.update_layout(coloraxis_colorbar=dict(title="Projects"), margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    st.markdown("---")
    gc1, gc2 = st.columns(2)
    with gc1:
        top_countries = by_country.sort_values("N", ascending=False).head(12)
        st.plotly_chart(ranked_bar(top_countries, "MAP_COUNTRY", "N", "Top countries", height=440),
                        use_container_width=True, config={"displayModeBar": False})
    with gc2:
        rd = gp.groupby("REGION").size().rename("N").reset_index()
        rd["R"] = rd["REGION"].str.title()
        st.plotly_chart(ranked_bar(rd, "R", "N", "By region", height=440),
                        use_container_width=True, config={"displayModeBar": False})

# ===========================================================================
# BY SECTOR
# ===========================================================================
elif page == "sector":
    st.markdown('<p class="cb-eyebrow">Sectors &mdash; most and least represented in Cortex</p>', unsafe_allow_html=True)
    mp = main_p.copy()
    mp["S"] = mp["SECTOR"].map(sector_short)

    all_time = mp.groupby("S").size().rename("N").reset_index()
    in_cortex = mp[mp["CURRENT_STAGE"] == "IN CORTEX COMPLETE"].groupby("S").size().rename("In Cortex").reset_index()
    sd = all_time.merge(in_cortex, on="S", how="left").fillna(0)
    sd["In Cortex"] = sd["In Cortex"].astype(int)
    sd["In pipeline"] = sd["N"] - sd["In Cortex"]

    fig = go.Figure()
    d = sd.sort_values("N", ascending=True)
    fig.add_bar(y=d["S"], x=d["In Cortex"], name="In Cortex", orientation="h", marker_color=PLUM,
                hovertemplate="%{y}: <b>%{x}</b> in Cortex<extra></extra>")
    fig.add_bar(y=d["S"], x=d["In pipeline"], name="Still in pipeline", orientation="h", marker_color="#c0aad0",
                hovertemplate="%{y}: <b>%{x}</b> still in pipeline<extra></extra>")
    _base_layout(fig, height=420)
    fig.update_layout(barmode="stack")
    st.markdown("##### Projects per sector — in Cortex vs still working")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    top = sd.sort_values("N", ascending=False)
    a, b = st.columns(2)
    a.success(f"**Most data:** {top.iloc[0]['S']} ({int(top.iloc[0]['N'])} projects)")
    b.warning(f"**Least data:** {top.iloc[-1]['S']} ({int(top.iloc[-1]['N'])} projects)")

# ===========================================================================
# SUSTAINABILITY (its own report - never feeds main-pipeline totals)
# ===========================================================================
elif page == "sustainability":
    total = len(sus_p)
    in_cortex = int((sus_p["CURRENT_STAGE"] == "PUBLISHED TO CORTEX").sum())
    in_prog = int((sus_p["CURRENT_STAGE"] == "IN PROGRESS").sum())
    k = st.columns(4)
    k[0].metric("Sustainability projects — total", f"{total:,}")
    k[1].metric("Published to Cortex", in_cortex)
    k[2].metric("In progress", f"{in_prog:,}")
    k[3].metric("Countries", sus_p["COUNTRY"].nunique())

    st.markdown("---")
    s1, s2 = st.columns(2)
    with s1:
        stage_d = sus_p["CURRENT_STAGE"].value_counts().reindex(SUS_STAGES).fillna(0).reset_index()
        stage_d.columns = ["Stage", "N"]
        stage_d["Stage"] = stage_d["Stage"].str.title()
        fig = go.Figure(go.Bar(
            x=stage_d["Stage"], y=stage_d["N"], marker_color=["#cfe0cb", "#93b58c", "#5f8659", "#3e5b3e"],
            text=stage_d["N"].astype(int), textposition="outside", cliponaxis=False,
            hovertemplate="%{x}: <b>%{y}</b><extra></extra>",
        ))
        _base_layout(fig, height=360, legend=False)
        fig.update_layout(title=dict(text="Sustainability pipeline", font_size=15, x=0))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with s2:
        cd = sus_p.groupby("COUNTRY").size().rename("N").reset_index()
        cd = cd[cd["COUNTRY"].notna() & (cd["COUNTRY"] != "")].sort_values("N", ascending=True)
        fig = go.Figure(go.Bar(
            x=cd["N"], y=cd["COUNTRY"].str.title(), orientation="h",
            marker=dict(color=cd["N"], colorscale=[[0, "#d7e5d3"], [1, "#3e5b3e"]]),
            text=cd["N"], textposition="outside", cliponaxis=False,
            hovertemplate="%{y}: <b>%{x}</b><extra></extra>",
        ))
        _base_layout(fig, height=360, legend=False)
        fig.update_layout(title=dict(text="Sustainability projects by country", font_size=15, x=0))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
