import os
import zlib
import struct
import io
import re
import numpy as np
import pandas as pd
from PIL import Image
import streamlit as st

# ตั้งค่าหน้าเว็บ Streamlit
st.set_page_config(page_title="Datapaq .PAQ File Processor", layout="wide")

# ตรวจสอบและติดตั้ง olefile อัตโนมัติ (หากรันในระบบที่ไม่มี)
try:
    import olefile
except ImportError:
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "olefile"])
    import olefile

# ตั้งค่าการแสดงผลทศนิยมของ Pandas
pd.options.display.float_format = '{:.1f}'.format

# --- หัวข้อแอปพลิเคชัน ---
st.title("🔥 Datapaq .PAQ File Processor")
st.markdown("แปลงไฟล์ดึงข้อมูลอุณหภูมิเตาอบอัตโนมัติ รองรับไฟล์ประเภท binary `.paq`")
st.divider()

# --- แถบตั้งค่าด้านข้าง (Sidebar) ---
st.sidebar.header("⚙️ Configuration")
LINE_SPEED_MPM = st.sidebar.number_input(
    "Line Speed (Meters per Minute)", 
    min_value=0.1, 
    max_value=10.0, 
    value=1.2700, 
    step=0.01,
    format="%.4f"
)

# --- ส่วนอัปโหลดไฟล์ (จาก Cell 1) ---
st.subheader("📁 Step 1: Upload Datapaq File")
uploaded_file = st.file_uploader("ลากและวางไฟล์ .paq ที่นี่", type=["paq"])

# ฟังก์ชันถอดรหัส Stream (จาก Cell 2)
def decompress_stream(ole_obj, stream_name):
    try:
        raw_data = ole_obj.openstream(stream_name).read()
        zlib_data = raw_data[8:] if raw_data.startswith(b'ZLIB') else raw_data
        try:
            return zlib.decompress(zlib_data)
        except Exception:
            return zlib.decompress(zlib_data, -zlib.MAX_WBITS)
    except Exception:
        return None

# ฟังก์ชันดึงชุดข้อมูล Probe (จาก Cell 2)
def extract_probe_series_autonomously(decomp_bytes):
    best_series = []
    for offset in range(0, min(12000, len(decomp_bytes) - 800), 1):
        rem = len(decomp_bytes) - offset
        cnt = rem // 8
        if cnt < 500: continue
        try:
            vals = struct.unpack(f"<{cnt}d", decomp_bytes[offset : offset + cnt * 8])
        except Exception:
            continue

        clean_vals, glitch_count = [], 0
        for v in vals:
            if isinstance(v, float) and -10.0 <= v <= 650.0:
                clean_vals.append(v)
                glitch_count = 0
            else:
                glitch_count += 1
                if len(clean_vals) > 500:
                    if glitch_count <= 5:
                        clean_vals.append(clean_vals[-1] if clean_vals else 0.0)
                    else: break
                elif glitch_count > 3: clean_vals = []

        if len(clean_vals) > len(best_series) and max(clean_vals) > 150.0:
            best_series = clean_vals

    return best_series


