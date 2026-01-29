import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

st.title("Google Sheets Connection Test")

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(worksheet="Sheet1", ttl=0) # 這裡記得改成您的分頁名稱
    st.success("成功連線並讀取資料！")
    st.write("目前的資料內容：")
    st.dataframe(df)
    
    # 測試寫入功能
    if st.button("測試寫入一筆測試資料"):
        test_data = pd.DataFrame([{"user_name": "Test_User", "comparison": "Connection_OK"}])
        updated_df = pd.concat([df, test_data], ignore_index=True)
        conn.update(worksheet="Sheet1", data=updated_df)
        st.balloons()
        st.success("寫入測試成功！請去查看 Google Sheet。")

except Exception as e:
    st.error("連線失敗！具體錯誤訊息如下：")
    st.code(str(e))