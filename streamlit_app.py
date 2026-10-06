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
st.set_page_config(page_title="Datapaq .PAQ Analyzer & Furnace Profiler", page_icon="🔥", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
div[data-testid="stMetricValue"] { font-size: 1.8rem !important; font-weight: 700 !important; white-space: normal !important; line-height: 1.2 !important; }
div[data-testid="stMetricLabel"] { font-size: 1.1rem !important; font-weight: 500 !important; color: #a0aab2 !important; }
div.stButton > button:first-child { background-color: #ff4b4b; color: white; font-weight: bold; border-radius: 5px; width: 100%; margin-bottom: 20px; }
div.stButton > button:first-child:hover { background-color: #ff3333; border-color: #ff3333; }
button[data-baseweb="tab"] { font-size: 1.2rem !important; font-weight: 600 !important; }
div[data-testid="stAlert"] { font-size: 1.3rem !important; font-weight: 500 !important; padding: 1rem !important; }
</style>
""", unsafe_allow_html=True)

PROBE_COLORS = {"PB#1": "#ff0000", "PB#2": "#00ff00", "PB#3": "#0000ff", "PB#4": "#8b4513", "PB#5": "#ff00ff", "PB#6": "#b8860b", "PB#7": "#800080", "PB#8": "#00ffff"}
GROUP_COLORS = {"Dryer": "rgba(255, 235, 156, 0.15)", "Debinder": "rgba(255, 199, 119, 0.15)", "Heating": "rgba(255, 160, 160, 0.15)", "Cooling": "rgba(173, 216, 230, 0.15)"}

STANDARD_SPECS = {
    "NB1 (RAD)": {"id": "PRCNVR02044", "max": "Dryer: 175-260°C &nbsp;|&nbsp; Debinder: 200-375°C &nbsp;|&nbsp; Brazing: 583-607°C", "dwell": "Dryer ≥175°C ≥ 1.00 min &nbsp;|&nbsp; Debinder ≥200°C ≥ 2.00 min &nbsp;|&nbsp; Brazing ≥577°C = 2.30 - 7.00 min, ≥583°C ≥ 2.30 min"},
    "NB1 (CDS/KN9/12SHP)": {"id": "PRCNVR02004 Rev.E + 2025 DSR TDOC_101182039 CDS BRAZING CYCLE", "max": "Dryer: 200-350°C &nbsp;|&nbsp; Debinder: 300-375°C &nbsp;|&nbsp; Brazing: 585-607°C", "dwell": "Dryer ≥200°C ≥ 1.30 min &nbsp;|&nbsp; Debinder ≥300°C ≥ 2.30 min &nbsp;|&nbsp; Brazing ≥577°C = 4.00 - 7.45 min (PB#1, PB#5) / 2.00 - 7.45 min (Others)"},
    "NB3 (KE8 : M2/EVO)": {"id": "PRCNVR02059 + V-PAS/T88/Chon Buri 1/2025-10-29-ZVK (Evaporator M2 ,EVO)", "max": "Dryer: 200-375°C &nbsp;|&nbsp; Brazing: M2 = 595-602°C , EVO = 598-606°C", "dwell": "Dryer ≥200°C ≥ 1.30 min &nbsp;|&nbsp; Brazing ≥550°C = 7.00 - 10.30 min, ≥577°C = 4.30 - 7.00 min, ≥591°C = 1.30 - 4.00 min"},
    "NB2 (Tahc/Utahc)": {"id": "PRCNVR02050", "max": "Dryer: 200-375°C &nbsp;|&nbsp; Brazing: 596-604°C", "dwell": "Dryer ≥250°C ≥ 1.00 min &nbsp;|&nbsp; Brazing ≥577°C = 4.00 - 7.00 min, ≥591°C = 1.30 - 4.30 min"},
    "NB3 (BTM)": {"id": "PRCNVR02033", "max": "Dryer: 300-375°C &nbsp;|&nbsp; Brazing: 595-608°C", "dwell": "Dryer ≥300°C ≥ 2.00 min &nbsp;|&nbsp; Brazing ≥577°C = 4.00 - 14.00 min, ≥591°C = 2.00 - 12.00 min, ≥600°C ≤ 8.00 min"}
}

VALIDATION_RULES = {
    "NB1 (RAD)": {"Dryer Max (°C)": (175, 260), "Debinder Max (°C)": (200, 375), "Brazing Max (°C)": (583, 607), "Dryer Dwell (≥175°C)": (60, 99999), "Debinder Dwell (≥200°C)": (120, 99999), "Brazing Dwell (≥577°C)": (150, 420), "Brazing Dwell (≥583°C)": (150, 99999)},
    "NB1 (CDS/KN9/12SHP)": {"Dryer Max (°C)": (200, 350), "Debinder Max (°C)": (300, 375), "Brazing Max (°C)": (585, 607), "Dryer Dwell (≥200°C)": (90, 99999), "Debinder Dwell (≥300°C)": (150, 99999), "Brazing Dwell (≥577°C)": (120, 465)},
    "NB3 (KE8 : M2/EVO)": {"Dryer Max (°C)": (200, 375), "Brazing Max (°C)": (595, 606), "Dryer Dwell (≥200°C)": (90, 99999), "Brazing Dwell (≥550°C)": (420, 630), "Brazing Dwell (≥577°C)": (270, 420), "Brazing Dwell (≥591°C)": (90, 240)},
    "NB2 (Tahc/Utahc)": {"Dryer Max (°C)": (200, 375), "Brazing Max (°C)": (596, 604), "Dryer Dwell (≥250°C)": (60, 99999), "Brazing Dwell (≥577°C)": (240, 420), "Brazing Dwell (≥591°C)": (90, 270)},
    "NB3 (BTM)": {"Dryer Max (°C)": (300, 375), "Brazing Max (°C)": (595, 608), "Dryer Dwell (≥300°C)": (120, 99999), "Brazing Dwell (≥577°C)": (240, 840), "Brazing Dwell (≥591°C)": (120, 720), "Brazing Dwell (≥600°C)": (0, 480)}
}

def style_inspection_matrix(row, variant, check_dryer_max=False):
    styles = [''] * len(row)
    rules = VALIDATION_RULES.get(variant, {})
    probe_name = row.get("Probe", "")
    
    for i, col in enumerate(row.index):
        if col == "Probe": continue
        val = row[col]
        rule = rules.get(col)
        
        if variant == "NB1 (CDS/KN9/12SHP)" and col == "Brazing Dwell (≥577°C)":
            if probe_name in ["PB#1", "PB#5"]:
                rule = (240, 465)
            else:
                rule = (120, 465)
        
        if not check_dryer_max and ("Dryer Max" in col or "Dryer Dwell" in col):
            rule = None
            
        is_fail = False
        if pd.isna(val) or val == "00:00:00" or val == "" or val == 0:
            if rule and rule[0] > 0: is_fail = True
        else:
            if rule:
                min_v, max_v = rule
                if "Max (°C)" in col:
                    try:
                        if not (min_v <= float(val) <= max_v): is_fail = True
                    except: pass
                elif "Dwell" in col:
                    try:
                        parts = str(val).split(':')
                        if len(parts) == 3:
                            total_s = int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
                            if not (min_v <= total_s <= max_v): is_fail = True
                    except: pass
                    
        base_bg = ""
        if "Dryer" in col:
            base_bg = "background-color: rgba(255, 235, 156, 0.15);" 
        elif "Debinder" in col:
            base_bg = "background-color: rgba(255, 199, 119, 0.15);" 
        elif "Brazing" in col:
            base_bg = "background-color: rgba(255, 160, 160, 0.15);" 
            
        if rule:
            if is_fail: 
                styles[i] = f'background-color: rgba(255, 0, 0, 0.25); color: #ff5252; font-weight: bold; border: 1px solid #ff5252;'
            else: 
                styles[i] = f'{base_bg} color: #00e676; font-weight: bold;'
        else:
            styles[i] = f'{base_bg} color: #e0e0e0;'
            
    return styles

FURNACE_CONFIGS = {
    "NB1": {
        "line_speed_mpm": 1.400,
        "trigger_temp_brazing": 577.0,
        "zones": [
            {"num": 1, "name": "Dryer Z#1", "start": 0.00, "length": 3.15, "group": "Dryer"},
            {"num": 2, "name": "Dryer Z#2", "start": 3.15, "length": 3.13, "group": "Dryer"},
            {"num": 3, "name": "EXT Dryer", "start": 6.27, "length": 0.70, "group": "Dryer"},
            {"num": 4, "name": "ENT DB", "start": 6.97, "length": 0.67, "group": "Debinder"},
            {"num": 5, "name": "DB Z#1", "start": 7.64, "length": 3.13, "group": "Debinder"},
            {"num": 6, "name": "DB Z#2", "start": 10.77, "length": 2.60, "group": "Debinder"},
            {"num": 7, "name": "DB Z#3", "start": 13.37, "length": 2.60, "group": "Debinder"},
            {"num": 8, "name": "DB Z#4", "start": 15.97, "length": 3.13, "group": "Debinder"},
            {"num": 9, "name": "XFER#1", "start": 19.10, "length": 2.71, "group": "Heating"},
            {"num": 10, "name": "Z#1", "start": 21.81, "length": 3.14, "group": "Heating"},
            {"num": 11, "name": "Z#2", "start": 24.95, "length": 2.68, "group": "Heating"},
            {"num": 12, "name": "Z#3", "start": 27.63, "length": 2.72, "group": "Heating"},
            {"num": 13, "name": "Z#4", "start": 30.35, "length": 2.04, "group": "Heating"},
            {"num": 14, "name": "Z#5", "start": 32.39, "length": 2.00, "group": "Heating"},
            {"num": 15, "name": "Z#6", "start": 34.39, "length": 2.00, "group": "Heating"},
            {"num": 16, "name": "Z#7", "start": 36.39, "length": 2.29, "group": "Heating"},
            {"num": 17, "name": "WatCool#1", "start": 38.68, "length": 2.39, "group": "Cooling"},
            {"num": 18, "name": "WatCool#2", "start": 41.07, "length": 1.90, "group": "Cooling"},
            {"num": 19, "name": "Exit curtain box", "start": 42.97, "length": 1.90, "group": "Cooling"},
            {"num": 20, "name": "XFER#2", "start": 44.87, "length": 0.60, "group": "Cooling"},
            {"num": 21, "name": "Air Cool#1", "start": 45.47, "length": 1.25, "group": "Cooling"},
            {"num": 22, "name": "Air Cool#2", "start": 46.72, "length": 1.25, "group": "Cooling"},
            {"num": 23, "name": "Exit", "start": 47.97, "length": 1.85, "group": "Cooling"}
        ],
        "stages": [
            {"Stage": "Dryer", "Start (m)": 0.00, "End (m)": 6.28, "thresh": 200.0},
            {"Stage": "Debinder", "Start (m)": 7.64, "End (m)": 19.10, "thresh": 300.0},
            {"Stage": "Brazing", "Start (m)": 21.81, "End (m)": 42.97, "thresh": 577.0}
        ]
    },
    "NB2": {
        "line_speed_mpm": 1.560,
        "trigger_temp_brazing": 577.0,
        "zones": [
            {"num": 1, "name": "DryOff-Z#1", "start": 0.00, "length": 2.80, "group": "Dryer"},
            {"num": 2, "name": "DryOff-Z#2", "start": 2.80, "length": 2.80, "group": "Dryer"},
            {"num": 3, "name": "Xfer1", "start": 5.60, "length": 3.13, "group": "Dryer"},
            {"num": 4, "name": "Z#1", "start": 8.73, "length": 3.60, "group": "Heating"},
            {"num": 5, "name": "Z#2", "start": 12.33, "length": 2.70, "group": "Heating"},
            {"num": 6, "name": "Z#3", "start": 15.03, "length": 2.40, "group": "Heating"},
            {"num": 7, "name": "Z#4", "start": 17.43, "length": 2.10, "group": "Heating"},
            {"num": 8, "name": "Z#5", "start": 19.53, "length": 2.30, "group": "Heating"},
            {"num": 9, "name": "Z#6", "start": 21.83, "length": 1.90, "group": "Heating"},
            {"num": 10, "name": "Z#7", "start": 23.73, "length": 2.20, "group": "Heating"},
            {"num": 11, "name": "Xfer2", "start": 25.93, "length": 0.80, "group": "Heating"},
            {"num": 12, "name": "Watcol1", "start": 26.73, "length": 1.75, "group": "Cooling"},
            {"num": 13, "name": "Watcol2", "start": 28.48, "length": 1.85, "group": "Cooling"},
            {"num": 14, "name": "Exit curtain box", "start": 30.33, "length": 2.30, "group": "Cooling"},
            {"num": 15, "name": "Airc1", "start": 32.63, "length": 1.25, "group": "Cooling"},
            {"num": 16, "name": "Airc2", "start": 33.88, "length": 1.25, "group": "Cooling"},
            {"num": 17, "name": "Exit", "start": 35.13, "length": 1.80, "group": "Cooling"}
        ],
        "stages": [
            {"Stage": "Dryer", "Start (m)": 0.00, "End (m)": 5.60, "thresh": 200.0},
            {"Stage": "Brazing", "Start (m)": 8.73, "End (m)": 30.33, "thresh": 577.0}
        ]
    },
    "NB3": {
        "line_speed_mpm": 1.270,
        "trigger_temp_brazing": 577.0,
        "zones": [
            {"num": 1, "name": "XFER", "start": 0.00, "length": 0.10, "group": "Dryer"},
            {"num": 2, "name": "Dryer#1", "start": 0.10, "length": 1.85, "group": "Dryer"},
            {"num": 3, "name": "Dryer#2", "start": 1.95, "length": 1.85, "group": "Dryer"},
            {"num": 4, "name": "Dryer#3", "start": 3.80, "length": 1.95, "group": "Dryer"},
            {"num": 5, "name": "XFER#1", "start": 5.75, "length": 3.39, "group": "Dryer"},
            {"num": 6, "name": "Z#1", "start": 9.14, "length": 3.60, "group": "Heating"},
            {"num": 7, "name": "Z#2", "start": 12.74, "length": 2.75, "group": "Heating"},
            {"num": 8, "name": "Z#3", "start": 15.49, "length": 2.30, "group": "Heating"},
            {"num": 9, "name": "Z#4", "start": 17.79, "length": 2.10, "group": "Heating"},
            {"num": 10, "name": "Z#5", "start": 19.89, "length": 2.10, "group": "Heating"},
            {"num": 11, "name": "Z#6", "start": 21.99, "length": 1.90, "group": "Heating"},
            {"num": 12, "name": "Z#7", "start": 23.89, "length": 1.63, "group": "Heating"},
            {"num": 13, "name": "WatCoo#1", "start": 25.52, "length": 2.56, "group": "Cooling"},
            {"num": 14, "name": "WatCoo#2", "start": 28.08, "length": 1.90, "group": "Cooling"},
            {"num": 15, "name": "Exit curtain box", "start": 29.98, "length": 1.90, "group": "Cooling"},
            {"num": 16, "name": "XFER#2", "start": 31.88, "length": 0.60, "group": "Cooling"},
            {"num": 17, "name": "AirCoo#1", "start": 32.48, "length": 1.25, "group": "Cooling"},
            {"num": 18, "name": "AirCoo#2", "start": 33.73, "length": 1.25, "group": "Cooling"},
            {"num": 19, "name": "Exit", "start": 34.98, "length": 1.85, "group": "Cooling"}
        ],
        "stages": [
            {"Stage": "Dryer", "Start (m)": 0.00, "End (m)": 5.75, "thresh": 200.0},
            {"Stage": "Brazing", "Start (m)": 9.14, "End (m)": 29.98, "thresh": 577.0}
        ]
    }
}

def decompress_stream(ole_obj, stream_name):
    try:
        raw_data = ole_obj.openstream(stream_name).read()
        zlib_data = raw_data[8:] if raw_data.startswith(b'ZLIB') else raw_data
        try: return zlib.decompress(zlib_data)
        except: return zlib.decompress(zlib_data, -zlib.MAX_WBITS)
    except: return None

def extract_probe_series_autonomously(decomp_bytes):
    best_series = []
    for offset in range(0, min(12000, len(decomp_bytes) - 800), 1):
        rem = len(decomp_bytes) - offset
        cnt = rem // 8
        if cnt < 500: continue
        try: vals = struct.unpack(f"<{cnt}d", decomp_bytes[offset : offset + cnt * 8])
        except: continue
        clean_vals, glitch_count = [], 0
        for v in vals:
            if isinstance(v, float) and -10.0 <= v <= 650.0:
                clean_vals.append(v)
                glitch_count = 0
            else:
                glitch_count += 1
                if len(clean_vals) > 500:
                    if glitch_count <= 5: clean_vals.append(clean_vals[-1] if clean_vals else 0.0)
                    else: break
                elif glitch_count > 3: clean_vals = []
        if len(clean_vals) > len(best_series) and max(clean_vals) > 150.0:
            best_series = clean_vals
    return best_series

def format_dwell_time(total_seconds):
    if pd.isna(total_seconds) or total_seconds == 0: return "00:00:00"
    m, s = divmod(total_seconds, 60)
    h, m = divmod(m, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"

def clean_paq_text(raw_text):
    if not raw_text: return ""
    text = re.split(r'\\\\', raw_text)[0]
    parts = re.split(r'\b(?:CProbe|CSampleInterval|CAxisCustomUnits|CPaqfile|CByteDataArray|CProbeResult|CFurnaceRecipe|CZoom|CProbeMapEntry\w*|cho1-sv|CProcessFile|COven|CZone|CRecipe|CProduct|CAnalysisParameters|CAlarmParameters|CAlarmProbes|CAlarmParametersTime|CRiseFallRange|CTemperatureLimits|CTimeLimits|CCustomUnits|CLineSpeed|COvenStart|CProcessOptimisation|CToleranceCurve|CVersionInfo|CLogger|CSystemInfo|CMaximumMinimumAnalysisParameters|CTimeAtMeasurementAnalysisParameters)\b', text)
    cleaned_parts = []
    for p in parts:
        p = re.sub(r'^[>#;\.,\|]+', '', p).strip() 
        if len(p) < 3: continue
        
        p = re.sub(r'\b(Untitled|Entry Zone|XFER|WatCool|Exit curtain|AirCool|Exit Zone|Dryer#1|VSTS Exit Dryer|Exit Dryer|0Hl|!@f|"onB|aaa\.\.\.|FFGCC|bbbRRR|LNNSQ|OD@)\b', ' ', p, flags=re.IGNORECASE)
        
        if re.search(r'(.)\1{4,}', p) or re.search(r'[@^\$|~<>{}\[\]]{2,}', p) or re.search(r'^[0-9\W]+$', p): continue 
        p = re.sub(r'#[0-9]{3,}', '', p)
        p = re.sub(r'\s+', ' ', p).strip()
        if p and len(p) >= 3: cleaned_parts.append(p)
    return " ".join(cleaned_parts)

def parse_operator_and_metadata(comments_list):
    combined = " ".join(comments_list)
    op, site = "N/A", "N/A"
    comp = "VSTS"
    
    m_site = re.search(r'(Power\s+Chonburi|Chonburi|Plant\s+\d+|Factory\s+\d+)', combined, re.IGNORECASE)
    if m_site: site = m_site.group(1).strip()
    
    clean_notes = re.sub(r'^\s*CAlarm\s*', '', combined, flags=re.IGNORECASE)
    
    m_op = re.search(r'^([A-Za-z/]+)\s+(?:Datapaq|NB[1-3]|Monthly|WK|date|product|validation|run|test|DBLog|disconnected|Power|Chonburi|Plant|Factory)', clean_notes, re.IGNORECASE)
    if m_op: 
        op = m_op.group(1).strip()
    elif re.search(r'\b(Niwat|Sunisa|Mongkhon|Sompong|Operator)\b', clean_notes, re.IGNORECASE):
        op = re.search(r'\b(Niwat|Sunisa|Mongkhon|Sompong|Operator)\b', clean_notes, re.IGNORECASE).group(1).strip()

    log_marker = re.search(r'(disconnected:|DBLog Cleared:|DP2300|CommIn:LOGGER_|USB_NOTIFY_|TickRate|VBatt|\(USB_VALID\)|CommsIn\s+\d+|LoggerState_NewState:|trigger_search|DP\d{4}|Logger:|Battery:|Firmware:|Serial No:)', clean_notes, flags=re.IGNORECASE)
    if log_marker:
        clean_notes = clean_notes[:log_marker.start()].strip()
    
    for token in [op, "VSTS", site, "CAlarm"]:
        if token != "N/A":
            clean_notes = re.sub(rf'^\s*{re.escape(token)}\b\s*', '', clean_notes, flags=re.IGNORECASE)

    clean_notes = re.sub(r'NB\s+with\s+Debinder\s+NB\s+Furnace\s+Total\s*;\s*[\d,]+\s*mm', '', clean_notes, flags=re.IGNORECASE)
    
    clean_notes = re.split(r':?\s*NB\s*[1-3]\s*with\s*Debinder', clean_notes, flags=re.IGNORECASE)[0]
    
    chop_pattern = r'\b(NB\s*\d\s*DryOff|DryOff-Z|Xfer2\s*Watcol|Watcol1|AN\s*h8|ljjSQP|xwTLL)\b'
    split_notes = re.split(chop_pattern
