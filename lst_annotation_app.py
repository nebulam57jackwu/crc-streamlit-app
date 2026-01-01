import streamlit as st
import pandas as pd
import sqlite3
import json
import uuid
from datetime import datetime
from streamlit_drawable_canvas import st_canvas

# ==========================================
# 1. 配置與常數定義 (Schema & Enums)
# ==========================================
st.set_page_config(layout="wide", page_title="NTUH ESD/LST AI Annotation System V2")

# 資料庫檔案
DB_FILE = "esd_annotation.db"

# 完整的 Phase 定義 (Project 1 Source)
PHASES = [
    ("1. Preparation", "Preparation"),
    ("2. Diagnosis_WL", "Diagnosis using WL"),
    ("3. Diagnosis_NBI", "Diagnosis using NBI"),
    ("4. Diagnosis_Indigo", "Diagnosis using Indigo Carmine"),
    ("5. Diagnosis_Crystal", "Diagnosis using Crystal Violet"),
    ("6. Marking", "Marking"),
    ("7. Local_injection", "Local injection"),
    ("8. Circum_incision", "Circumferential incision"),
    ("9. Submucosal_dissection", "Submucosal dissection"),
    ("10. Tumor_traction", "Tumor traction"),
    ("11. Hybrid_ESD", "Hybrid ESD"),
    ("12. Wound_closure", "Wound closure"),
    ("13. Hemostasis_Coagrasper", "Hemostasis (Coagrasper)"),
    ("14. Hemostasis_Knife", "Hemostasis (Knife)"),
    ("15. Hemostasis_Clip", "Hemostasis (Hemoclipping)"),
    ("16. Tumor_removal", "Tumor removal"),
    ("17. Polypectomy", "Polypectomy (CSP/HSP)"),
    ("0. No_Step", "No Step / Transition")
]

# Project 2 影像分類定義
JNET_OPTIONS = ["NA (WL Mode)", "Type 1", "Type 2A", "Type 2B", "Type 3"]
KUDO_OPTIONS = ["NA (Non-Mag)", "Type I", "Type II", "Type IIIs", "Type IIIl", "Type IV", "Type Vi", "Type Vn"]
PARIS_OPTIONS = ["0-Is", "0-IIa", "0-IIb", "0-IIc"]
LST_SUBTYPES = ["LST-G (H)", "LST-G (M)", "LST-NG (F)", "LST-NG (PD)"]
DEPTH_OPTIONS = ["Mucosa (M)", "SM-superficial (<1000μm)", "SM-deep (≥1000μm)", "Unknown"]

# ==========================================
# 2. 資料庫管理 (SQLite Backend)
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 表 1: 影片段落 (Video Segments)
    c.execute('''CREATE TABLE IF NOT EXISTS video_segments (
        segment_id TEXT PRIMARY KEY,
        case_id TEXT,
        video_id TEXT,
        phase_code TEXT,
        start_time REAL,
        end_time REAL,
        annotator_id TEXT,
        created_at TEXT
    )''')
    
    # 表 2: 影像標註 (Image Annotations + ROI)
    c.execute('''CREATE TABLE IF NOT EXISTS image_annotations (
        annotation_id TEXT PRIMARY KEY,
        case_id TEXT,
        lesion_id TEXT,
        image_source_phase TEXT, 
        modality TEXT,
        jnet_class TEXT,
        kudo_class TEXT,
        paris_class TEXT,
        lst_subtype TEXT,
        invasion_depth TEXT,
        roi_json TEXT,  -- 存 Canvas 的 Polygon 座標
        quality_grade TEXT, -- A/B/C/D
        confidence_level TEXT, -- High/Med/Low
        is_keyframe INTEGER,
        teaching_point TEXT,
        annotator_id TEXT,
        created_at TEXT
    )''')
    conn.commit()
    return conn

conn = init_db()

# ==========================================
# 3. 輔助函式 (Helpers)
# ==========================================
def new_uuid():
    return str(uuid.uuid4())

def get_segments(case_id):
    df = pd.read_sql_query("SELECT * FROM video_segments WHERE case_id = ?", conn, params=(case_id,))
    return df

def save_segment(seg_data):
    c = conn.cursor()
    c.execute('''INSERT INTO video_segments VALUES (?,?,?,?,?,?,?,?)''', 
              (seg_data['segment_id'], seg_data['case_id'], seg_data['video_id'], 
               seg_data['phase_code'], seg_data['start_time'], seg_data['end_time'], 
               seg_data['annotator_id'], seg_data['created_at']))
    conn.commit()

