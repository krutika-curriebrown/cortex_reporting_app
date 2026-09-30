"""Shared visual theme for the Cortex reporting app. Bright purple chrome
(header + sidebar page-navigator) around white content cards, styled after
the Power BI report format Global Management already reads dashboards in -
a familiar shape, not a from-scratch design."""

import streamlit as st

PURPLE = "#3D1466"        # brand purple - chrome, chart primary
PURPLE_DARK = "#1F0938"   # sidebar gradient end, deepest accent
PURPLE_LIGHT = "#7A3FB0"  # hover / secondary accent
PURPLE_PALE = "#E4D6F2"   # chart low-end, step backgrounds

CB_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Lato:wght@300;400;700&family=Merriweather:wght@400;700&display=swap');

html, body, [class*="css"] {{ font-family:'Lato',sans-serif; background-color:#f5f2ef; color:#2c2c2c; }}
.stApp {{ background-color:#f5f2ef; }}
div[data-testid="stAppViewBlockContainer"] {{ padding-top: 1.2rem; }}

/* ---- sidebar page-navigator ---- */
section[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, {PURPLE} 0%, {PURPLE_DARK} 100%);
    width: 230px !important;
    min-width: 230px !important;
    max-width: 230px !important;
}}
/* Locks the width above - hide the drag handle so it can't be resized. */
div[data-testid="stSidebarResizeHandle"] {{ display: none !important; }}
section[data-testid="stSidebar"] > div {{ padding-top: 1rem; }}
section[data-testid="stSidebar"] .stButton > button {{
    background: transparent !important; border: none !important;
    color: #e6d9f5 !important; text-align: left !important; font-weight: 600 !important;
    font-family: 'Lato', sans-serif !important; font-size: .88rem !important;
    border-radius: 8px !important; padding: .6rem .9rem !important;
    letter-spacing: .02em !important; width: 100% !important; box-shadow: none !important;
    transition: background .15s ease;
}}
section[data-testid="stSidebar"] .stButton > button:hover {{
    background: rgba(255,255,255,.14) !important; color: #ffffff !important;
}}
section[data-testid="stSidebar"] .stButton > button[kind="primary"] {{
    background: #ffffff !important; color: {PURPLE_DARK} !important;
    box-shadow: 0 2px 8px rgba(0,0,0,.25) !important;
}}
.cb-sidebar-brand {{
    padding: .3rem 1rem 1.2rem; border-bottom: 1px solid rgba(255,255,255,.15); margin-bottom: .8rem;
}}
.cb-sidebar-brand h1 {{
    font-family: 'Merriweather', serif; font-size: 1.05rem; font-weight: 700; color: #fff !important; margin: 0;
}}
.cb-sidebar-brand p {{
    font-size: .68rem; color: #c9b3e0 !important; margin: .25rem 0 0;
    letter-spacing: .06em; text-transform: uppercase;
}}

/* ---- top bar ---- */
.cb-header {{
    background: {PURPLE}; padding: 1.1rem 1.6rem; margin: -1rem -1rem 1.3rem -1rem;
    display: flex; align-items: center; justify-content: space-between;
}}
.cb-header-left h1 {{ font-family:'Merriweather',serif; font-size:1.25rem; font-weight:700; color:#fff; margin:0; }}
.cb-header-left p  {{ font-size:.72rem; color:#d9c3ef; margin:.2rem 0 0; letter-spacing:.06em; text-transform:uppercase; }}

h1, h2, h3 {{ font-family:'Merriweather',serif; color:{PURPLE}; font-weight:700; margin-bottom:0.3rem; }}
.subtitle {{ color:#5a4a6a; font-size:16px; line-height:1.5; margin-top:0.5rem; }}
.cb-eyebrow {{ font-size:.72rem; color:{PURPLE_LIGHT}; letter-spacing:.08em; text-transform:uppercase; font-weight:700; margin:0 0 .4rem; }}

.welcome-box, .form-card, .content-card {{
    background-color:white; padding:1.5rem; border-radius:6px; border-left:6px solid {PURPLE};
    margin-bottom:1.5rem; box-shadow:0 2px 5px rgba(91,31,148,0.10);
}}

div[data-testid="stSelectbox"] > div > div {{
    background:#ffffff !important; border:1px solid #d4cdd9 !important; color:#2c2c2c !important;
    border-radius:3px !important; font-family:'Lato',sans-serif !important;
}}
label {{ color:#5a4a6a !important; font-size:.72rem !important; font-weight:700 !important; letter-spacing:.05em !important; text-transform:uppercase !important; }}

div[data-testid="stMainBlockContainer"] .stButton > button {{
    background:#ffffff !important; border:1px solid #c9bdd6 !important; color:{PURPLE} !important;
    font-family:'Lato',sans-serif !important; font-size:.85rem !important; font-weight:700 !important;
    padding:.5rem 1rem !important; border-radius:20px !important; letter-spacing:.03em !important;
}}
div[data-testid="stMainBlockContainer"] .stButton > button:hover {{ background:{PURPLE} !important; border-color:{PURPLE} !important; color:#fff !important; }}

.stDataFrame, div[data-testid="stDataFrameResizable"] {{ border:1px solid #c9bdd6 !important; border-radius:6px; }}

div[data-testid="stMetric"] {{
    background-color:white; padding:0.8rem; border-radius:6px; border-left:4px solid {PURPLE_LIGHT};
    box-shadow:0 1px 4px rgba(91,31,148,0.10);
}}

hr {{ border-color:#ddd5e5 !important; }}
footer {{visibility: hidden;}}
[data-testid="collapsedControl"] {{ color: {PURPLE} !important; }}
</style>
"""


def apply_theme():
    st.markdown(CB_CSS, unsafe_allow_html=True)


def page_header(title, subtitle="Currie &amp; Brown &middot; Construction Business Intelligence"):
    st.markdown(f"""
    <div class="cb-header">
      <div class="cb-header-left">
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
    </div>""", unsafe_allow_html=True)
