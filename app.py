import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="수문 유량 데이터 추출기", layout="wide")
st.title("🌊 수문 유량 데이터 추출기 by KJH (.dis 전용)")
st.info("💡 .dis 파일을 드래그 앤 드롭하면 즉시 엑셀 데이터로 변환됩니다.")

if "flow_data" not in st.session_state:
    st.session_state.flow_data = []

def parse_dis_file(file_content, filename):
    data = {"파일명": filename}
    keys = ["측정일", "사이트명", "위치", "게이지높이(m)", "작업자", "배", 
            "폭(m)", "면적(m²)", "평균 깊이(m)", "평균 속력(m/s)", 
            "총 Q(m³/s)", "최대 깊이(m)", "최대 스피드(m/s)"]
    for k in keys: data[k] = "-"

    patterns = {
        "측정일": r"Date Measured:\s*([0-9-]+)",
        "사이트명": r"Site Name;\s*(.*)",
        "위치": r"Location;\s*(.*)",
        "게이지높이(m)": r"Gauge Height.*?;([0-9.]+)",
        "작업자": r"Party;\s*(.*)",
        "배": r"Boat/Motor;\s*(.*)",
        "폭(m)": r"Width\s*\(m\);\s*([0-9.]+)",
        "면적(m²)": r"Area\s*\(m\s*[²2]\);\s*([0-9.]+)",
        "평균 깊이(m)": r"Mean Depth\s*\(m\);\s*([0-9.]+)",
        "평균 속력(m/s)": r"Mean Speed\s*\(m/s\);\s*([0-9.]+)",
        "총 Q(m³/s)": r"Total Q\s*\(m\s*[³3]/s\);\s*([0-9.]+)",
        "최대 깊이(m)": r"Maximum Depth\s*\(m\);\s*([0-9.]+)",
        "최대 스피드(m/s)": r"Maximum Speed\s*\(m/s\);\s*([0-9.]+)"
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, file_content)
        if match:
            data[key] = match.group(1).strip()
    return data

uploaded_files = st.file_uploader("📁 .dis 파일 업로드 (여러 개 가능)", type=["dis", "txt"], accept_multiple_files=True)

if uploaded_files:
    for file in uploaded_files:
        if not any(d["파일명"] == file.name for d in st.session_state.flow_data):
            try:
                content = file.getvalue().decode('utf-8')
            except UnicodeDecodeError:
                content = file.getvalue().decode('euc-kr')
            st.session_state.flow_data.append(parse_dis_file(content, file.name))

if st.session_state.flow_data:
    df = pd.DataFrame(st.session_state.flow_data)
    
    col1, col2, col3 = st.columns([1, 1, 6])
    csv_bytes = df.to_csv(index=False).encode('utf-8-sig')
    col1.download_button("📄 CSV 저장", data=csv_bytes, file_name="유량결과.csv", mime="text/csv")
        
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='수문유량결과')
    col2.download_button("📊 Excel 저장", data=output.getvalue(), file_name="유량결과.xlsx", mime="application/vnd.ms-excel")

    if col3.button("🗑️ 초기화", type="primary"):
        st.session_state.flow_data = []
        st.rerun()

    st.data_editor(df, use_container_width=True)