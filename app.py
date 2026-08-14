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

    sys_type_match = re.search(r"(?:System Type|시스템 타입);\s*(.*)", file_content)
    sys_type_val = sys_type_match.group(1).upper() if sys_type_match else ""

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
                if "RS5" in val.upper() or "RS5" in sys_type_val:
                    num_part = re.sub(r'(?i)RS5', '', val).strip()
                    data[key] = f"RS5({num_part})"
                elif "M9" in val.upper() or "M9" in sys_type_val:
                    num_part = re.sub(r'(?i)M9', '', val).strip()
                    data[key] = f"M9({num_part})"
                else:
                    data[key] = val
            else:
                data[key] = val

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

    comp_match = re.search(r"(?:Heading Error|헤딩 에러)[^\d]*([0-9.]+)", file_content)
    if comp_match:
        data["컴파스 오차(deg)"] = comp_match.group(1).strip()
        
    sys_match = re.search(r"(?:System Test|시스템 테스트)\s*[:;]\s*(.*)", file_content)
    if sys_match:
        sys_val = sys_match.group(1).strip()
        if sys_val.lower() not in ["성공", "pass", "passed"]:
            data["비고"] = f"🚨오류: {sys_val}"

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

            def get_max_dev(lst):
                if not lst or sum(lst) == 0: return 0
                mean_v = sum(lst) / len(lst)
                if mean_v == 0: return 0
                return max(abs(x - mean_v) for x in lst) / mean_v * 100

            # 🚨 문자열에 직접 기호를 삽입하는 방식으로 시각화 🚨
            def add_warning(val, dev):
                if dev >= 20: return f"🔴 {val}"
                elif dev >= 10: return f"🟡 {val}"
                return val

            data["트랙거리(mean)"] = add_warning(f"{track_sum / len(transects):.2f}", get_max_dev(tracks))
            data["폭"] = add_warning(data["폭"], get_max_dev(widths))
            data["면적"] = add_warning(data["면적"], get_max_dev(areas))
            data["평균깊이"] = add_warning(data["평균깊이"], get_max_dev(depths))
            data["보트속력(mean)"] = f"{boat_spd_sum / len(transects):.2f}"
            
            if pct_count > 0:
                pct_val = pct_meas_sum / pct_count
                if pct_val < 50:
                    data["측정된 %(mean)"] = f"🔴 {pct_val:.2f}"
                elif pct_val < 60:
                    data["측정된 %(mean)"] = f"🟡 {pct_val:.2f}"
                else:
                    data["측정된 %(mean)"] = f"{pct_val:.2f}"
            
        except Exception:
            pass

    return data

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
    kst = pytz.timezone('Asia/Seoul')
    today_str = datetime.now(kst).strftime("%y%m%d")
    default_name = f"{today_str}_"
    custom_filename = st.text_input("저장할 파일 이름을 입력하세요", value=default_name)
    
    col1, col2, col3 = st.columns(3)
    
    # 다운로드할 때는 경고 기호(🔴, 🟡)를 깔끔하게 제거하여 순수 숫자만 남김
    export_df = df.copy()
    for col in export_df.columns:
        if export_df[col].dtype == object:
            export_df[col] = export_df[col].apply(lambda x: str(x).replace("🔴 ", "").replace("🟡 ", "") if isinstance(x, str) else x)

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
    st.warning("🚨 **수위를 입력해주세요!** 표 안에서 직접 수정이 가능하며, 🔴(빨강)/🟡(노랑) 기호는 편차가 크거나 주의가 필요한 데이터입니다.")
    st.data_editor(df, use_container_width=True)