def save_annotation(anno_data):
    c = conn.cursor()
    c.execute('''INSERT INTO image_annotations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (anno_data['annotation_id'], anno_data['case_id'], anno_data['lesion_id'],
               anno_data['image_source_phase'], anno_data['modality'],
               anno_data['jnet_class'], anno_data['kudo_class'],
               anno_data['paris_class'], anno_data['lst_subtype'],
               anno_data['invasion_depth'], anno_data['roi_json'],
               anno_data['quality_grade'], anno_data['confidence_level'],
               anno_data['is_keyframe'], anno_data['teaching_point'],
               anno_data['annotator_id'], anno_data['created_at']))
    conn.commit()

# ==========================================
# 4. Session State 初始化
# ==========================================
if 'user_id' not in st.session_state:
    st.session_state.user_id = "Dr_Wu_001"
if 'case_id' not in st.session_state:
    st.session_state.case_id = "NTUH_2025_Case001"
if 'video_id' not in st.session_state:
    st.session_state.video_id = "Vid_001.mp4"
if 'seg_start' not in st.session_state:
    st.session_state.seg_start = None

# ==========================================
# 5. UI 主邏輯
# ==========================================

# 側邊欄
st.sidebar.title("🏥 ESD/LST 標註系統 V2.0")
st.sidebar.info(f"User: {st.session_state.user_id} | Case: {st.session_state.case_id}")
app_mode = st.sidebar.selectbox("工作模式", 
    ["1. 影片階段標註 (Video Phase)", "2. 影像細節與 ROI (Image Detail)", "3. 圖譜資料庫 (Atlas DB)"])

# --- PAGE 1: VIDEO PHASE ---
if app_mode.startswith("1."):
    st.title("🎥 Project 1: Video Phase Recognition")
    
    c1, c2 = st.columns([2, 1])
    
    with c1:
        # 實務上這裡會是真實影片路徑
        st.video("https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4")
        # 模擬播放器的時間軸 (在此用 Slider 代替，實際可用 streamlit-javascript 獲取 video.currentTime)
        current_time = st.slider("Video Timeline (Seconds)", 0.0, 600.0, 0.0, 0.1, key="vid_slider")
        st.caption(f"Current Time: {current_time:.1f} s")

    with c2:
        st.subheader("階段標記控制")
        selected_phase = st.selectbox("選擇階段 (Phase)", [p[1] for p in PHASES], index=0)
        phase_code = [p[0] for p in PHASES if p[1] == selected_phase][0]
        
        # Start / End 邏輯
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("⏱️ Set START", use_container_width=True):
                st.session_state.seg_start = current_time
                st.toast(f"Start point set at {current_time}s")
        
        with col_btn2:
            if st.button("💾 Set END & Save", use_container_width=True):
                if st.session_state.seg_start is None:
                    st.error("請先設定 START 點！")
                elif current_time <= st.session_state.seg_start:
                    st.error("結束時間必須晚於開始時間！")
                else:
                    # 寫入 SQLite
                    seg_data = {
                        "segment_id": new_uuid(),
                        "case_id": st.session_state.case_id,
                        "video_id": st.session_state.video_id,
                        "phase_code": phase_code,
                        "start_time": st.session_state.seg_start,
                        "end_time": current_time,
                        "annotator_id": st.session_state.user_id,
                        "created_at": datetime.now().isoformat()
                    }
                    save_segment(seg_data)
                    st.success(f"已儲存: {selected_phase} ({seg_data['start_time']} - {seg_data['end_time']}s)")
                    st.session_state.seg_start = None # 重置
                    
                    # 自動化提示
                    if "Diagnosis" in phase_code:
                        st.info("🤖 診斷區段已記錄：背景服務將自動進行抽幀與清晰度過濾。")

        st.markdown("---")
        st.markdown("### 📋 已標註段落 (Current Case)")
        df_seg = get_segments(st.session_state.case_id)
        if not df_seg.empty:
            st.dataframe(df_seg[["phase_code", "start_time", "end_time", "created_at"]], hide_index=True)
        else:
            st.caption("尚無資料")

# --- PAGE 2: IMAGE DETAIL & ROI ---
elif app_mode.startswith("2."):
    st.title("🔬 Project 2: Image Annotation & Segmentation")
    
    col_img, col_form = st.columns([1.5, 1])
    
    with col_img:
        st.markdown("##### 影像來源: Diagnosis_NBI / Frame_0052")
        # 這裡未來接 Frame Extractor 產生的圖片
        # 使用 streamlit-drawable-canvas 讓醫生畫 ROI
        # 設置背景圖片
        bg_image_url = "https://via.placeholder.com/600x450.png?text=Lesion+Image+(NBI)"
        
        st.caption("請使用工具列畫出病灶範圍 (Polygon) 或 ROI (Rect)")
        canvas_result = st_canvas(
            fill_color="rgba(255, 165, 0, 0.3)",  # 填充顏色
            stroke_width=2,
            stroke_color="#ff0000",
            background_image=None, # 若有真實圖片，需用 PIL.Image 開啟放入這裡
            background_color="#eee",
            update_streamlit=True,
            height=450,
            drawing_mode="polygon", # 預設多邊形
            key="canvas",
        )
        
        # 顯示 ROI JSON (Debug 用，實務上隱藏)
        if canvas_result.json_data is not None:
            roi_json_str = json.dumps(canvas_result.json_data)
            st.caption(f"ROI Data Size: {len(roi_json_str)} bytes")
        else:
            roi_json_str = "{}"

    with col_form:
        with st.form("img_anno_form"):
            st.subheader("病理特徵標註")
            
            lesion_id = st.text_input("Lesion ID", value=f"{st.session_state.case_id}_L1")
            modality = st.selectbox("Modality", ["White Light", "NBI", "Indigo Carmine", "Crystal Violet"])
            
            # 動態顯示邏輯 (這裡用簡單邏輯，實際可用 JavaScript 或 callback 優化)
            c1, c2 = st.columns(2)
            with c1:
                jnet = st.selectbox("JNET Class", JNET_OPTIONS, index=0)
            with c2:
                kudo = st.selectbox("Kudo Pit", KUDO_OPTIONS, index=0)
            
            c3, c4 = st.columns(2)
            with c3:
                paris = st.selectbox("Paris Class", PARIS_OPTIONS)
            with c4:
                lst = st.selectbox("LST Subtype", LST_SUBTYPES)
            
            depth = st.radio("Invasion Depth", DEPTH_OPTIONS, horizontal=True)
            
            st.markdown("---")
            st.markdown("**品質與信心 (QC Metrics)**")
            q1, q2 = st.columns(2)
            quality = q1.select_slider("影像清晰度", options=["D (Blur)", "C", "B", "A (Clear)"], value="A (Clear)")
            confidence = q2.select_slider("診斷確信度", options=["Low", "Medium", "High"], value="High")
            
            is_key = st.checkbox("🌟 收錄為圖譜 (Key Frame)")
            teaching = st.text_area("Teaching Point", placeholder="血管紋理特徵...")
            
            if st.form_submit_button("✅ 提交標註 (Save to DB)"):
                anno_data = {
                    "annotation_id": new_uuid(),
                    "case_id": st.session_state.case_id,
                    "lesion_id": lesion_id,
                    "image_source_phase": "Diagnosis_NBI", # 範例
                    "modality": modality,
                    "jnet_class": jnet,
                    "kudo_class": kudo,
                    "paris_class": paris,
                    "lst_subtype": lst,
                    "invasion_depth": depth,
                    "roi_json": roi_json_str,
                    "quality_grade": quality,
                    "confidence_level": confidence,
                    "is_keyframe": 1 if is_key else 0,
                    "teaching_point": teaching,
                    "annotator_id": st.session_state.user_id,
                    "created_at": datetime.now().isoformat()
                }
                save_annotation(anno_data)
                st.success("標註已寫入資料庫！ROI 座標已儲存。")

# --- PAGE 3: ATLAS DB ---
else:
    st.title("📚 Automated Atlas Generation")
    
    # 搜尋過濾器
    f1, f2, f3 = st.columns(3)
    filter_jnet = f1.multiselect("Filter JNET", JNET_OPTIONS)
    filter_depth = f2.multiselect("Filter Depth", DEPTH_OPTIONS)
    
    # 構建查詢
    query = "SELECT * FROM image_annotations WHERE is_keyframe = 1"
    params = []
    
    if filter_jnet:
        query += " AND jnet_class IN ({})".format(','.join(['?']*len(filter_jnet)))
        params.extend(filter_jnet)
    
    df_atlas = pd.read_sql_query(query, conn, params=params)
    
    st.markdown(f"**Found {len(df_atlas)} Key Frames**")
    
    # 顯示結果卡片
    for idx, row in df_atlas.iterrows():
        with st.container():
            st.markdown(f"#### Case: {row['case_id']} | Lesion: {row['lesion_id']}")
            c_img, c_info = st.columns([1, 2])
            with c_img:
                st.image("https://via.placeholder.com/300x200.png?text=Key+Frame", caption=row['modality'])
                # 在此處，若要顯示 Mask，需解析 row['roi_json'] 並畫在圖上
            with c_info:
                st.write(f"**Dx:** {row['jnet_class']} / {row['kudo_class']}")
                st.write(f"**Depth:** {row['invasion_depth']}")
                st.info(f"💡 **Teaching Point:** {row['teaching_point']}")
            st.divider()
            
    # 匯出功能
    if not df_atlas.empty:
        json_str = df_atlas.to_json(orient='records', force_ascii=False)
        st.download_button("📥 下載圖譜數據 (JSON)", json_str, "atlas_export.json", "application/json")