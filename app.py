import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="유량 데이터 추출기", layout="wide")
st.title("🌊 유량 데이터 추출 by KJH(.dis 전용)")
st.info("💡 .dis 파일을 드래그 앤 드롭하면 즉시 엑셀 데이터로 변환됩니다.")

# 데이터 및 초기화 키 세션 상태
if "flow_data" not in st.session_state:
    st.session_state.flow_data = []
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

def parse_dis_file(file_content, filename):
    # 1. 요청하신 순서대로 컬럼 초기화
    columns = [
        "파일명", "사이트 이름", "측정 날짜", "시스템 테스트시간(hh:mm)", "배", 
        "시작수위", "종료수위", "평균수위", "폭", "면적", 
        "평균속력", "평균깊이", "총 Q", "시리얼번호", "측정 횟수(Tr)", 
        "변환기 깊이", "최대 깊이", "최대 스피드", "자기편차", 
        "측정된 %(mean)", "보트속력(mean)", "트랙거리(mean)", 
        "작업자", "위치"
    ]
    
    data = {col: "-" for col in columns}
    data["파일명"] = filename

    # 2. 단일 값 정규식 매핑
    patterns = {
        "사이트 이름": r"Site Name;\s*(.*)",
        "측정 날짜": r"Date Measured:\s*([0-9-]+)",
        "배": r"Boat/Motor;\s*(.*)",
        "폭": r"Width\s*\(m\);\s*([0-9.]+)",
        "면적": r"Area\s*\(m\s*[²2]\);\s*([0-9.]+)",
        "평균속력": r"Mean Speed\s*\(m/s\);\s*([0-9.]+)",
        "평균깊이": r"Mean Depth\s*\(m\);\s*([0-9.]+)",
        "총 Q": r"Total Q\s*\(m\s*[³3]/s\);\s*([0-9.]+)",
        "시리얼번호": r"Serial Number;\s*(.*)",
        "변환기 깊이": r"Transducer Depth\s*\(m\);\s*([0-9.]+)",
        "최대 깊이": r"Maximum Depth\s*\(m\);\s*([0-9.]+)",
        "최대 스피드": r"Maximum Speed\s*\(m/s\);\s*([0-9.]+)",
        "자기편차": r"Magnetic Declination\s*\(deg\);\s*([0-9.-]+)",
        "작업자": r"Party;\s*(.*)",
        "위치": r"Location;\s*(.*)"
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, file_content)
        if match:
            data[key] = match.group(1).strip()

    # 3. 수위 (Gauge Height) 3칸 동일 적용 로직
    gauge_m = re.search(r"Gauge Height.*?[;:]\s*([0-9.]+)", file_content)
    if gauge_m:
        gauge_val = gauge_m.group(1).strip()
        data["시작수위"] = gauge_val
        data["종료수위"] = gauge_val
        data["평균수위"] = gauge_val

    # 4. Transect 테이블 분석 (개수 및 Mean 계산)
    in_table = False
    transects = []
    for line in file_content.split('\n'):
        if line.startswith("Transect\tFile Name"):
            in_table = True
            continue
        if in_table:
            parts = line.split('\t')
            # 행이 숫자(Tr#)로 시작하고 데이터가 있는 경우만 수집
            if len(parts) > 15 and parts[0].strip().isdigit():
                transects.append(parts)

    if transects:
        data["측정 횟수(Tr)"] = str(len(transects))
        try:
            # 합계 계산
            track_sum = sum(float(t[5]) for t in transects if t[5].strip())
            boat_spd_sum = sum(float(t[9]) for t in transects if t[9].strip())
            pct_meas_sum = sum(float(t[18].strip()) for t in transects if len(t) > 18 and t[18].strip())
            
            # 평균(Mean) 할당
            data["트랙거리(mean)"] = f"{track_sum / len(transects):.3f}"
            data["보트속력(mean)"] = f"{boat_spd_sum / len(transects):.4f}"
            data["측정된 %(mean)"] = f"{pct_meas_sum / len(transects):.2f}"
            
            # 5. 시스템 테스트 시간 추출 (Transect 1의 Start Time 기준)
            time_str = transects[0][3]
            m = re.search(r"\d{4}-\d{2}-\d{2}\s+(\d{2}:\d{2})", time_str)
            if m:
                data["시스템 테스트시간(hh:mm)"] = m.group(1)
        except Exception:
            pass

    return data

# 파일 업로더
uploaded_files = st.file_uploader(
    "📁 .dis 파일을 여기에 드래그하거나 선택하세요", 
    type=["dis", "txt"], 
    accept_multiple_files=True,
    key=f"uploader_{st.session_state.uploader_key}"
)

if uploaded_files:
    for file in uploaded_files:
        if not any(d["파일명"] == file.name for d in st.session_state.flow_data):
            try:
                content = file.getvalue().decode('utf-8')
            except UnicodeDecodeError:
                content = file.getvalue().decode('euc-kr')
            st.session_state.flow_data.append(parse_dis_file(content, file.name))

if st.session_state.flow_data:
    # 딕셔너리 순서대로 DataFrame 생성
    df = pd.DataFrame(st.session_state.flow_data)
    
    st.markdown("### 💾 저장 설정")
    custom_filename = st.text_input("저장할 파일 이름을 입력하세요 (확장자 제외)", value="수문유량결과_최종본")
    
    col1, col2, col3 = st.columns(3)
    
    csv_bytes = df.to_csv(index=False).encode('utf-8-sig')
    with col1:
        st.download_button(
            label="📥 CSV 포맷 다운로드", 
            data=csv_bytes, 
            file_name=f"{custom_filename}.csv", 
            mime="text/csv",
            use_container_width=True
        )
        
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='수문유량결과')
    with col2:
        st.download_button(
            label="📊 Excel 포맷 다운로드", 
            data=output.getvalue(), 
            file_name=f"{custom_filename}.xlsx", 
            mime="application/vnd.ms-excel",
            use_container_width=True
        )

    with col3:
        if st.button("🔄 전체 데이터 및 파일 초기화", type="primary", use_container_width=True):
            st.session_state.flow_data = []
            st.session_state.uploader_key += 1
            st.rerun()

    st.markdown("---")
    st.data_editor(df, use_container_width=True)