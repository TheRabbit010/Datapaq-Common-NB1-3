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
div[data-testid="stMetricValue"] { font-size: 2.8rem !important; font-weight: 700 !important; }
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
    "NB1 (CDS/KN9/12SHP)": {"id": "PRCNVR02004", "max": "Dryer: 200-350°C &nbsp;|&nbsp; Debinder: 300-375°C &nbsp;|&nbsp; Brazing: 585-607°C", "dwell": "Dryer ≥200°C ≥ 1.30 min &nbsp;|&nbsp; Debinder ≥300°C ≥ 2.30 min &nbsp;|&nbsp; Brazing ≥577°C = 4.00 - 7.45 min"},
    "NB3 (KE8/M2/EVO)": {"id": "PRCNVR02059", "max": "Dryer: 200-375°C &nbsp;|&nbsp; Brazing: 598-606°C", "dwell": "Dryer ≥200°C ≥ 1.30 min &nbsp;|&nbsp; Brazing ≥550°C = 7.00 - 10.30 min, ≥577°C = 4.30 - 7.00 min, ≥591°C = 1.30 - 4.00 min"},
    "NB2 (Tahc/Utahc)": {"id": "PRCNVR02050", "max": "Dryer: 200-375°C &nbsp;|&nbsp; Brazing: 596-604°C", "dwell": "Dryer ≥250°C ≥ 1.00 min &nbsp;|&nbsp; Brazing ≥577°C = 4.00 - 7.00 min, ≥591°C = 1.30 - 4.30 min"},
    "NB3 (BTM)": {"id": "PRCNVR02033", "max": "Dryer: 300-375°C &nbsp;|&nbsp; Brazing: 595-608°C", "dwell": "Dryer ≥300°C ≥ 2.00 min &nbsp;|&nbsp; Brazing ≥577°C = 4.00 - 14.00 min, ≥591°C = 2.00 - 12.00 min, ≥600°C ≤ 8.00 min"}
}

VALIDATION_RULES = {
    "NB1 (RAD)": {"Dryer Max (°C)": (175, 260), "Debinder Max (°C)": (200, 375), "Brazing Max (°C)": (583, 607), "Dryer Dwell (≥175°C)": (60, 99999), "Debinder Dwell (≥200°C)": (120, 99999), "Brazing Dwell (≥577°C)": (150, 420), "Brazing Dwell (≥583°C)": (150, 99999)},
    "NB1 (CDS/KN9/12SHP)": {"Dryer Max (°C)": (200, 350), "Debinder Max (°C)": (300, 375), "Brazing Max (°C)": (585, 607), "Dryer Dwell (≥200°C)": (90, 99999), "Debinder Dwell (≥300°C)": (150, 99999), "Brazing Dwell (≥577°C)": (240, 465)},
    "NB3 (KE8/M2/EVO)": {"Dryer Max (°C)": (200, 375), "Brazing Max (°C)": (598, 606), "Dryer Dwell (≥200°C)": (90, 99999), "Brazing Dwell (≥550°C)": (420, 630), "Brazing Dwell (≥577°C)": (270, 420), "Brazing Dwell (≥591°C)": (90, 240)},
    "NB2 (Tahc/Utahc)": {"Dryer Max (°C)": (200, 375), "Brazing Max (°C)": (596, 604), "Dryer Dwell (≥250°C)": (60, 99999), "Brazing Dwell (≥577°C)": (240, 420), "Brazing Dwell (≥591°C)": (90, 270)},
    "NB3 (BTM)": {"Dryer Max (°C)": (300, 375), "Brazing Max (°C)": (595, 608), "Dryer Dwell (≥300°C)": (120, 99999), "Brazing Dwell (≥577°C)": (240, 840), "Brazing Dwell (≥591°C)": (120, 720), "Brazing Dwell (≥600°C)": (0, 480)}
}

def style_inspection_matrix(row, variant, check_dryer_max=False):
    styles = [''] * len(row)
    rules = VALIDATION_RULES.get(variant, {})
    for i, col in enumerate(row.index):
        if col == "Probe": continue
        val = row[col]
        rule = rules.get(col)
        
        # --- เงื่อนไขสำหรับข้ามการเช็คสีแดงของ Dryer Max หากผู้ใช้ไม่ได้ติ๊กเลือก ---
        if not check_dryer_max and "Dryer Max" in col:
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
        if rule:
            if is_fail: styles[i] = 'background-color: rgba(255, 0, 0, 0.15); color: #ff4444; font-weight: bold;'
            else: styles[i] = 'color: #00e676;'
    return styles

