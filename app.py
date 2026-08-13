import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime, timedelta, date, time

st.set_page_config(page_title="유량 데이터 추출기", layout="wide")
st.title("🌊 유량 데이터 추출(.dis 전용)")
st.info("💡 .dis 파일을 드래그 앤 드롭하면 즉시 지정된 순서대로 엑셀 데이터가 추출 및 계산됩니다. by KJH")

# 데이터 및 초기화 키 세션 상태
if "flow_data" not in st.session_state:
    st.session_state.flow_data = []
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

def format_measurement_time(first_start_time, last_start_time, last_duration):
    """최초 시작시간과 마지막 종료시간을 바탕으로 10분 단위 측정시간 범위 계산 (한/영 시간 포맷 대응)"""
    dummy_date = date(2000, 1, 1) 
    
    def to_datetime(t_str):
        if '오전' in t_str or '오후' in t_str:
            t_str = t_str.strip()
            is_pm = '오후' in t_str
            time_part = t_str.replace('오전', '').replace('오후', '').strip()
            h, m, s = map(int, time_part.split(':'))
            if is_pm and h < 12: h += 12
            elif not is_pm and h == 12: h = 0
            return datetime.combine(dummy_date, time(h, m, s))
        else:
            return datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S")

    try:
        # 1. 시작 시간 계산 (-10분 후 10분 단위로 내림)
        start_dt = to_datetime(first_start_time)
        logical_start_dt = start_dt - timedelta(minutes=10)
        logical_start_min = (logical_start_dt.minute // 10) * 10
        logical_start_dt = logical_start_dt.replace(minute=logical_start_min, second=0)
        
        # 2. 종료 시간 계산 (마지막 측정시간 + 소요시간 후 10분 단위로 올림)
        h, m, s = map(int, last_duration.strip().split(':'))
        end_dt = to_datetime(last_start_time)
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
    # 컬럼 초기화
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

    # 단일 값 정규식 매핑 (한글/영문 파일 완벽 대응)
    patterns = {
        "사이트 이름": r"(?:Site Name|사이트 이름);\s*(.*)",
        "측정 날짜": r"(?:Date Measured|생성 날짜):\s*([0-9-]+)",
        "배": r"(?:Boat/Motor|보트/모터);\s*(.*)",
        "폭": r"(?:Width|폭)\s*\(m\);\s*([0-9.]+)",
        "면적": r"(?:Area|면적)\s*\(m\s*[²2]\);\s*([0-9.]+)",
        "평균속력": r"(?:Mean Speed|평균유속)\s*\(m/s\);\s*([0-9.]+)",
        "평균깊이": r"(?:Mean Depth|평균 깊이|Mean Depth)[\s\(]*m*\)*;\s*([0-9.]+)",
        "총 Q": r"(?:Total Q|전체 Q)\s*\(m\s*[³3]/s\);\s*([0-9.]+)",
        "시리얼번호": r"(?:Serial Number|시리얼 번호);\s*(.*)",
        "변환기 깊이": r"(?:Transducer Depth|센서부 깊이)\s*\(m\);\s*([0-9.]+)",
        "최대 깊이": r"(?:Maximum Depth|최대 깊이|Maximum Depth)[\s\(]*m*\)*;\s*([0-9.]+)",
        "최대 스피드": r"(?:Maximum Speed|최대 스피드|Maximum Speed)[\s\(]*(?:m/s)*\)*;\s*([0-9.]+)",
        "자기편차": r"(?:Magnetic Declination|자기 편차)\s*\(deg\);\s*([0-9.-]+)",
        "작업자": r"(?:Party|측정자);\s*(.*)",
        "위치": r"(?:Location|위치);\s*(.*)",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, file_content)
        if match:
            val = match.group(1).strip()
            # 소수점 반올림 및 문자열 처리
            if key == "총 Q":
                data[key] = f"{float(val):.3f}"
            elif key in ["평균속력", "평균깊이", "폭", "면적"]:
                data[key] = f"{float(val):.2f}"
            elif key == "시리얼번호" and "RS5" in val:
                num_part = val.replace("RS5", "").strip()
                data[key] = f"RS5({num_part})"
            else:
                data[key] = val

    # 수위 (Gauge Height) 3칸 동일 적용 로직
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

    # Transect 테이블 분석 (언어 감지 및 인덱스 동적 할당)
    in_table = False
    transects = []
    is_korean = False
    
    for line in file_content.split('\n'):
        if line.startswith("Transect\tFile Name"):
            in_table = True
            is_korean = False
            continue
        elif line.startswith("횡단면\t파일이름"):
            in_table = True
            is_korean = True
            continue
            
        if in_table:
            parts = line.split('\t')
            if len(parts) > 10 and parts[0].strip().isdigit():
                transects.append(parts)

    if transects:
        data["측정 횟수(Tr)"] = str(len(transects))
        try:
            # 한글/영문 폼에 따른 열(Column) 번호 할당
            if is_korean:
                idx_start, idx_dur = 4, 5
                idx_track, idx_boat, idx_pct = 7, 11, 20
            else:
                idx_start, idx_dur = 3, 4
                idx_track, idx_boat, idx_pct = 5, 9, 18

            # 측정시간(hh:mm 범위) 계산
            first_start_time = transects[0][idx_start]
            last_start_time = transects[-1][idx_start]
            last_duration = transects[-1][idx_dur]
            data["측정시간"] = format_measurement_time(first_start_time, last_start_time, last_duration)

            # 합계 계산
            track_sum = sum(float(t[idx_track]) for t in transects if t[idx_track].strip())
            boat_spd_sum = sum(float(t[idx_boat]) for t in transects if t[idx_boat].strip())
            
            pct_meas_sum = 0
            pct_count = 0
            for t in transects:
                if len(t) > idx_pct and t[idx_pct].strip() and t[idx_pct].strip() != '--':
                    pct_meas_sum += float(t[idx_pct].strip())
                    pct_count += 1
            
            # 평균 할당
            data["트랙거리(mean)"] = f"{track_sum / len(transects):.2f}"
            data["보트속력(mean)"] = f"{boat_spd_sum / len(transects):.2f}"
            if pct_count > 0:
                data["측정된 %(mean)"] = f"{pct_meas_sum / pct_count:.2f}"
            
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
    default_name = f"{today_str}_"
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
    st.warning("🚨 **수위를 입력해주세요!** 추출 결과는 아래 표에서 엑셀처럼 더블클릭하여 직접 수정이 가능합니다.")
    st.data_editor(df, use_container_width=True)