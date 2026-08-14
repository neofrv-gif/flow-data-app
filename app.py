import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime, timedelta, date, time
import pytz

st.set_page_config(page_title="유량 데이터 추출기", layout="wide")
st.title("🌊 유량 데이터 추출(.dis 전용)")
st.info("💡 .dis 파일을 드래그 앤 드롭하면 즉시 엑셀 데이터 추출이 진행됩니다. by KJH")

# 데이터 및 초기화 키 세션 상태
if "flow_data" not in st.session_state:
    st.session_state.flow_data = []
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

def format_measurement_time(first_start_time, last_start_time, last_duration):
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
        start_dt = to_datetime(first_start_time)
        logical_start_dt = start_dt - timedelta(minutes=10)
        logical_start_min = (logical_start_dt.minute // 10) * 10
        logical_start_dt = logical_start_dt.replace(minute=logical_start_min, second=0)
        
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
    # 컬럼 설정 (비고, 컴파스 오차 추가)
    columns = [
        "파일명", "사이트 이름", "측정 날짜", "측정시간", "날씨", 
        "시작수위", "종료수위", "평균수위", "폭", "면적", 
        "평균속력", "평균깊이", "총 Q", "시리얼번호", "측정 횟수(Tr)", 
        "변환기 깊이", "최대 깊이", "최대 스피드", "자기편차", 
        "측정된 %(mean)", "보트속력(mean)", "트랙거리(mean)", 
        "작업자", "위치", "비고", "컴파스 오차(deg)"
    ]
    
    data = {col: "-" for col in columns}
    data["파일명"] = filename
    data["날씨"] = ""
    data["비고"] = ""

    # 시스템 타입 사전 추출 (시리얼번호 M9 판별용)
    sys_type_match = re.search(r"(?:System Type|시스템 타입);\s*(.*)", file_content)
    sys_type_val = sys_type_match.group(1).upper() if sys_type_match else ""

    # 정규식 매핑
    patterns = {
        "사이트 이름": r"(?:Site Name|사이트 이름);\s*(.*)",
        "측정 날짜": r"(?:Date Measured|생성 날짜):\s*([0-9-]+)",
        "날씨": r"(?:Comments|사이트 설명);[ \t]*([^\n\r]*)", 
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
            if key == "총 Q" and val:
                data[key] = f"{float(val):.3f}"
            elif key in ["평균속력", "평균깊이", "폭", "면적"] and val:
                data[key] = f"{float(val):.2f}"
            elif key == "시리얼번호":
                # RS5 감지 (시리얼번호나 시스템타입에 포함된 경우)
                if "RS5" in val.upper() or "RS5" in sys_type_val:
                    num_part = re.sub(r'(?i)RS5', '', val).strip()
                    data[key] = f"RS5({num_part})"
                # M9 감지 (시리얼번호나 시스템타입에 포함된 경우)
                elif "M9" in val.upper() or "M9" in sys_type_val:
                    num_part = re.sub(r'(?i)M9', '', val).strip()
                    data[key] = f"M9({num_part})"
                else:
                    data[key] = val
            else:
                data[key] = val

    # 수위
    gauge_val = "-"
    g_match_supp = re.search(r"Start Gauge Height[^\n]*\n+(\d+\s*;\s*[^;]+\s*;\s*([0-9.]+)\s*;)", file_content)
    if g_match_supp:
        gauge_val = g_match_supp.group(2).strip()
    else:
        g_match_gen = re.search(r"Gauge Height.*?[;:]\s*([0-9.]+)", file_content, re.IGNORECASE)
        if g_match_gen:
            gauge_val = g_match_gen.group(1).strip()
    if gauge_val != "-":
        data["시작수위"] = data["종료수위"] = data["평균수위"] = gauge_val

    # 컴파스 오차 추출
    comp_match = re.search(r"(?:Heading Error|헤딩 에러)[^\d]*([0-9.]+)", file_content)
    if comp_match:
        data["컴파스 오차(deg)"] = comp_match.group(1).strip()
        
    # 시스템 테스트 추출 및 비고란 알림
    sys_match = re.search(r"(?:System Test|시스템 테스트)\s*[:;]\s*(.*)", file_content)
    if sys_match:
        sys_val = sys_match.group(1).strip()
        if sys_val.lower() not in ["성공", "pass", "passed"]:
            data["비고"] = f"🚨테스트 오류: {sys_val}"

    # Transect 테이블 분석
    in_table = False
    transects = []
    is_korean = False
    for line in file_content.split('\n'):
        if line.startswith("Transect\tFile Name"):
            in_table = True; is_korean = False; continue
        elif line.startswith("횡단면\t파일이름"):
            in_table = True; is_korean = True; continue
        if in_table:
            parts = line.split('\t')
            if len(parts) > 10 and parts[0].strip().isdigit():
                transects.append(parts)

    if transects:
        data["측정 횟수(Tr)"] = str(len(transects))
        try:
            if is_korean:
                idx_start, idx_dur = 4, 5
                idx_track, idx_width, idx_area, idx_boat, idx_pct = 7, 9, 10, 11, 20
            else:
                idx_start, idx_dur = 3, 4
                idx_track, idx_width, idx_area, idx_boat, idx_pct = 5, 7, 8, 9, 18

            data["측정시간"] = format_measurement_time(transects[0][idx_start], transects[-1][idx_start], transects[-1][idx_dur])

            # 편차 계산을 위한 리스트 수집
            tracks, widths, areas, depths = [], [], [], []
            track_sum = boat_spd_sum = pct_meas_sum = pct_count = 0
            
            for t in transects:
                tr_val = float(t[idx_track]) if t[idx_track].strip() else 0
                w_val = float(t[idx_width]) if t[idx_width].strip() else 0
                a_val = float(t[idx_area]) if t[idx_area].strip() else 0
                
                track_sum += tr_val
                boat_spd_sum += float(t[idx_boat]) if t[idx_boat].strip() else 0
                
                if len(t) > idx_pct and t[idx_pct].strip() and t[idx_pct].strip() != '--':
                    pct_meas_sum += float(t[idx_pct].strip())
                    pct_count += 1
                    
                tracks.append(tr_val)
                widths.append(w_val)
                areas.append(a_val)
                if w_val > 0: depths.append(a_val / w_val)

            data["트랙거리(mean)"] = f"{track_sum / len(transects):.2f}"
            data["보트속력(mean)"] = f"{boat_spd_sum / len(transects):.2f}"
            if pct_count > 0:
                data["측정된 %(mean)"] = f"{pct_meas_sum / pct_count:.2f}"

            # 편차율 계산 함수 ((Max - Mean) / Mean * 100)
            def get_max_dev(lst):
                if not lst or sum(lst) == 0: return 0
                mean_v = sum(lst) / len(lst)
                if mean_v == 0: return 0
                return max(abs(x - mean_v) for x in lst) / mean_v * 100

            # 백그라운드 색칠을 위한 숨겨진 데이터 저장
            data["_dev_트랙"] = get_max_dev(tracks)
            data["_dev_폭"] = get_max_dev(widths)
            data["_dev_면적"] = get_max_dev(areas)
            data["_dev_깊이"] = get_max_dev(depths)
            
        except Exception:
            pass

    return data

# DataFrame 스타일 지정 함수
def style_dataframe(row):
    styles = [''] * len(row)
    cols = row.index.tolist()
    
    # 1. 측정된 % 경고 (50미만 빨강, 60미만 노랑)
    if "측정된 %(mean)" in cols:
        idx = cols.index("측정된 %(mean)")
        val = row["측정된 %(mean)"]
        if val != "-":
            v = float(val)
            if v < 50: styles[idx] = 'background-color: #ffcccc; color: #900;'
            elif v < 60: styles[idx] = 'background-color: #fff3cd; color: #856404;'
                
    # 2. TR 편차 경고 (20%이상 빨강, 10%이상 노랑)
    metrics = {"폭": "_dev_폭", "면적": "_dev_면적", "평균깊이": "_dev_깊이", "트랙거리(mean)": "_dev_트랙"}
    for col_name, dev_key in metrics.items():
        if col_name in cols and dev_key in cols:
            idx = cols.index(col_name)
            dev_val = row[dev_key]
            if pd.notna(dev_val) and dev_val != "-":
                d = float(dev_val)
                if d >= 20: styles[idx] = 'background-color: #ffcccc; color: #900;'
                elif d >= 10: styles[idx] = 'background-color: #fff3cd; color: #856404;'
                    
    # 3. 시스템 테스트 실패 경고
    if "비고" in cols:
        idx = cols.index("비고")
        if "테스트 오류" in str(row["비고"]):
            styles[idx] = 'background-color: #ffcccc; color: #900; font-weight: bold;'
            
    return styles

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
    
    # 엑셀 다운로드용 순수 데이터프레임 (숨김 계산용 컬럼 제거)
    export_df = df.drop(columns=[col for col in df.columns if col.startswith('_')])
    
    st.markdown("### 💾 저장 설정")
    kst = pytz.timezone('Asia/Seoul')
    today_str = datetime.now(kst).strftime("%y%m%d")
    default_name = f"{today_str}_"
    custom_filename = st.text_input("저장할 파일 이름을 입력하세요", value=default_name)
    
    col1, col2, col3 = st.columns(3)
    csv_bytes = export_df.to_csv(index=False).encode('utf-8-sig')
    with col1:
        st.download_button(label="📥 CSV 다운로드", data=csv_bytes, file_name=f"{custom_filename}.csv", mime="text/csv", use_container_width=True)
        
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        export_df.to_excel(writer, index=False, sheet_name='수문유량결과')
    with col2:
        st.download_button(label="📊 Excel 다운로드", data=output.getvalue(), file_name=f"{custom_filename}.xlsx", mime="application/vnd.ms-excel", use_container_width=True)

    with col3:
        if st.button("🔄 전체 데이터 초기화", type="primary", use_container_width=True):
            st.session_state.flow_data = []
            st.session_state.uploader_key += 1
            st.rerun()

    st.markdown("---")
    st.warning("🚨 **수위를 입력해주세요!** 엑셀처럼 직접 수정이 가능하며, 🔴빨간색/🟡노란색 셀은 편차가 크거나 확인이 필요한 데이터입니다.")
    
    # 스타일 적용 및 숨김 컬럼 지정 후 출력
    styled_df = df.style.apply(style_dataframe, axis=1)
    hidden_cols = {col: None for col in df.columns if col.startswith('_')}
    
    st.data_editor(styled_df, column_config=hidden_cols, use_container_width=True)