import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime, timedelta

st.set_page_config(page_title="유량 데이터 추출기", layout="wide")
st.title("🌊 유량 데이터 추출(.dis 전용)")
st.info("💡 .dis 파일을 드래그 앤 드롭하면 즉시 지정된 순서대로 엑셀 데이터가 추출 및 계산됩니다. by KJH")

# 데이터 및 초기화 키 세션 상태
if "flow_data" not in st.session_state:
    st.session_state.flow_data = []
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

def format_measurement_time(start_time_str, end_time_str, duration_str):
    """최초 시작시간과 마지막 종료시간을 바탕으로 10분 단위 측정시간 범위 계산"""
    try:
        # 1. 시작 시간 계산 (-10분 후 10분 단위로 내림)
        start_dt = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
        logical_start_dt = start_dt - timedelta(minutes=10)
        logical_start_min = (logical_start_dt.minute // 10) * 10
        logical_start_dt = logical_start_dt.replace(minute=logical_start_min, second=0)
        
        # 2. 종료 시간 계산 (마지막 측정시간 + 소요시간 후 10분 단위로 올림)
        h, m, s = map(int, duration_str.split(':'))
        end_dt = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")
        real_end_dt = end_dt + timedelta(hours=h, minutes=m, seconds=s)
        
        minutes_up = ((real_end_dt.minute // 10) + 1) * 10
        if real_end_dt.minute % 10 == 0 and real_end_dt.second == 0:
            logical_end_dt = real_end_dt
        else:
            diff = minutes_up - real_end_dt.minute
            logical_end_dt = real_end_dt + timedelta(minutes=diff)
            logical_end_dt = logical_end_dt.replace(second=0)
            
        return f"{logical_start_dt.strftime('%H:%M')} ~ {logical_end_dt.strftime('%H:%M')}"
    except Exception:
        return "-"

def parse_dis_file(file_content, filename):
    # 1. 요청하신 순서대로 컬럼 초기화 (시스템 테스트시간 -> 측정시간)
    columns = [
        "파일명", "사이트 이름", "측정 날짜", "측정시간", "배", 
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
            val = match.group(1).strip()
            # 소수점 반올림 처리
            if key == "총 Q":
                data[key] = f"{float(val):.3f}"
            elif key in ["평균속력", "평균깊이"]:
                data[key] = f"{float(val):.2f}"
            else:
                data[key] = val

    # 3. 수위 (Gauge Height) 3칸 동일 적용 로직
    gauge_val = "-"
    g_match_supp = re.search(r"Start Gauge Height[^\n]*\n+(\d+\s*;\s*[^;]+\s*;\s*([0-9.]+)\s*;)", file_content)
    if g_match_supp:
        gauge_val = g_match_supp.group(2).strip()
    else:
        g_match_gen = re.search(r"Gauge Height.*?[;:]\s*([0-9.]+)", file_content, re.IGNORECASE)
        if g_match_gen:
            gauge_val = g_match_gen.group(1).strip()

    if gauge_val != "-":
        data["시작수위"] = gauge_val
        data["종료수위"] = gauge_val
        data["평균수위"] = gauge_val

    # 4. Transect 테이블 분석 (개수, 시간, Mean 계산)
    in_table = False
    transects = []
    for line in file_content.split('\n'):
        if line.startswith("Transect\tFile Name"):
            in_table = True
            continue
        if in_table:
            parts = line.split('\t')
            if len(parts) > 15 and parts[0].strip().isdigit():
                transects.append(parts)

    if transects:
        data["측정 횟수(Tr)"] = str(len(transects))
        try:
            # 5. 측정시간(hh:mm 범위) 계산
            first_start_time = transects[0][3]
            last_start_time = transects[-1][3]
            last_duration = transects[-1][4]
            data["측정시간"] = format_measurement_time(first_start_time, last_start_time, last_duration)

            # 합계 및 평균(Mean) 계산
            track_sum = sum(float(t[5]) for t in transects if t[5].strip())
            boat_spd_sum = sum(float(t[9]) for t in transects if t[9].strip())
            pct_meas_sum = sum(float(t[18].strip()) for t in transects if len(t) > 18 and t[18].strip())
            
            data["트랙거리(mean)"] = f"{track_sum / len(transects):.3f}"
            data["보트속력(mean)"] = f"{boat_spd_sum / len(transects):.4f}"
            data["측정된 %(mean)"] = f"{pct_meas_sum / len(transects):.2f}"
            
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
    df = pd.DataFrame(st.session_state.flow_data)
    
    st.markdown("### 💾 저장 설정")
    today_str = datetime.now().strftime("%y%m%d")
    default_name=f"{today_str}_"
    custom_filename = st.text_input("저장할 파일 이름을 입력하세요 (예시 260705_5팀)", value=default_name)
    
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