# --- ส่วนประมวลผลข้อมูลหลักเมื่ออัปโหลดไฟล์ (จาก Cell 2) ---
if uploaded_file is not None:
    st.success(f"✓ Success! Datapaq file '{uploaded_file.name}' loaded into memory.")
    st.divider()
    
    st.subheader("⚙️ Step 2: Main Processing & Extraction")
    
    with st.spinner("กำลังประมวลผลและวิเคราะห์รหัสไฟล์..."):
        try:
            # แปลงอ็อบเจกต์ที่อัปโหลดมาให้เป็น Byte Stream เพื่อให้ olefile อ่านได้
            file_bytes = uploaded_file.read()
            ole_io = io.BytesIO(file_bytes)
            
            ole = olefile.OleFileIO(ole_io)
            probe_streams = [s for s in ole.listdir() if len(s) >= 4 and s[0] == 'Paqfiles' and s[2] == 'ProbeResults']
            probe_streams = sorted(probe_streams, key=lambda x: x[-1])

            all_probes = {}
            
            # สร้างคอลัมน์แสดงสถานะการถอดรหัสแบบ Real-time บนหน้าเว็บ
            status_container = st.empty()
            extracted_logs = []

            for stream_path in probe_streams:
                stream_name = "/".join(stream_path)
                probe_folder = stream_path[-1]
                probe_num = int(''.join(filter(str.isdigit, probe_folder))) + 1 if any(c.isdigit() for c in probe_folder) else len(all_probes) + 1
                col_name = f"PB#{probe_num}"

                d = decompress_stream(ole, stream_name)
                if d:
                    series = extract_probe_series_autonomously(d)
                    if series:
                        all_probes[col_name] = series
                        extracted_logs.append(f"✓ {col_name}: Extracted {len(series)} raw samples")
            
            # พิมพ์บอกสถานะล็อกการดึงข้อมูลบนหน้าเว็บ
            with st.expander("ดูบันทึกการดึงข้อมูลตำแหน่งหัววัด (Extraction Logs)"):
                for log in extracted_logs:
                    st.text(log)

            if all_probes:
                max_samples = max(len(v) for v in all_probes.values())
                aligned_probes = {k: (v + [np.nan] * (max_samples - len(v)) if len(v) < max_samples else v) for k, v in all_probes.items()}

                df_master = pd.DataFrame(aligned_probes)
                df_master.insert(0, "Time_Seconds", range(len(df_master)))
                df_master.insert(1, "Time_HHMMSS", pd.to_datetime(df_master["Time_Seconds"], unit='s').dt.strftime('%H:%M:%S'))

                probe_cols = [col for col in df_master.columns if col.startswith("PB#")]

                # --- ตรวจจับทางเข้าเตาอบคงที่ที่อุณหภูมิ 60°C เป็นเวลา 15 วินาที ---
                SUSTAINED_SECONDS = 15
                probe_start_secs = {}

                for col in probe_cols:
                    is_p60 = (df_master[col] >= 60.0)
                    valid_p_mask = is_p60.copy()
                    for i in range(1, SUSTAINED_SECONDS):
                        valid_p_mask = valid_p_mask & is_p60.shift(-i, fill_value=False)

                    if valid_p_mask.any():
                        p_sec = int(df_master[valid_p_mask].iloc[0]["Time_Seconds"])
                    else:
                        p_sec = 0
                    probe_start_secs[col] = p_sec

                valid_starts = [sec for sec in probe_start_secs.values() if sec > 0]
                detected_start_sec = min(valid_starts) if valid_starts else 0

                first_probe_name = [k for k, v in probe_start_secs.items() if v == detected_start_sec][0] if valid_starts else probe_cols[0]

                start_row = df_master[df_master["Time_Seconds"] == detected_start_sec].iloc[0]
                detected_start_hhmmss = start_row["Time_HHMMSS"]

                # คำนวณระยะทาง
                df_master["Distance_Meters"] = ((df_master["Time_Seconds"] - detected_start_sec) / 60.0) * LINE_SPEED_MPM

                probe_start_info = {}
                for col in probe_cols:
                    p_sec = probe_start_secs[col]
                    offset_sec = p_sec - detected_start_sec
                    offset_m = (offset_sec / 60.0) * LINE_SPEED_MPM

                    df_master[f"Distance_{col}"] = ((df_master["Time_Seconds"] - p_sec) / 60.0) * LINE_SPEED_MPM

                    p_hhmmss = df_master[df_master["Time_Seconds"] == p_sec].iloc[0]["Time_HHMMSS"] if p_sec < len(df_master) else "00:00:00"

                    probe_start_info[col] = {
                        "Start_Sec": p_sec,
                        "Start_HHMMSS": p_hhmmss,
                        "Offset_Sec": offset_sec,
                        "Offset_Meters": round(offset_m, 2),
                        "Is_First": (col == first_probe_name)
                    }

                # --- การแปรผลข้อมูลในหน้าแดชบอร์ด (Streamlit UI elements) ---
                st.success("🎉 ประมวลผลข้อมูลหลักสำเร็จแล้ว!")
                
                # แสดงการ์ดข้อมูลสรุป (Metrics)
                col1, col2, col3 = st.columns(3)
                col1.metric("จุดเริ่มต้นเข้าเตาอบที่พบ (Time)", f"{detected_start_hhmmss}")
                col2.metric("เวลาเริ่มต้น (วินาที)", f"{detected_start_sec} s")
                col3.metric("หัววัดหลักที่เข้าเตาคนแรก", f"{first_probe_name}")

                # แสดงตารางประวัติเวลาออฟเซ็ตของแต่ละหัววัด
                st.subheader("📊 ข้อมูลตำแหน่งการเริ่มวัดของแต่ละหัววัด (Probe Start Info)")
                df_info = pd.DataFrame(probe_start_info).T
                st.dataframe(df_info, use_container_width=True)

                # แสดงตัวอย่างตารางผลลัพธ์หลัก (Master DataFrame)
                st.subheader("📋 ตารางข้อมูล Master Data (ตัวอย่าง 100 แถวแรก)")
                st.dataframe(df_master.head(100), use_container_width=True)
                
                # ปุ่มดาวน์โหลดข้อมูลเป็นไฟล์ Excel/CSV
                csv_data = df_master.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 ดาวน์โหลดไฟล์ Master Data เป็น CSV",
                    data=csv_data,
                    file_name=f"Processed_{uploaded_file.name}.csv",
                    mime="text/csv"
                )

            else:
                st.error("❌ ไม่พบข้อมูลหัววัด (Probe Streams) ที่สามารถใช้งานได้ในไฟล์นี้")

        except Exception as e:
            st.error(f"❌ เกิดข้อผิดพลาดในการอ่านโครงสร้างไฟล์: {str(e)}")

else:
    st.info("💡 รอการอัปโหลดไฟล์ไฟล์ .paq เพื่อเริ่มต้นการทำงาน...")
