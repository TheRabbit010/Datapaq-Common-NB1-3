import io
import os
import re
import struct
import zlib
import numpy as np
import olefile
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image

# ==============================================================================
# STREAMLIT PAGE CONFIGURATION & CSS STYLING
# ==============================================================================
st.set_page_config(
    page_title="Datapaq .PAQ Analyzer & Furnace Profiler",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
div[data-testid="stMetricValue"] {
    font-size: 2.8rem !important;
    font-weight: 700 !important;
}
div[data-testid="stMetricLabel"] {
    font-size: 1.1rem !important;
    font-weight: 500 !important;
    color: #a0aab2 !important;
}
div.stButton > button:first-child {
    background-color: #ff4b4b;
    color: white;
    font-weight: bold;
    border-radius: 5px;
    width: 100%;
    margin-bottom: 20px;
}
div.stButton > button:first-child:hover {
    background-color: #ff3333;
    border-color: #ff3333;
}
button[data-baseweb="tab"] {
    font-size: 1.2rem !important;
    font-weight: 600 !important;
}
div[data-testid="stAlert"] {
    font-size: 1.3rem !important;
    font-weight: 500 !important;
    padding: 1rem !important;
}
</style>
""", unsafe_allow_html=True)

PROBE_COLORS = {
    "PB#1": "#ff0000", "PB#2": "#00ff00", "PB#3": "#0000ff", "PB#4": "#8b4513", 
    "PB#5": "#ff00ff", "PB#6": "#b8860b", "PB#7": "#800080", "PB#8": "#00ffff"
}

GROUP_COLORS = {
    "Dryer": "rgba(255, 235, 156, 0.15)", "Debinder": "rgba(255, 199, 119, 0.15)",
    "Heating": "rgba(255, 160, 160, 0.15)", "Cooling": "rgba(173, 216, 230, 0.15)"
}

# ==============================================================================
# PROCESS STANDARDS & VALIDATION RULES
# ==============================================================================
STANDARD_SPECS = {
    "NB1 (RAD)": {
        "id": "PRCNVR02044",
        "max": "Dryer: 175-260°C &nbsp;|&nbsp; Debinder: 200-375°C &nbsp;|&nbsp; Brazing: 583-607°C",
        "dwell": "Dryer ≥175°C ≥ 1.00 min &nbsp;|&nbsp; Debinder ≥200°C ≥ 2.00 min &nbsp;|&nbsp; Brazing ≥577°C = 2.30 - 7.00 min, ≥583°C ≥ 2.30 min"
    },
    "NB1 (CDS/KN9/12SHP)": {
        "id": "PRCNVR02004",
        "max": "Dryer: 200-350°C &nbsp;|&nbsp; Debinder: 300-375°C &nbsp;|&nbsp; Brazing: 585-607°C",
        "dwell": "Dryer ≥200°C ≥ 1.30 min &nbsp;|&nbsp; Debinder ≥300°C ≥ 2.30 min &nbsp;|&nbsp; Brazing ≥577°C = 4.00 - 7.45 min"
    },
    "NB3 (KE8/M2/EVO)": {
        "id": "PRCNVR02059",
        "max": "Dryer: 200-375°C &nbsp;|&nbsp; Brazing: 598-606°C",
        "dwell": "Dryer ≥200°C ≥ 1.30 min &nbsp;|&nbsp; Brazing ≥550°C = 7.00 - 10.30 min, ≥577°C = 4.30 - 7.00 min, ≥591°C = 1.30 - 4.00 min"
    },
    "NB2 (Tahc/Utahc)": {
        "id": "PRCNVR02050",
        "max": "Dryer: 200-375°C &nbsp;|&nbsp; Brazing: 596-604°C",
        "dwell": "Dryer ≥250°C ≥ 1.00 min &nbsp;|&nbsp; Brazing ≥577°C = 4.00 - 7.00 min, ≥591°C = 1.30 - 4.30 min"
    },
    "NB3 (BTM)": {
        "id": "PRCNVR02033",
        "max": "Dryer: 300-375°C &nbsp;|&nbsp; Brazing: 595-608°C",
        "dwell": "Dryer ≥300°C ≥ 2.00 min &nbsp;|&nbsp; Brazing ≥577°C = 4.00 - 14.00 min, ≥591°C = 2.00 - 12.00 min, ≥600°C ≤ 8.00 min"
    }
}

VALIDATION_RULES = {
    "NB1 (RAD)": {
        "Dryer Max (°C)": (175, 260), "Debinder Max (°C)": (200, 375), "Brazing Max (°C)": (583, 607),
        "Dryer Dwell (≥175°C)": (60, 99999), "Debinder Dwell (≥200°C)": (120, 99999),
        "Brazing Dwell (≥577°C)": (150, 420), "Brazing Dwell (≥583°C)": (150, 99999),
    },
    "NB1 (CDS/KN9/12SHP)": {
        "Dryer Max (°C)": (200, 350), "Debinder Max (°C)": (300, 375), "Brazing Max (°C)": (585, 607),
        "Dryer Dwell (≥200°C)": (90, 99999), "Debinder Dwell (≥300°C)": (150, 99999), "Brazing Dwell (≥577°C)": (240, 465),
    },
    "NB3 (KE8/M2/EVO)": {
        "Dryer Max (°C)": (200, 375), "Brazing Max (°C)": (598, 606),
        "Dryer Dwell (≥200°C)": (90, 99999), "Brazing Dwell (≥550°C)": (420, 630),
        "Brazing Dwell (≥577°C)": (270, 420), "Brazing Dwell (≥591°C)": (90, 240),
    },
    "NB2 (Tahc/Utahc)": {
        "Dryer Max (°C)": (200, 375), "Brazing Max (°C)": (596, 604),
        "Dryer Dwell (≥250°C)": (60, 99999), "Brazing Dwell (≥577°C)": (240, 420), "Brazing Dwell (≥591°C)": (90, 270),
    },
    "NB3 (BTM)": {
        "Dryer Max (°C)": (300, 375), "Brazing Max (°C)": (595, 608),
        "Dryer Dwell (≥300°C)": (120, 99999), "Brazing Dwell (≥577°C)": (240, 840),
        "Brazing Dwell (≥591°C)": (120, 720), "Brazing Dwell (≥600°C)": (0, 480),
    }
}

def style_inspection_matrix(row, variant):
    styles = [''] * len(row)
    rules = VALIDATION_RULES.get(variant, {})
    
    for i, col in enumerate(row.index):
        if col == "Probe": continue
        val = row[col]
        rule = rules.get(col)
        
        is_fail = False
        if pd.isna(val) or val == "00:00:00" or val == "" or val == 0:
            if rule and rule[0] > 0: is_fail = True
        else:
            if rule:
                min_v, max_v = rule
                if "Max (°C)" in col:
                    try:
