import streamlit as st
import pandas as pd
import random
import time
import io
from pathlib import Path

# ==============================================================================
# ### 0. 資料載入函數 (Data Loading Function)
# ==============================================================================

@st.cache_data
def load_questions_from_excel(file_path):
    """
    從 Excel 檔案載入問題資料庫，並處理空儲存格。
    """
    try:
        df = pd.read_excel(file_path)
        
        # --- 處理 NaN 問題：將報告欄位中的空值替換為空字串 ---
        df['endoscopy_report'] = df['endoscopy_report'].fillna('')
        df['pathology_report'] = df['pathology_report'].fillna('')
        df['llm_suggestion'] = df['llm_suggestion'].fillna('')
        # ----------------------------------------------------
        
        questions_list = df.to_dict('records')
        return questions_list
    except FileNotFoundError:
        # 錯誤訊息
        st.error(f"Error: Question file not found at '{file_path}'.")
        st.error("Please make sure the file path is correct.")
        return []
    except Exception as e:
        # 錯誤訊息
        st.error(f"Error reading Excel file: {e}")
        return []

# ==============================================================================
# ### 1. 檔案路徑與資料庫載入 (File Path & DB Loading)
# ==============================================================================

# 取得「目前這支 .py 檔案」所在的資料夾路徑
SCRIPT_DIR = Path(__file__).parent

# 組合出資料檔案的完整路徑 (假設檔案在 data/ 資料夾中)
DATA_FILE_PATH = SCRIPT_DIR / "data" / "llm_cfs_report_questions.xlsx"

# 嘗試讀取檔案並處理錯誤訊息
try:
    df = pd.read_excel(DATA_FILE_PATH)
    # df 僅用於讀取檔案，實際問題列表使用 QUESTIONS_DB
except FileNotFoundError:
    st.error(f"Error: File not found at {DATA_FILE_PATH}")
    st.error("Please check if the file 'llm_cfs_report_questions.xlsx' exists in the 'data' folder of your GitHub repository.")

QUESTIONS_DB = load_questions_from_excel(DATA_FILE_PATH)


# --- 追蹤間隔選項 (Follow-up Interval Options) ---
FOLLOW_UP_OPTIONS = {
    "1y": "1 Year Follow-up",
    "3y": "3 Years Follow-up",
    "3-5y": "3-5 Years Follow-up",
    "5y": "5 Years Follow-up",
    "7-10y": "7-10 Years Follow-up",
    "10y": "10 Years Follow-up",
    "other": "Other",
    "malignancy": "Malignancy found, immediate clinical evaluation recommended"
}

# ==============================================================================
# ### 2. 實驗初始化與分組邏輯 (Experiment Initialization & Group Allocation)
# ==============================================================================

def initialize_experiment():
    # 初始化 Session State 變數
    if 'user_info_submitted' not in st.session_state:
        st.session_state.user_info_submitted = False
    if 'current_question_index' not in st.session_state:
        st.session_state.current_question_index = 0
    if 'results' not in st.session_state:
        st.session_state.results = []
    if 'user_info' not in st.session_state:
        st.session_state.user_info = {}

    # --- 關鍵：分配組別 (G1/G2) 和準備題目 (交叉試驗邏輯) ---
    if 'questions' not in st.session_state:
        
        if not QUESTIONS_DB:
            st.session_state.questions = []
            return

        # 1. 隨機將所有題目分為 A 組和 B 組
        all_questions = list(QUESTIONS_DB)
        
        # 確保有足夠的題目 (至少 50 題，否則調整大小)
        if len(all_questions) < 50:
            # 警告訊息
            st.warning(f"Warning: Only {len(all_questions)} questions found in Excel file. Adjusting group sizes.")
            split_point = len(all_questions) // 2
            set_A = all_questions[:split_point]
            set_B = all_questions[split_point:]
        else:
            random.shuffle(all_questions)
            set_A = all_questions[:25]
            set_B = all_questions[25:]
        
        # 2. 隨機將參與者分配到 G1 或 G2
        if 'participant_group' not in st.session_state.user_info:
            st.session_state.user_info['participant_group'] = random.choice(['G1', 'G2'])

        participant_group = st.session_state.user_info['participant_group']
        phase_1_questions = []
        phase_2_questions = []
        
        if participant_group == 'G1':
            # G1: Phase 1 (Set A, No LLM), Phase 2 (Set B, With LLM)
            for q in set_A:
                new_q = q.copy(); new_q['show_llm'] = False; new_q['phase'] = 1; new_q['question_set'] = 'A'; phase_1_questions.append(new_q)
            for q in set_B:
                new_q = q.copy(); new_q['show_llm'] = True; new_q['phase'] = 2; new_q['question_set'] = 'B'; phase_2_questions.append(new_q)
        else: # G2
            # G2: Phase 1 (Set B, With LLM), Phase 2 (Set A, No LLM)
            for q in set_B:
                new_q = q.copy(); new_q['show_llm'] = True; new_q['phase'] = 1; new_q['question_set'] = 'B'; phase_1_questions.append(new_q)
            for q in set_A:
                new_q = q.copy(); new_q['show_llm'] = False; new_q['phase'] = 2; new_q['question_set'] = 'A'; phase_2_questions.append(new_q)
        
        # 3. 組合兩個階段的題目並儲存到 Session State
        st.session_state.questions = phase_1_questions + phase_2_questions
        
    # 初始化單題計時器
    if 'question_start_time' not in st.session_state:
        st.session_state.question_start_time = time.perf_counter()

# ==============================================================================
# ### 3. 答案提交處理 (Answer Submission Handler)
# ==============================================================================

def submit_answer(selected_option_key):
    # 1. 計算花費時間
    end_time = time.perf_counter()
    time_taken = end_time - st.session_state.question_start_time
    
    # 2. 獲取當前題目資訊
    q_index = st.session_state.current_question_index
    current_q = st.session_state.questions[q_index]
    
    # 3. 檢查答案準確性
    is_correct = (selected_option_key == current_q['correct_answer'])
    
    # 4. 記錄結果
    result_data = {
        "user_name": st.session_state.user_info.get('name', 'N/A'),
        "background": st.session_state.user_info.get('is_gastro', 'N/A'),
        "practice_years": st.session_state.user_info.get('practice_years', 0),
        "participant_group": st.session_state.user_info.get('participant_group', 'N/A'),
        "phase": current_q['phase'],
        "question_set": current_q['question_set'],
        "question_id": current_q['id'],
        "question_index_session": q_index + 1,
        "llm_assisted": current_q['show_llm'],
        "selected_answer": selected_option_key,
        "correct_answer": current_q['correct_answer'],
        "is_correct": is_correct,
        "time_taken_seconds": time_taken
    }
    st.session_state.results.append(result_data)
    
    # 5. 移至下一題
    st.session_state.current_question_index += 1
    
    # 6. 重置下一題的開始時間
    st.session_state.question_start_time = time.perf_counter()

# ==============================================================================
# ### 4. 顯示結果與下載 (Show Results & Download)
# ==============================================================================

def show_results_and_download():
    # 介面文字
    st.success("Experiment Complete! Thank thank you for your participation.")
    results_df = pd.DataFrame(st.session_state.results)
    st.dataframe(results_df)
    
    # 介面文字
    st.subheader("Preliminary Results Summary")
    if not results_df.empty:
        try:
            # 介面文字
            st.write("--- Grouped by LLM Assistance (All Questions) ---")
            summary_llm = results_df.groupby('llm_assisted').agg(
                accuracy=('is_correct', 'mean'),
                average_time=('time_taken_seconds', 'mean')
            ).reset_index()
            summary_llm['accuracy'] = (summary_llm['accuracy'] * 100).round(2)
            st.dataframe(summary_llm)

            # 介面文字
            st.write("--- Phase 1 Only (Cleanest Data) ---")
            phase_1_data = results_df[results_df['phase'] == 1]
            if not phase_1_data.empty:
                summary_phase1 = phase_1_data.groupby('llm_assisted').agg(
                    accuracy=('is_correct', 'mean'),
                    average_time=('time_taken_seconds', 'mean')
                ).reset_index()
                summary_phase1['accuracy'] = (summary_phase1['accuracy'] * 100).round(2)
                st.dataframe(summary_phase1)
            else:
                # 介面文字
                st.write("No data available for Phase 1 analysis yet.")
            
        except Exception as e:
            # 介面文字
            st.warning(f"Error generating summary: {e}")
    
    # --- 下載 CSV 的程式碼 (Download CSV) ---
    @st.cache_data
    def convert_df_to_csv(df):
       output = io.StringIO()
       df.to_csv(output, index=False, encoding='utf-8-sig')
       return output.getvalue()
       
    csv_data = convert_df_to_csv(results_df)
    
    # 介面文字
    st.download_button(
        label="Download Experiment Results (CSV)",
        data=csv_data,
        file_name=f"study_results_{st.session_state.user_info.get('name', 'user')}.csv",
        mime="text/csv",
    )

# ==============================================================================
# ### 5. 使用者登入表單 (User Login Form)
# ==============================================================================

