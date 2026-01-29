import streamlit as st
import pandas as pd
import random
import time
import io
import os
from pathlib import Path
from streamlit_gsheets import GSheetsConnection

# ==============================================================================
# ### 0. 常數與權重定義 (Constants & Rankings)
# ==============================================================================

# 檔案路徑設定
SCRIPT_DIR = Path(__file__).parent
DATA_FILE_PATH = SCRIPT_DIR / "data" / "llm_cfs_report_questions.xlsx"

# 追蹤間隔權重：用於計算 Earlier/Same/Later (10y 最晚，1y 最早)
INTERVAL_RANK = {
    "1y": 1,
    "3y": 2,
    "3-5y": 3,
    "5-10y": 4,
    "7-10y": 5,
    "10y": 6,
    "other": 0,
    "malignancy": 0
}

# 網頁顯示選項
FOLLOW_UP_OPTIONS = {
    "1y": "1 Year Follow-up",
    "3y": "3 Years Follow-up",
    "3-5y": "3-5 Years Follow-up",
    "5-10y": "5-10 Years Follow-up",
    "7-10y": "7-10 Years Follow-up",
    "10y": "10 Years Follow-up",
    "other": "Other",
    "malignancy": "Malignancy found, immediate clinical evaluation recommended"
}

# ==============================================================================
# ### 1. 核心邏輯函數 (Core Logic Functions)
# ==============================================================================

@st.cache_data
def load_questions_from_excel(file_path):
    """從 Excel 載入題庫並處理空值"""
    try:
        df = pd.read_excel(file_path)
        df['endoscopy_report'] = df['endoscopy_report'].fillna('')
        df['pathology_report'] = df['pathology_report'].fillna('')
        df['llm_suggestion'] = df['llm_suggestion'].fillna('')
        return df.to_dict('records')
    except Exception as e:
        st.error(f"Excel Load Error: {e}")
        return []

def get_comparison(reply, correct):
    """邏輯比較：判斷醫師回答比標準答案 早、一樣、或晚"""
    r_val = INTERVAL_RANK.get(reply, 0)
    c_val = INTERVAL_RANK.get(correct, 0)
    
    if r_val == 0 or c_val == 0: return "N/A"
    if r_val > c_val: return "Later (Under-surveillance)"
    if r_val < c_val: return "Earlier (Over-surveillance)"
    return "Same"

def sync_to_google_sheets(new_data):
    """即時將答題結果同步至 Google Sheets 避免資料遺失"""
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        # 讀取現有資料
        existing_df = conn.read(worksheet="Sheet1", ttl=0)
        # 附加新行
        new_df = pd.DataFrame([new_data])
        updated_df = pd.concat([existing_df, new_df], ignore_index=True)
        # 寫回雲端
        conn.update(worksheet="Sheet1", data=updated_df)
    except Exception as e:
        st.warning(f"Cloud Sync Delay/Error: {e}") # 同步失敗時僅警告，不中斷實驗

# ==============================================================================
# ### 2. 實驗初始化 (Initialization)
# ==============================================================================

def initialize_experiment():
    # 初始化 session state
    if 'user_info_submitted' not in st.session_state:
        st.session_state.user_info_submitted = False
    if 'current_question_index' not in st.session_state:
        st.session_state.current_question_index = 0
    if 'results' not in st.session_state:
        st.session_state.results = []
    if 'total_time_spent' not in st.session_state:
        st.session_state.total_time_spent = {} # 紀錄每題累積耗時
    if 'user_info' not in st.session_state:
        st.session_state.user_info = {}

    # 交叉設計分組邏輯
    if 'questions' not in st.session_state:
        db = load_questions_from_excel(DATA_FILE_PATH)
        if not db: return

        # 取前 40 題，分為 A (0-19), B (20-39)
        selected = db[:40]
        set_A = selected[:20]
        set_B = selected[20:]
        
        # 隨機分配參與者到 G1 或 G2
        if 'participant_group' not in st.session_state.user_info:
            st.session_state.user_info['participant_group'] = random.choice(['G1', 'G2'])

        group = st.session_state.user_info['participant_group']
        final_list = []
        if group == 'G1':
            # G1: P1(Set A, No LLM) -> P2(Set B, With LLM)
            for q in set_A: final_list.append({**q, 'show_llm': False, 'phase': 1, 'set': 'A'})
            for q in set_B: final_list.append({**q, 'show_llm': True, 'phase': 2, 'set': 'B'})
        else:
            # G2: P1(Set B, No LLM) -> P2(Set A, With LLM)
            for q in set_B: final_list.append({**q, 'show_llm': False, 'phase': 1, 'set': 'B'})
            for q in set_A: final_list.append({**q, 'show_llm': True, 'phase': 2, 'set': 'A'})
        
        st.session_state.questions = final_list
        
    if 'question_start_time' not in st.session_state:
        st.session_state.question_start_time = time.perf_counter()

# ==============================================================================
# ### 3. 動作處理邏輯 (Action Handlers)
# ==============================================================================