FURNACE_CONFIGS = {
    "NB1": {"line_speed_mpm": 1.400, "trigger_temp_brazing": 577.0,
        "zones": [{"num": 1, "name": "Dryer Z#1", "start": 0.00, "length": 3.15, "group": "Dryer"}, {"num": 2, "name": "Dryer Z#2", "start": 3.15, "length": 3.13, "group": "Dryer"}, {"num": 3, "name": "EXT Dryer", "start": 6.27, "length": 0.70, "group": "Dryer"}, {"num": 4, "name": "ENT DB", "start": 6.97, "length": 0.67, "group": "Debinder"}, {"num": 5, "name": "DB Z#1", "start": 7.64, "length": 3.13, "group": "Debinder"}, {"num": 6, "name": "DB Z#2", "start": 10.77, "length": 2.60, "group": "Debinder"}, {"num": 7, "name": "DB Z#3", "start": 13.37, "length": 2.60, "group": "Debinder"}, {"num": 8, "name": "DB Z#4", "start": 15.97, "length": 3.13, "group": "Debinder"}, {"num": 9, "name": "XFER#1", "start": 19.10, "length": 2.71, "group": "Heating"}, {"num": 10, "name": "Z#1", "start": 21.81, "length": 3.14, "group": "Heating"}, {"num": 11, "name": "Z#2", "start": 24.95, "length": 2.68, "group": "Heating"}, {"num": 12, "name": "Z#3", "start": 27.63, "length": 2.72, "group": "Heating"}, {"num": 13, "name": "Z#4", "start": 30.35, "length": 2.04, "group": "Heating"}, {"num": 14, "name": "Z#5", "start": 32.39, "length": 2.00, "group": "Heating"}, {"num": 15, "name": "Z#6", "start": 34.39, "length": 2.00, "group": "Heating"}, {"num": 16, "name": "Z#7", "start": 36.39, "length": 2.29, "group": "Heating"}, {"num": 17, "name": "WatCool#1", "start": 38.68, "length": 2.39, "group": "Cooling"}, {"num": 18, "name": "WatCool#2", "start": 41.07, "length": 1.90, "group": "Cooling"}, {"num": 19, "name": "Exit curtain box", "start": 42.97, "length": 1.90, "group": "Cooling"}, {"num": 20, "name": "XFER#2", "start": 44.87, "length": 0.60, "group": "Cooling"}, {"num": 21, "name": "Air Cool#1", "start": 45.47, "length": 1.25, "group": "Cooling"}, {"num": 22, "name": "Air Cool#2", "start": 46.72, "length": 1.25, "group": "Cooling"}, {"num": 23, "name": "Exit", "start": 47.97, "length": 1.85, "group": "Cooling"}],
        "stages": [{"Stage": "Dryer", "Start (m)": 0.00, "End (m)": 6.28, "thresh": 200.0}, {"Stage": "Debinder", "Start (m)": 7.64, "End (m)": 19.10, "thresh": 300.0}, {"Stage": "Brazing", "Start (m)": 21.81, "End (m)": 42.97, "thresh": 577.0}]},
    "NB2": {"line_speed_mpm": 1.560, "trigger_temp_brazing": 577.0,
        "zones": [{"num": 1, "name": "DryOff-Z#1", "start": 0.00, "length": 2.80, "group": "Dryer"}, {"num": 2, "name": "DryOff-Z#2", "start": 2.80, "length": 2.80, "group": "Dryer"}, {"num": 3, "name": "Xfer1", "start": 5.60, "length": 3.13, "group": "Dryer"}, {"num": 4, "name": "Z#1", "start": 8.73, "length": 3.60, "group": "Heating"}, {"num": 5, "name": "Z#2", "start": 12.33, "length": 2.70, "group": "Heating"}, {"num": 6, "name": "Z#3", "start": 15.03, "length": 2.40, "group": "Heating"}, {"num": 7, "name": "Z#4", "start": 17.43, "length": 2.10, "group": "Heating"}, {"num": 8, "name": "Z#5", "start": 19.53, "length": 2.30, "group": "Heating"}, {"num": 9, "name": "Z#6", "start": 21.83, "length": 1.90, "group": "Heating"}, {"num": 10, "name": "Z#7", "start": 23.73, "length": 2.20, "group": "Heating"}, {"num": 11, "name": "Xfer2", "start": 25.93, "length": 0.80, "group": "Heating"}, {"num": 12, "name": "Watcol1", "start": 26.73, "length": 1.75, "group": "Cooling"}, {"num": 13, "name": "Watcol2", "start": 28.48, "length": 1.85, "group": "Cooling"}, {"num": 14, "name": "Exit curtain box", "start": 30.33, "length": 2.30, "group": "Cooling"}, {"num": 15, "name": "Airc1", "start": 32.63, "length": 1.25, "group": "Cooling"}, {"num": 16, "name": "Airc2", "start": 33.88, "length": 1.25, "group": "Cooling"}, {"num": 17, "name": "Exit", "start": 35.13, "length": 1.80, "group": "Cooling"}],
        "stages": [{"Stage": "Dryer", "Start (m)": 0.00, "End (m)": 5.60, "thresh": 200.0}, {"Stage": "Brazing", "Start (m)": 8.73, "End (m)": 30.33, "thresh": 577.0}]},
    "NB3": {"line_speed_mpm": 1.270, "trigger_temp_brazing": 577.0,
        "zones": [{"num": 1, "name": "XFER", "start": 0.00, "length": 0.10, "group": "Dryer"}, {"num": 2, "name": "Dryer#1", "start": 0.10, "length": 1.85, "group": "Dryer"}, {"num": 3, "name": "Dryer#2", "start": 1.95, "length": 1.85, "group": "Dryer"}, {"num": 4, "name": "Dryer#3", "start": 3.80, "length": 1.95, "group": "Dryer"}, {"num": 5, "name": "XFER#1", "start": 5.75, "length": 3.39, "group": "Dryer"}, {"num": 6, "name": "Z#1", "start": 9.14, "length": 3.60, "group": "Heating"}, {"num": 7, "name": "Z#2", "start": 12.74, "length": 2.75, "group": "Heating"}, {"num": 8, "name": "Z#3", "start": 15.49, "length": 2.30, "group": "Heating"}, {"num": 9, "name": "Z#4", "start": 17.79, "length": 2.10, "group": "Heating"}, {"num": 10, "name": "Z#5", "start": 19.89, "length": 2.10, "group": "Heating"}, {"num": 11, "name": "Z#6", "start": 21.99, "length": 1.90, "group": "Heating"}, {"num": 12, "name": "Z#7", "start": 23.89, "length": 1.63, "group": "Heating"}, {"num": 13, "name": "WatCoo#1", "start": 25.52, "length": 2.56, "group": "Cooling"}, {"num": 14, "name": "WatCoo#2", "start": 28.08, "length": 1.90, "group": "Cooling"}, {"num": 15, "name": "Exit curtain box", "start": 29.98, "length": 1.90, "group": "Cooling"}, {"num": 16, "name": "XFER#2", "start": 31.88, "length": 0.60, "group": "Cooling"}, {"num": 17, "name": "AirCoo#1", "start": 32.48, "length": 1.25, "group": "Cooling"}, {"num": 18, "name": "AirCoo#2", "start": 33.73, "length": 1.25, "group": "Cooling"}, {"num": 19, "name": "Exit", "start": 34.98, "length": 1.85, "group": "Cooling"}],
        "stages": [{"Stage": "Dryer", "Start (m)": 0.00, "End (m)": 5.75, "thresh": 200.0}, {"Stage": "Brazing", "Start (m)": 9.14, "End (m)": 29.98, "thresh": 577.0}]}
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
    parts = re.split(r'\b(?:CProbe|CSampleInterval|CAxisCustomUnits|CPaqfile|CByteDataArray|CProbeResult|CFurnaceRecipe|CZoom|CProbeMapEntry\w*|cho1-sv|CProcessFile|COven|CZone|CRecipe|CProduct|CAnalysisParameters|CAlarmParameters|CAlarmProbes|CAlarmParametersTime|CRiseFallRange|CTemperatureLimits|CTimeLimits|CCustomUnits|CLineSpeed|COvenStart|CProcessOptimisation|CToleranceCurve)\b', text)
    cleaned_parts = []
    for p in parts:
        p = re.sub(r'^[>#;\.,\|]+', '', p).strip() 
        if len(p) < 3: continue
        if re.search(r'\b(Untitled|Entry Zone|XFER|WatCool|Exit curtain|AirCool|Exit Zone|Dryer#1|VSTS Exit Dryer|Exit Dryer|0Hl|!@f|"onB|aaa\.\.\.|FFGCC|bbbRRR|LNNSQ|OD@)\b', p, re.IGNORECASE):
            clean_segment = re.split(r'\b(Untitled|Entry Zone|XFER|WatCool|Exit curtain|AirCool|Exit Zone|Dryer#1|VSTS Exit Dryer|Exit Dryer|0Hl|!@f|"onB|aaa\.\.\.|FFGCC|bbbRRR|LNNSQ|OD@)\b', p, flags=re.IGNORECASE)[0]
            if clean_segment.strip(): cleaned_parts.append(clean_segment.strip())
            break 
        if re.search(r'(.)\1{3,}', p) or re.search(r'[@^\$|~<>{}\[\]]{2,}', p) or re.search(r'^[0-9\W]+$', p): continue 
        p = re.sub(r'#\d+', '', p)
        p = re.sub(r'\s+', ' ', p).strip()
        if p and len(p) >= 3: cleaned_parts.append(p)
    return " ".join(cleaned_parts)

def parse_operator_and_metadata(comments_list):
    combined = " ".join(comments_list)
    op, site = "N/A", "N/A"
    
    # --- บังคับให้เป็นชื่อบริษัท VSTS ตามที่ระบุมา ---
    comp = "VSTS"
    # ----------------------------------------
    
    m_site = re.search(r'(Power\s+Chonburi|Chonburi|Plant\s+\d+|Factory\s+\d+)', combined, re.IGNORECASE)
    if m_site: site = m_site.group(1).strip()
    
    combined_clean_start = re.sub(r'^\s*CAlarm\s*', '', combined, flags=re.IGNORECASE)
    m_op = re.search(r'^([A-Za-z/]+)\s+(?:Monthly|WK|date|product|validation|run|test)', combined_clean_start, re.IGNORECASE)
    if m_op: op = m_op.group(1).strip()
    elif "Niwat" in combined_clean_start: op = "Niwat"
    elif "Sunisa" in combined_clean_start: op = "Sunisa"

    chopped_comment = re.split(r'\b(Untitled|Entry Zone|VSTS Exit Dryer|Exit Dryer|0Hl|!@f|"onB|aaa\.\.\.|FFGCC|bbbRRR|LNNSQ|OD@)\b', combined_clean_start, flags=re.IGNORECASE)[0]
    clean_notes = chopped_comment
    
    for token in [op, "Datapaq", "VSTS", site, "CAlarm"]:
        if token != "N/A":
            clean_notes = re.sub(rf'^\s*{re.escape(token)}\b\s*', '', clean_notes, flags=re.IGNORECASE)
            clean_notes = re.sub(rf'\s+\b{re.escape(token)}\b\s+', ' ', clean_notes, flags=re.IGNORECASE)

    split_match = re.search(r'(.*?)(?:\s+)?\b([A-Za-z]?Middle\s+left|[A-Za-z]?Middle\s+right|[A-Za-z]?Left\s+core|[A-Za-z]?Right\s+core|Bottom cooler|Top cooler)\b', clean_notes, flags=re.IGNORECASE)
    if split_match: clean_notes = split_match.group(1).strip()
    
    clean_notes = re.sub(r'NB\s+with\s+Debinder\s+NB\s+Furnace\s+Total\s*;\s*[\d,]+\s*mm', '', clean_notes, flags=re.IGNORECASE)
    clean_notes = re.sub(r'\b(Dryer Z|Air Cool|Exit|EXT Dryer|ENT DB|DB Z|RAD|SU2|12XHP|68T|G100|CV2-2-2|NB1|12XHP68Tube)\b', '', clean_notes, flags=re.IGNORECASE)
    garbage_regex = r'(C:\\Program Files|IJ@1|a@FGr|YW@\.|dhmquz|QUZ|rx\s+knv|V\^e|ipyw~|MSYmqw~|AFMEKO|FIL257|CVersionInfo|1w-!|zfo@|8gDi|R@\?m|MQTDFI|HKN\*,|CAlarmParametersDouble|CMaximumMinimumAnalysisParameters)'
    clean_notes = re.split(garbage_regex, clean_notes, flags=re.IGNORECASE)[0]
    clean_notes = re.sub(r'\s{2,}', ' ', clean_notes)
    clean_notes = re.sub(r'^[.,;\s]+', '', clean_notes)
    clean_notes = re.sub(r'[\.,\s]+$', '.', clean_notes).strip()
    
    return op, comp, site, clean_notes if clean_notes else "N/A"

def clean_probe_location(loc_desc):
    loc_desc = re.sub(r'^[^A-Za-z]*(Top|Bottom|Middle|Left|Right|Core)', r'\1', loc_desc, flags=re.IGNORECASE)
    return re.sub(r'\b[A-Z](Left|Right|Middle|Bottom|Top)\b', r'\1', loc_desc, flags=re.IGNORECASE)

@st.cache_data
def process_paq_file(file_bytes, filename):
    ole_bytes = io.BytesIO(file_bytes)
    ole = olefile.OleFileIO(ole_bytes)
    probe_streams = [s for s in ole.listdir() if len(s) >= 4 and s[0] == 'Paqfiles' and s[2] == 'ProbeResults']
    probe_streams = sorted(probe_streams, key=lambda x: x[-1])

    all_probes = {}
    for stream_path in probe_streams:
        stream_name = "/".join(stream_path)
        probe_folder = stream_path[-1]
        probe_num = int(''.join(filter(str.isdigit, probe_folder))) + 1 if any(c.isdigit() for c in probe_folder) else len(all_probes) + 1
        col_name = f"PB#{probe_num}"
        d = decompress_stream(ole, stream_name)
        if d:
            series = extract_probe_series_autonomously(d)
            if series: all_probes[col_name] = series

    if not all_probes: return None

    max_samples = max(len(v) for v in all_probes.values())
    aligned_probes = {k: (v + [np.nan] * (max_samples - len(v)) if len(v) < max_samples else v) for k, v in all_probes.items()}
    df_master = pd.DataFrame(aligned_probes)
    df_master.insert(0, "Time_Seconds", range(len(df_master)))
    base_date = pd.Timestamp("1970-01-01 00:00:00")
    df_master.insert(1, "Time_Stamp", base_date + pd.to_timedelta(df_master["Time_Seconds"], unit="s"))
    df_master.insert(2, "Time_HHMMSS", df_master["Time_Stamp"].dt.strftime('%H:%M:%S'))

    probe_cols = [col for col in df_master.columns if col.startswith("PB#")]
    SUSTAINED_SECONDS = 15
    probe_start_secs = {}
    for col in probe_cols:
        is_p60 = (df_master[col] >= 60.0)
        valid_p_mask = is_p60.copy()
        for i in range(1, SUSTAINED_SECONDS):
            valid_p_mask = valid_p_mask & is_p60.shift(-i, fill_value=False)
        probe_start_secs[col] = int(df_master[valid_p_mask].iloc[0]["Time_Seconds"]) if valid_p_mask.any() else 0

    valid_starts = [sec for sec in probe_start_secs.values() if sec > 0]
    detected_start_sec = min(valid_starts) if valid_starts else 0
    first_probe_name = [k for k, v in probe_start_secs.items() if v == detected_start_sec][0] if valid_starts else probe_cols[0]
    detected_start_hhmmss = df_master[df_master["Time_Seconds"] == detected_start_sec].iloc[0]["Time_HHMMSS"]

    raw_texts = []
    embedded_img = None
    for stream_path in ole.listdir():
        try:
            raw_b = ole.openstream(stream_path).read()
            if not raw_b: continue
            data_b = raw_b
            if raw_b.startswith(b'ZLIB') or b'x\x9c' in raw_b[:20]:
                try: data_b = zlib.decompress(raw_b[8:] if raw_b.startswith(b'ZLIB') else raw_b)
                except:
                    try: data_b = zlib.decompress(raw_b[8:] if raw_b.startswith(b'ZLIB') else raw_b, -zlib.MAX_WBITS)
                    except: pass
            if embedded_img is None and len(data_b) > 500:
                for header in [b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff', b'BM']:
                    idx = data_b.find(header)
                    if idx != -1:
                        try:
                            embedded_img = Image.open(io.BytesIO(data_b[idx:]))
                            break
                        except: pass
            ascii_matches = re.findall(rb'[\x20-\x7E]{4,}', data_b)
            for m in ascii_matches: raw_texts.append(m.decode('ascii', errors='ignore').strip())
        except: continue

    found_comments, found_recipes, found_probes = [], [], []
    for s in raw_texts:
        # --- ดักจับ Recipe ก่อนถูกคำสั่ง skip หากมี \ ปะปนมา ---
        is_recipe = re.search(r'\b(O2 Exit|ppm|CV speed|mm/min|N2 Flow|WJ Flow|Top Temp|Bot temp|SP1|SP2\s*==>|Braze Temp)\b', s, re.IGNORECASE)
        if is_recipe:
            s_rec = re.sub(r'\b(?:CProcessFile|COven|CZone|CRecipe|CProduct|CAnalysisParameters|CToleranceCurve|CAlarmParametersDouble|CMaximumMinimumAnalysisParameters|CTimeAtMeasurementAnalysisParameters|CRiseFallAnalysisParameters|CSlopeAnalysisParameters|CPeakDifferenceAnalysisParameters|CAreaUnderCurveAnalysisParameters|CFurnaceSurveyAnalysisParameters)\b', '', s).strip()
            s_rec = re.sub(r'[A-Za-z]:\\[^\s]+', '', s_rec) # ลบ path ไฟล์ที่อาจติดมาเช่น C:\Program Files
            s_rec = re.sub(r'^[>#;\.,\|]+', '', s_rec).strip()
            s_rec = re.sub(r'\bdouble m\b', '', s_rec).strip() # ลบคำขยะข้างๆ
            s_rec = re.sub(r'(WJ Flow)', r'\n\1', s_rec)
            s_rec = re.sub(r'(NB Top Temp)', r'\n\1', s_rec)
            s_rec = re.sub(r'(NB Bot temp)', r'\n\1', s_rec)
            s_rec = re.sub(r'(Braze Temp)', r'\n\1', s_rec)
            if s_rec and s_rec not in found_recipes: found_recipes.append(s_rec)
            continue
        
        if re.search(r'\\\\|\b[A-Z]:\\', s) or re.search(r'\.(ovn|prd|pro|rec|paq|jpg|png|bmp)\b', s, re.IGNORECASE) or re.search(r'\\Users\\|Desktop', s, re.IGNORECASE): continue
        s_clean = clean_paq_text(s)
        if not s_clean: continue
        is_probe = re.search(r'\b(cooler|drill&insert|inside H/D|manifold|core)\b', s_clean, re.IGNORECASE)
        if is_probe:
            if s_clean not in found_probes: found_probes.append(s_clean)
        else:
            if s_clean not in found_comments: found_comments.append(s_clean)

    probe_locations = {}
    for p in found_probes:
        m = re.search(r'^#?([1-8])\s*[\(°C\)]*\s*[-:]?\s*(.+)', p)
        if m:
            idx = int(m.group(1))
            ch_key = f"PB#{idx}"
            loc_desc = clean_probe_location(m.group(2).strip())
            label = f"#{idx} (°C) {loc_desc}"
            if ch_key not in probe_locations or len(label) > len(probe_locations[ch_key]):
                probe_locations[ch_key] = label
    unassigned_probes = [p for p in found_probes if not re.search(r'^#?[1-8]\s*[\(°C\)]', p)]
    assigned_idx = 1
    for p in unassigned_probes:
        while f"PB#{assigned_idx}" in probe_locations and assigned_idx <= 8: assigned_idx += 1
        if assigned_idx > 8: break
        probe_locations[f"PB#{assigned_idx}"] = f"#{assigned_idx} (°C) {clean_probe_location(p)}"
        assigned_idx += 1
    for col in probe_cols:
        if col not in probe_locations: probe_locations[col] = f"Channel {col.replace('PB#', '')} (Unlabeled)"

    operator_name, company, site, clean_comments_text = parse_operator_and_metadata(found_comments)
    process_settings = "\n".join(found_recipes) if found_recipes else "Standard Recipe Parameters"
    recipe_corpus = f"{process_settings} {clean_comments_text} {filename}"

    furnace_id, furnace_variant = "NB3", "NB3"
    if re.search(r'\bRAD\b', recipe_corpus, re.IGNORECASE): furnace_id, furnace_variant = "NB1", "NB1 (RAD)"
    elif re.search(r'\b(KE8|M2|EVO|BTM)\b', recipe_corpus, re.IGNORECASE):
        furnace_id = "NB3"
        furnace_variant = "NB3 (BTM)" if re.search(r'\bBTM\b', recipe_corpus, re.IGNORECASE) else "NB3 (KE8/M2/EVO)"
    elif re.search(r'\b(Tahc|Utahc)\b', recipe_corpus, re.IGNORECASE): furnace_id, furnace_variant = "NB2", "NB2 (Tahc/Utahc)"
    elif re.search(r'\b(CDS|KN9|12SHP)\b', recipe_corpus, re.IGNORECASE): furnace_id, furnace_variant = "NB1", "NB1 (CDS/KN9/12SHP)"
    elif (re.search(r'\bWK\d{1,2}\b', recipe_corpus, re.IGNORECASE) or re.search(r'\b\d{6}\b', recipe_corpus)): furnace_id, furnace_variant = "NB1", "NB1 (Standard)"
    else:
        f_match = re.search(r'NB\s*Furnace\s*0?([123])\b|NB\s*#?\s*0?([123])\b|NB-0?([123])\b', recipe_corpus, re.IGNORECASE)
        if f_match: furnace_id = furnace_variant = f"NB{f_match.group(1)}"

    base_cfg = FURNACE_CONFIGS.get(furnace_id, FURNACE_CONFIGS["NB3"])
    cfg = dict(base_cfg)

    if "RAD" in furnace_variant: cfg.update({"dryer_dwell_thresh_1": 150.0, "dryer_dwell_thresh_2": 175.0, "debinder_dwell_thresh": 200.0, "brazing_dwell_thresh_1": 550.0, "brazing_dwell_thresh_2": 577.0, "brazing_dwell_thresh_3": 583.0, "brazing_dwell_thresh_4": 600.0})
    elif "NB1" in furnace_variant: cfg.update({"dryer_dwell_thresh_1": 150.0, "dryer_dwell_thresh_2": 200.0, "debinder_dwell_thresh": 300.0, "brazing_dwell_thresh_1": 550.0, "brazing_dwell_thresh_2": 577.0, "brazing_dwell_thresh_3": 591.0, "brazing_dwell_thresh_4": 600.0})
    elif "NB2" in furnace_variant: cfg.update({"dryer_dwell_thresh_1": 200.0, "dryer_dwell_thresh_2": 250.0, "debinder_dwell_thresh": None, "brazing_dwell_thresh_1": 550.0, "brazing_dwell_thresh_2": 577.0, "brazing_dwell_thresh_3": 591.0, "brazing_dwell_thresh_4": 600.0})
    elif "BTM" in furnace_variant: cfg.update({"dryer_dwell_thresh_1": 250.0, "dryer_dwell_thresh_2": 300.0, "debinder_dwell_thresh": None, "brazing_dwell_thresh_1": 550.0, "brazing_dwell_thresh_2": 577.0, "brazing_dwell_thresh_3": 591.0, "brazing_dwell_thresh_4": 600.0})
    elif "NB3" in furnace_variant: cfg.update({"dryer_dwell_thresh_1": 150.0, "dryer_dwell_thresh_2": 200.0, "debinder_dwell_thresh": None, "brazing_dwell_thresh_1": 550.0, "brazing_dwell_thresh_2": 577.0, "brazing_dwell_thresh_3": 591.0, "brazing_dwell_thresh_4": 600.0})

    line_speed_mpm = cfg["line_speed_mpm"]
    cv_sp_matches = re.findall(r'CV\s*SP\s*[:=]?\s*(\d{3,4})\s*(?:mm/\s*min|mm)?', recipe_corpus, re.IGNORECASE)
    if cv_sp_matches:
        last_speed = float(cv_sp_matches[-1])
        if 800.0 <= last_speed <= 2500.0: line_speed_mpm = last_speed / 1000.0

    df_master["Distance_Meters"] = ((df_master["Time_Seconds"] - detected_start_sec) / 60.0) * line_speed_mpm
    probe_start_info = {}
    for col in probe_cols:
        p_sec = probe_start_secs[col]
        offset_m = ((p_sec - detected_start_sec) / 60.0) * line_speed_mpm
        df_master[f"Distance_{col}"] = ((df_master["Time_Seconds"] - p_sec) / 60.0) * line_speed_mpm
        probe_start_info[col] = {
            "Start_Sec": p_sec,
            "Start_HHMMSS": df_master[df_master["Time_Seconds"] == p_sec].iloc[0]["Time_HHMMSS"] if p_sec < len(df_master) else "00:00:00",
            "Offset_Sec": p_sec - detected_start_sec, "Offset_Meters": round(offset_m, 2), "Is_First": (col == first_probe_name)
        }

    return {
        "filename": filename, "df_master": df_master, "probe_cols": probe_cols, "furnace_id": furnace_id, "furnace_variant": furnace_variant, "cfg": cfg,
        "line_speed_mpm": line_speed_mpm, "detected_start_sec": detected_start_sec, "detected_start_hhmmss": detected_start_hhmmss, "first_probe_name": first_probe_name,
        "operator_name": operator_name, "company": company, "site": site, "operator_comment": clean_comments_text, "process_settings": process_settings,
        "probe_locations": probe_locations, "probe_start_info": probe_start_info, "embedded_img": embedded_img
    }

# ==============================================================================
# STREAMLIT UI LAYOUT & MAIN APPLICATION
# ==============================================================================
st.title("🔥 Datapaq .PAQ Furnace Profiler & Analyzer")
st.markdown("Automated thermal profile extraction, zone metrics, and multi-file comparison.")

with st.sidebar:
    st.header("📁 File Upload")
    if st.button("🔄 Reset / Clear Data"):
        st.cache_data.clear()
        st.rerun()
    uploaded_file1 = st.file_uploader("Upload Main .PAQ File", type=["paq"], key="paq1")
    st.markdown("---")
    st.header("⚖️ Comparison Option")
    uploaded_file2 = st.file_uploader("Upload 2nd .PAQ File (Optional)", type=["paq"], key="paq2")

if not uploaded_file1:
    st.info("👈 Please upload a `.paq` binary file using the sidebar to begin analysis.")
else:
    data1 = process_paq_file(uploaded_file1.getvalue(), uploaded_file1.name)
    if not data1:
        st.error("❌ Failed to parse valid probe temperature streams from the uploaded file.")
        st.stop()

    df_m1, f_variant, cfg, zones, probe_cols = data1["df_master"], data1["furnace_variant"], data1["cfg"], data1["cfg"]["zones"], data1["probe_cols"]
    total_furnace_length = zones[-1]["start"] + zones[-1]["length"]
    furnace_duration_mins = total_furnace_length / data1['line_speed_mpm']
    furnace_duration_secs = int(furnace_duration_mins * 60)

    st.success(f"✓ File Loaded Successfully: **{data1['filename']}**")
    m_col1, m_col2, m_col3 = st.columns(3)
    m_col1.metric("Confirmed Furnace", f_variant)
    m_col2.metric("Conveyor Speed", f"{data1['line_speed_mpm']:.3f} m/min")
    m_col3.metric("Time in Furnace", f"{furnace_duration_secs}s (~{furnace_duration_mins:.1f} min)")

    tabs = st.tabs(["📊 Profile Graphs", "🏭 Zone & Stage Summary", "📈 Statistics & Boxplots", "💾 Master Dataset & Export", "⚖️ Compare Files"])

    with tabs[0]:
        st.subheader("Global Furnace Profile")
        fig1 = go.Figure()
        end_time_stamp = pd.Timestamp("1970-01-01 00:00:00") + pd.to_timedelta(furnace_duration_secs + 120, unit="s")
        custom_hover1 = np.stack((df_m1["Time_HHMMSS"], df_m1["Time_Seconds"], df_m1["Distance_Meters"]), axis=-1)
        for col in probe_cols:
            fig1.add_trace(go.Scatter(x=df_m1["Time_Stamp"], y=df_m1[col], mode="lines", name=col, customdata=custom_hover1, hovertemplate="%{fullData.name}: %{y:.1f} °C<br>Time: %{customdata[0]}<br>Dist: %{customdata[2]:.2f} m", line=dict(color=PROBE_COLORS.get(col)), xaxis="x"))
        for z in zones:
            z_color = GROUP_COLORS.get(z["group"], "rgba(200, 200, 200, 0.2)")
            z_start_sec = (z["start"] / data1['line_speed_mpm']) * 60
            z_end_sec = ((z["start"] + z["length"]) / data1['line_speed_mpm']) * 60
            z_start_time = pd.Timestamp("1970-01-01 00:00:00") + pd.to_timedelta(z_start_sec, unit="s")
            z_end_time = pd.Timestamp("1970-01-01 00:00:00") + pd.to_timedelta(z_end_sec, unit="s")
            fig1.add_vrect(x0=z_start_time, x1=z_end_time, fillcolor=z_color, layer="below", line_width=0.5, line_dash="dot", line_color="rgba(120, 120, 120, 0.4)", annotation_text=f"{z['num']}.{z['name']}", annotation_position="top left", annotation=dict(font_size=9, font_color="#a0aab2", textangle=-90))
        fig1.add_hline(y=cfg["trigger_temp_brazing"], line_dash="dash", line_color="red", annotation_text=f"Brazing ({cfg['trigger_temp_brazing']}°C)", annotation_position="bottom right")

        fig1.update_layout(
            title=f"GLOBAL FURNACE PROFILE ({f_variant}): {data1['filename']}", yaxis=dict(title="Temperature (°C)", domain=[0.15, 1.0]), hovermode="x unified", template="plotly_white", height=600, margin=dict(b=80),
            xaxis=dict(title="Time (hh:mm:ss)", tickformat="%H:%M:%S", range=[pd.Timestamp("1970-01-01 00:00:00"), end_time_stamp], anchor="y"),
            xaxis2=dict(title="Distance (Meters)", overlaying="x", side="bottom", position=0.0, anchor="free", range=[0, total_furnace_length + (120 * data1['line_speed_mpm'] / 60)])
        )
        fig1.add_trace(go.Scatter(x=df_m1["Distance_Meters"], y=df_m1[probe_cols[0]] * 0, showlegend=False, opacity=0, xaxis="x2", hoverinfo='skip'))
        st.plotly_chart(fig1, use_container_width=True)
        st.markdown("---")
        
        stages = cfg["stages"]
        has_debinder = any(s["Stage"] == "Debinder" for s in stages)
        dryer_info = next((s for s in stages if s["Stage"] == "Dryer"), stages[0])
        debinder_info = next((s for s in stages if s["Stage"] == "Debinder"), None) if has_debinder else None
        brazing_info = next((s for s in stages if s["Stage"] == "Brazing"), stages[-1])

        if f_variant == "NB1 (RAD)":
            process_time = df_m1["Time_Seconds"] - data1["detected_start_sec"]
            dryer_df = df_m1[(process_time >= 0) & (process_time <= 300)]
            debinder_df = df_m1[(process_time > 300) & (process_time <= 930)]
        else:
            dryer_df = df_m1[(df_m1["Distance_Meters"] >= dryer_info["Start (m)"]) & (df_m1["Distance_Meters"] <= dryer_info["End (m)"])]
            debinder_df = df_m1[(df_m1["Distance_Meters"] >= debinder_info["Start (m)"]) & (df_m1["Distance_Meters"] <= debinder_info["End (m)"])] if debinder_info else None
        
        brazing_df = df_m1[(df_m1["Distance_Meters"] >= brazing_info["Start (m)"]) & (df_m1["Distance_Meters"] <= brazing_info["End (m)"])]

        matrix_rows = []
        for col in probe_cols:
            r = {"Probe": col, "Dryer Max (°C)": round(dryer_df[col].max(), 1) if not dryer_df.empty else np.nan}
            for dt in [cfg.get("dryer_dwell_thresh_1"), cfg.get("dryer_dwell_thresh_2")]:
                if dt is not None: r[f"Dryer Dwell (≥{int(dt)}°C)"] = format_dwell_time((dryer_df[col] >= dt).sum()) if not dryer_df.empty else "00:00:00"
            if has_debinder and debinder_df is not None:
                d_thresh = cfg.get("debinder_dwell_thresh", 300.0) or 300.0
                r["Debinder Max (°C)"] = round(debinder_df[col].max(), 1) if not debinder_df.empty else np.nan
                r[f"Debinder Dwell (≥{int(d_thresh)}°C)"] = format_dwell_time((debinder_df[col] >= d_thresh).sum()) if not debinder_df.empty else "00:00:00"
            r["Brazing Max (°C)"] = round(brazing_df[col].max(), 1) if not brazing_df.empty else np.nan
            for bt in [cfg.get(f"brazing_dwell_thresh_{i}") for i in range(1, 5)]:
                if bt is not None: r[f"Brazing Dwell (≥{int(bt)}°C)"] = format_dwell_time((brazing_df[col] >= bt).sum()) if not brazing_df.empty else "00:00:00"
            matrix_rows.append(r)
            
        if f_variant == "NB1 (RAD)":
            desired_order = ["PB#1", "PB#2", "PB#3", "PB#8", "PB#4", "PB#5", "PB#6", "PB#7"]
            matrix_rows = sorted(matrix_rows, key=lambda x: desired_order.index(x["Probe"]) if x["Probe"] in desired_order else 99)

        # --- เพิ่ม Checkbox สั่งเปิด-ปิด การตรวจสอบผลของ Dryer Max ---
        st.subheader(f"⏱️ Inspection Matrix — {f_variant}")
        check_dryer_max = st.checkbox("🔍 ตรวจสอบเกณฑ์ Dryer Max Temp (°C) / Evaluate Dryer Max", value=False)
        
        std_info = STANDARD_SPECS.get(f_variant)
        if std_info:
            st.markdown(f"""
            <div style="background-color: rgba(38, 39, 48, 0.8); padding: 10px; border-left: 5px solid #00ffff; border-radius: 5px; margin-bottom: 15px;">
                <strong style="color: #00ffff; font-size: 1.1rem;">📝 Standard: {std_info['id']}</strong><br>
                <span style="color: #a0aab2; font-size: 0.9rem;"><b>Max Temp:</b> {std_info['max']}<br><b>Dwell Time:</b> {std_info['dwell']}</span>
            </div>
            """, unsafe_allow_html=True)
            
        st.markdown("""
        <div style="font-size: 0.95rem; margin-bottom: 10px; padding: 10px; border-radius: 5px; background-color: rgba(255,255,255,0.05);">
            <b>Color Legend / คำอธิบายสี:</b>&nbsp;&nbsp;
            <span style="color: #00e676; font-weight: bold;">■ Green (สีเขียว)</span>: Pass standard (ผ่านเกณฑ์) &nbsp;&nbsp;|&nbsp;&nbsp;
            <span style="color: #ff4444; font-weight: bold;">■ Red (สีแดง)</span>: Fail standard (ไม่ผ่านเกณฑ์) &nbsp;&nbsp;|&nbsp;&nbsp;
            <span style="color: #a0aab2; font-weight: bold;">■ Default (สีปกติ)</span>: Reference only (ใช้เพื่ออ้างอิง)
        </div>
        """, unsafe_allow_html=True)

        df_matrix = pd.DataFrame(matrix_rows)
        format_dict = {col: "{:.1f}" for col in df_matrix.columns if "Max (°C)" in col}
        st.dataframe(df_matrix.style.apply(style_inspection_matrix, variant=f_variant, check_dryer_max=check_dryer_max, axis=1).format(format_dict, na_rep="N/A"), use_container_width=True, hide_index=True)
        
        # --- สร้างกล่องสรุปสถานะการประมวลผล (Overall Status) ---
        overall_pass = True
        failed_points = []
        val_rules = VALIDATION_RULES.get(f_variant, {})
        
        for r in matrix_rows:
            probe = r["Probe"]
            for k, v in r.items():
                if k == "Probe": continue
                if not check_dryer_max and "Dryer Max" in k: continue # ข้ามถ้าไม่ให้เช็ค
                
                rule = val_rules.get(k)
                if not rule: continue
                is_fail = False
                if pd.isna(v) or v == "00:00:00" or v == "" or v == 0:
                    if rule[0] > 0: is_fail = True
                else:
                    min_v, max_v = rule
                    if "Max (°C)" in k:
                        try:
                            if not (min_v <= float(v) <= max_v): is_fail = True
                        except: pass
                    elif "Dwell" in k:
                        try:
                            parts = str(v).split(':')
                            if len(parts) == 3:
                                total_s = int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
                                if not (min_v <= total_s <= max_v): is_fail = True
                        except: pass
                if is_fail:
                    overall_pass = False
                    failed_points.append(f"{probe} ({k})")

        if std_info:
            if overall_pass:
                st.success("✅ **OVERALL STATUS: PASS | สถานะภาพรวม: ผ่านเกณฑ์มาตรฐาน**\n\nThe thermal profile meets all specified requirements for this product. (โปรไฟล์อุณหภูมิผ่านข้อกำหนดทั้งหมดสำหรับผลิตภัณฑ์นี้)")
            else:
                fail_str = ", ".join(list(dict.fromkeys(failed_points)))
                st.error(f"❌ **OVERALL STATUS: FAIL | สถานะภาพรวม: ไม่ผ่านเกณฑ์มาตรฐาน**\n\nThe thermal profile does NOT meet the requirements. Please check the red values in the matrix. (โปรไฟล์อุณหภูมิไม่ผ่านข้อกำหนด กรุณาตรวจสอบค่าสีแดงในตาราง)\n\n**Failed Items (จุดที่ไม่ผ่าน):** {fail_str}")
        # -------------------------------------------------------------------

        st.markdown("---")
        
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("👤 Operator Info")
            m1, m2, m3 = st.columns(3)
            m1.text_input("Name", data1["operator_name"], disabled=True)
            m2.text_input("Company", data1["company"], disabled=True)
            m3.text_input("Site", data1["site"], disabled=True)
            st.text_area("💬 Comments", data1["operator_comment"], height=120)
            st.text_area("⚙️ Recipe", data1["process_settings"], height=200)

        with col_b:
            st.subheader("📍 Probe Locations")
            if data1["probe_locations"]:
                if f_variant == "NB1 (RAD)":
                    desired_order = ["PB#1", "PB#2", "PB#3", "PB#8", "PB#4", "PB#5", "PB#6", "PB#7"]
                    sorted_probes = sorted(data1["probe_locations"].items(), key=lambda x: desired_order.index(x[0]) if x[0] in desired_order else 99)
                else:
                    sorted_probes = sorted(data1["probe_locations"].items(), key=lambda x: int(x[0].replace("PB#", "")) if x[0].replace("PB#", "").isdigit() else 99)
                st.dataframe(pd.DataFrame([{"Channel": k, "Attached Location": v} for k, v in sorted_probes]), use_container_width=True, hide_index=True)
            else:
                st.info("No explicit probe location mapping found in PAQ header.")
            if data1["embedded_img"]:
                st.subheader("🖼️ PAQ Image")
                st.image(data1["embedded_img"], use_container_width=True)

        st.markdown("---")
        show_indiv_chart = st.toggle("👁️ Show / Hide Individually Aligned Chart", value=False)
        if show_indiv_chart:
            st.subheader("Individually Aligned Probe Chart (Own 60°C Entry)")
            fig2 = go.Figure()
            for col in probe_cols:
                offset_m = data1["probe_start_info"][col]["Offset_Meters"]
                indiv_hover = np.stack((df_m1["Time_HHMMSS"], df_m1["Time_Seconds"], np.full(len(df_m1), offset_m)), axis=-1)
                fig2.add_trace(go.Scatter(x=df_m1[f"Distance_{col}"], y=df_m1[col], mode="lines", name=f"{col} (+{offset_m:.2f}m)" if offset_m > 0 else f"{col} (Lead)", customdata=indiv_hover, hovertemplate="%{fullData.name}: %{y:.1f} °C<br>Indiv Dist: %{x:.2f} m<br>Time: %{customdata[0]}", line=dict(color=PROBE_COLORS.get(col))))
            for z in zones:
                z_color = GROUP_COLORS.get(z["group"], "rgba(200, 200, 200, 0.2)")
                fig2.add_vrect(x0=z["start"], x1=z["start"] + z["length"], fillcolor=z_color, layer="below", line_width=0.5, line_dash="dot", line_color="rgba(120, 120, 120, 0.4)", annotation_text=f"{z['num']}.{z['name']}", annotation_position="top left", annotation=dict(font_size=9, font_color="#a0aab2", textangle=-90))
            fig2.update_layout(title=f"INDIVIDUALLY ALIGNED PROFILES ({f_variant}): {data1['filename']}", xaxis=dict(title="Individual Probe Distance (Meters from Probe's 60°C Entry)", range=[-1, total_furnace_length + 2]), yaxis_title="Temperature (°C)", hovermode="x unified", template="plotly_white", height=550)
            st.plotly_chart(fig2, use_container_width=True)

    with tabs[1]:
        st.subheader("🔥 Zone Peak Temperatures")
        zone_max_records = []
        for z in zones:
            z_df = df_m1[(df_m1["Distance_Meters"] >= z["start"]) & (df_m1["Distance_Meters"] < round(z["start"] + z["length"], 2))]
            r = {"Group": z["group"], "Zone #": z["num"], "Zone Name": z["name"], "Start (m)": z["start"], "End (m)": round(z["start"] + z["length"], 2)}
            if not z_df.empty and probe_cols:
                max_s = z_df[probe_cols].max()
                for col in probe_cols: r[col] = max_s[col]
                r["Zone Peak (°C)"] = max_s.max()
                r["Hot Probe"] = max_s.idxmax()
            else:
                for col in probe_cols: r[col] = np.nan
                r["Zone Peak (°C)"], r["Hot Probe"] = np.nan, "-"
            zone_max_records.append(r)
        df_zone_summary = pd.DataFrame(zone_max_records)
        try: st.dataframe(df_zone_summary.style.background_gradient(cmap="OrRd", subset=probe_cols + ["Zone Peak (°C)"]).format({col: "{:.2f}" for col in probe_cols + ["Zone Peak (°C)"]}), use_container_width=True)
        except: st.dataframe(df_zone_summary, use_container_width=True)

        st.markdown("---")
        st.subheader("⏱️ Entry Alignment (60°C)")
        shift_rows = [{"Probe": col, "Start Time (HH:MM:SS)": info["Start_HHMMSS"], "Start Sec": f"{info['Start_Sec']}s", "Lag Time vs First": f"+{info['Offset_Sec']}s" if info['Offset_Sec'] > 0 else "0s (Lead)", "Distance Shift": f"+{info['Offset_Meters']:.2f} m" if info['Offset_Meters'] > 0 else "0.00 m (Lead)", "Status": "🏆 First (Lead)" if info["Is_First"] else f"+{info['Offset_Meters']:.2f} m lag"} for col, info in data1["probe_start_info"].items()]
        st.dataframe(pd.DataFrame(shift_rows), use_container_width=True, hide_index=True)

    with tabs[2]:
        st.subheader("📈 Temperature Distribution Boxplot by Probe")
        fig_box = go.Figure()
        for idx, col in enumerate(probe_cols): fig_box.add_trace(go.Box(y=df_m1[col].dropna(), name=col, boxpoints='outliers', marker_color=PROBE_COLORS.get(col)))
        fig_box.update_layout(title="Temperature Distribution Across Probes", yaxis_title="Temperature (°C)", template="plotly_white", height=500)
        st.plotly_chart(fig_box, use_container_width=True)

        st.markdown("---")
        st.subheader("📊 Zone Temperature Statistics (All Probes Combined)")
        stats_list = []
        for z in zones:
            df_z = df_m1[(df_m1["Distance_Meters"] >= z["start"]) & (df_m1["Distance_Meters"] <= z["start"] + z["length"])]
            if not df_z.empty:
                z_vals = df_z[probe_cols].values.flatten()
                z_vals = z_vals[~np.isnan(z_vals)]
                if len(z_vals) > 0: stats_list.append({"Zone #": z["num"], "Zone Name": z["name"], "Group": z["group"], "Avg Temp (°C)": round(np.mean(z_vals), 2), "Std Dev (°C)": round(np.std(z_vals, ddof=1), 2), "Min Temp (°C)": round(np.min(z_vals), 2), "Max Temp (°C)": round(np.max(z_vals), 2), "Data Points": len(z_vals)})
        st.dataframe(pd.DataFrame(stats_list), use_container_width=True, hide_index=True)

    with tabs[3]:
        st.subheader("💾 Unified 1-Row Dataset (Database Ready)")
        row_data = {"File_Name": data1["filename"], "Furnace_Type": f_variant, "Operator_Name": data1["operator_name"], "Company": data1["company"], "Site": data1["site"], "Entrance_Time": data1["detected_start_hhmmss"], "Line_Speed_MPM": data1["line_speed_mpm"]}
        for pb in [f"PB{i}" for i in range(1, 9)]:
            ch = f"PB#{pb.replace('PB','')}"
            row_data[f"{pb}_Location"] = data1["probe_locations"].get(ch, "Unlabeled")
            row_data[f"{pb}_Start_Time"] = data1["probe_start_info"].get(ch, {}).get("Start_HHMMSS", "00:00:00")
            row_data[f"{pb}_Lag_Sec"] = data1["probe_start_info"].get(ch, {}).get("Offset_Sec", 0)
        df_single_row = pd.DataFrame([row_data])
        st.dataframe(df_single_row, use_container_width=True)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_single_row.to_excel(writer, sheet_name="Master_Record", index=False)
            df_zone_summary.to_excel(writer, sheet_name="Zone_Peaks", index=False)
            pd.DataFrame(matrix_rows).to_excel(writer, sheet_name="Inspection_Matrix", index=False)
        st.download_button(label="📥 Download Complete Excel Report", data=buffer.getvalue(), file_name=f"{os.path.splitext(data1['filename'])[0]}_Analysis.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with tabs[4]:
        st.subheader("⚖️ Compare Profiles Across Two Files")
        if not uploaded_file2: st.info("👈 Upload a second `.paq` file in the sidebar to view comparison graph.")
        else:
            data2 = process_paq_file(uploaded_file2.getvalue(), uploaded_file2.name)
            if not data2: st.error("❌ Failed to parse second `.paq` file.")
            else:
                df_m2 = data2["df_master"]
                fig_comp = go.Figure()
                for col in probe_cols:
                    if col in df_m1.columns: fig_comp.add_trace(go.Scatter(x=df_m1["Distance_Meters"], y=df_m1[col], mode="lines", name=f"F1: {col}", line=dict(color=PROBE_COLORS.get(col), width=1.5)))
                for col in data2["probe_cols"]:
                    if col in df_m2.columns: fig_comp.add_trace(go.Scatter(x=df_m2["Distance_Meters"], y=df_m2[col], mode="lines", name=f"F2: {col}", line=dict(dash='dash', color=PROBE_COLORS.get(col), width=1.5)))
                fig_comp.update_layout(title=f"COMPARISON: {data1['filename']} vs {data2['filename']}", xaxis=dict(title="Distance (Meters)", range=[-1, total_furnace_length + 2]), yaxis_title="Temperature (°C)", hovermode="x unified", template="plotly_white", height=600)
                st.plotly_chart(fig_comp, use_container_width=True)