def show_login_form():
    # 介面文字
    st.header("Welcome to the Experiment")
    st.write("Before you begin, please provide your information:")
    
    with st.form(key="user_info_form"):
        # 介面文字
        user_name = st.text_input("Your Name or ID", placeholder="e.g., David Wang or User01")
        
        # 介面文字 (選項)
        is_gastro = st.radio(
            "What is your attending physician background?",
            options=[
                # 選項翻譯
                "Senior Gastroenterologist (Attending > 5 years)", 
                "Junior Gastroenterologist (Attending <= 5 years)", 
                "Non-Gastroenterologist (e.g., Intern, Resident, other specialty)"
            ],
            index=None
        )
        
        # 介面文字
        practice_years = st.number_input(
            "How many years have you been an Attending Physician? (Enter 0 if not applicable)",
            min_value=0, max_value=50, step=1, value=0
        )
        
        # 介面文字
        submitted = st.form_submit_button("Start Experiment")
        
        if submitted:
            # 錯誤訊息
            if not user_name:
                st.error("Please enter your name or ID")
            elif is_gastro is None:
                st.error("Please select your background")
            else:
                # 儲存使用者資訊到 Session State
                st.session_state.user_info = {
                    "name": user_name,
                    "is_gastro": is_gastro,
                    "practice_years": practice_years
                }
                st.session_state.user_info_submitted = True
                st.session_state.question_start_time = time.perf_counter()
                st.rerun()

# ==============================================================================
# ### 6. 自定義 CSS 樣式 (Custom CSS Styles)
# ==============================================================================

st.markdown("""
<style>
/* 報告框樣式：用於 Endoscopy Report 和 Pathology Report */
.report-box {
    background-color: #e6f7ff; /* 淺藍色背景 */
    padding: 15px;
    border-radius: 5px;
    border: 1px solid #91d5ff;
    /* 讓內容能自動換行並顯示滾動條 */
    white-space: pre-wrap; 
    overflow-wrap: break-word;
    max-height: 300px; /* 限制高度 */
    overflow-y: auto; /* 超出時顯示滾動條 */
    font-family: monospace; /* 可選：使用等寬字體讓報告更清晰 */
}
</style>
""", unsafe_allow_html=True)


# ==============================================================================
# ### 7. 主應用程式介面 (Main App Interface)
# ==============================================================================

st.set_page_config(layout="wide")

# 介面標題
st.title("Colonoscopy Follow-up Interval Clinical Decision Experiment")

# 檢查資料庫是否成功載入
if not QUESTIONS_DB:
    st.warning("Failed to load question database. Please check the Excel file path and content.")
    st.stop()

# 初始化實驗 (執行交叉試驗的分配)
initialize_experiment()

# --- 介面流程控制 ---
if not st.session_state.user_info_submitted:
    # 流程 1: 顯示登入表單
    show_login_form()

elif st.session_state.current_question_index >= len(st.session_state.questions):
    # 流程 2: 顯示結果與下載
    show_results_and_download()

else:
    # 流程 3: 顯示題目
    
    # 確保題目列表非空
    if not st.session_state.questions:
        st.error("Error: Question list is empty. Cannot continue.")
        st.stop()
        
    q_index = st.session_state.current_question_index
    
    # 檢查題目索引
    if q_index >= len(st.session_state.questions):
        st.error("Error: Question index is out of range. Please refresh.")
        st.session_state.current_question_index = 0
        st.stop()
        
    current_q = st.session_state.questions[q_index]
    
    # --- 題目標頭資訊 ---
    # 介面文字
    st.header(f"Question {q_index + 1} / {len(st.session_state.questions)}")
    st.caption(f"Participant: {st.session_state.user_info.get('name', '')} (Group: {st.session_state.user_info.get('participant_group', 'N/A')})")
    
    # 介面文字
    if current_q['phase'] == 1:
        st.info(f"Phase 1 / 2 (Question Set: {current_q['question_set']})")
    else:
        st.info(f"Phase 2 / 2 (Question Set: {current_q['question_set']})")
    
    # --- 報告與選項欄位 ---
    col1, col2 = st.columns([2, 1])

    with col1:
        # 內視鏡報告 (Endoscopy Report)
        st.subheader("Endoscopy Report")
        endoscopy_html = f"""
        <div class="report-box">
            {current_q['endoscopy_report']}
        </div>
        """
        st.markdown(endoscopy_html, unsafe_allow_html=True)
        
        # 病理報告 (Pathology Report)
        st.subheader("Pathology Report")
        pathology_html = f"""
        <div class="report-box">
            {current_q['pathology_report']}
        </div>
        """
        st.markdown(pathology_html, unsafe_allow_html=True)
        
    with col2:
        # LLM 輔助建議
        if current_q['show_llm']:
            # 介面文字
            st.info(f"🤖 LLM Assisted Suggestion:\n\n{current_q['llm_suggestion']}")
        else:
            # 介面文字
            st.warning("LLM assistance is not provided in this phase.")
            
        # 選擇追蹤間隔
        # 介面文字
        st.subheader("Please select the follow-up interval:")
        
        option_key = st.radio(
            "Follow-up Options", # 介面文字
            options=list(FOLLOW_UP_OPTIONS.keys()), 
            format_func=lambda x: FOLLOW_UP_OPTIONS[x], 
            key=f"q_{current_q['id']}",
            index=None
        )
        
        # 答案提交按鈕
        # 介面文字
        if st.button("Submit Answer and Next Question"):
            # 警告訊息
            if option_key is None:
                st.warning("Please select an option!")
            else:
                submit_answer(option_key)
                st.rerun()