def handle_submit(ans_key):
    """處理提交下一題"""
    # 1. 計算當前這一段花費的時間並累加
    now = time.perf_counter()
    elapsed = now - st.session_state.question_start_time
    idx = st.session_state.current_question_index
    st.session_state.total_time_spent[idx] = st.session_state.total_time_spent.get(idx, 0) + elapsed
    
    current_q = st.session_state.questions[idx]
    
    # 2. 封裝數據
    row = {
        **st.session_state.user_info, # 這已經包含 user_name, participant_group 等所有欄位
        "phase": current_q['phase'],
        "question_id": current_q['id'],
        "question_index": idx + 1,
        "llm_assisted": current_q['show_llm'],
        "reply_answer": ans_key,
        "correct_answer": current_q['correct_answer'],
        "comparison": get_comparison(ans_key, current_q['correct_answer']),
        "is_correct": ans_key == current_q['correct_answer'],
        "time_taken_seconds": round(st.session_state.total_time_spent[idx], 2)
    }
    
    # 3. 儲存與同步
    st.session_state.results.append(row)
    sync_to_google_sheets(row) # 每題完成即同步
    
    # 4. 前進下一題
    st.session_state.current_question_index += 1
    st.session_state.question_start_time = time.perf_counter()

def handle_back():
    """處理回到上一題 (保留目前已花費時間)"""
    if st.session_state.current_question_index > 0:
        # 先儲存當前這題目前花掉的時間，以免切換遺失
        now = time.perf_counter()
        elapsed = now - st.session_state.question_start_time
        curr_idx = st.session_state.current_question_index
        st.session_state.total_time_spent[curr_idx] = st.session_state.total_time_spent.get(curr_idx, 0) + elapsed
        
        # 退回索引並移除最後一筆結果
        st.session_state.current_question_index -= 1
        if st.session_state.results:
            st.session_state.results.pop()
        
        st.session_state.question_start_time = time.perf_counter()

# ==============================================================================
# ### 4. UI 介面 (User Interface)
# ==============================================================================

st.set_page_config(layout="wide", page_title="Clinical Experiment")

# 注入自定義 CSS (報告框與按鈕樣式)
st.markdown("""
<style>
.report-box { background-color: #f8f9fa; padding: 20px; border-radius: 10px; border: 1px solid #dee2e6; 
              white-space: pre-wrap; word-wrap: break-word; font-family: 'Consolas', monospace; margin-bottom: 25px; }
.stButton>button { width: 100%; }
</style>
""", unsafe_allow_html=True)

initialize_experiment()

# --- 流程 1: 登入表單 (Login Form) ---
if not st.session_state.user_info_submitted:
    with st.form("login_panel"):
        st.header("Physician Demographic Information")
        name = st.text_input("Full Name / Participant ID")
        bg = st.radio("Professional Background", 
                      ["Senior Gastro (>5y)", "Junior Gastro (<=5y)", "Non-Gastro specialist"])
        years = st.number_input("Years of Practice as Attending", 0, 50)
        
        if st.form_submit_button("Start Experiment"):
            if name:
                # 使用 update 以保留 initialize_experiment 中產生的 participant_group
                st.session_state.user_info.update({
                    "user_name": name, 
                    "is_gastro": bg, 
                    "practice_years": years
                })
                st.session_state.user_info_submitted = True
                st.rerun()
            else: 
                st.warning("Please enter your Name or ID.")

# --- 流程 2: 實驗結束 (Results Page) ---
elif st.session_state.current_question_index >= len(st.session_state.questions):
    st.balloons()
    st.success("Experiment Complete! Your responses have been synced to the cloud.")
    
    final_df = pd.DataFrame(st.session_state.results)
    st.subheader("Your Performance Summary")
    st.dataframe(final_df)
    
    # 下載按鈕 (最後防線)
    csv = final_df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
    st.download_button("Download CSV Backup", csv, f"backup_{st.session_state.user_info['user_name']}.csv", "text/csv")

# --- 流程 3: 答題中 (Question Page) ---
else:
    idx = st.session_state.current_question_index
    q = st.session_state.questions[idx]
    
    # 顯示進度條
    st.progress(idx / len(st.session_state.questions))
    st.header(f"Question {idx + 1} / {len(st.session_state.questions)}")
    
    col_left, col_right = st.columns([2, 1])
    
    with col_left:
        st.subheader("Endoscopy Report")
        st.markdown(f'<div class="report-box">{q["endoscopy_report"]}</div>', unsafe_allow_html=True)
        st.subheader("Pathology Report")
        st.markdown(f'<div class="report-box">{q["pathology_report"]}</div>', unsafe_allow_html=True)
        
    with col_right:
        # LLM 輔助區塊
        if q['show_llm']:
            st.info(f"🤖 **LLM Assisted Suggestion:**\n\n{q['llm_suggestion']}")
        else:
            st.warning("⚠️ **Control Phase:** LLM assistance is disabled.")
            
        st.subheader("Surveillance Interval Selection")
        st.caption("Based on 2020 USMSTF Guidelines")
        
        # 答題選項
        user_choice = st.radio("Select the most appropriate interval:", 
                               options=list(FOLLOW_UP_OPTIONS.keys()), 
                               format_func=lambda x: FOLLOW_UP_OPTIONS[x], 
                               key=f"radio_{idx}", index=None)
        
        st.markdown("---")
        # 導覽按鈕區
        nav1, nav2 = st.columns(2)
        with nav1:
            if st.button("⬅ Back", disabled=(idx == 0)):
                handle_back()
                st.rerun()
        with nav2:
            if st.button("Submit & Next ➡", type="primary"):
                if user_choice:
                    handle_submit(user_choice)
                    st.rerun()
                else: st.error("Please select an option before moving forward.")