# main.py
from pathlib import Path
from io import BytesIO

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ----------------------------- 경로 설정 (상대 경로) -----------------------------
BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "out"

SUPPLY_CSV = OUT_DIR / "용도별_수요가수_공급량_(2001-현재).csv"
PIPE_CSV   = OUT_DIR / "배관실적_tidy_all.csv"

# ----------------------------- 기본 페이지 설정 -----------------------------
st.set_page_config(page_title="전국 도시가스 효율성 지표 추이", layout="wide")

st.title("전국 도시가스 효율성 지표 추이")
st.caption("전국 도시가스 데이터 · 수요·공급·배관길이 효율성 분석")

st.divider()

# ----------------------------- 데이터/사용 방법 설명 (토글) -----------------------------
with st.expander("📘 사용 설명서 / 데이터 안내", expanded=False):
    st.markdown(
        """
### 📘 데이터 설명

- **자료 출처**: 한국도시가스협회 통계  
  👉 [한국도시가스협회 통계 바로가기](http://www.citygas.or.kr/info/stats/index.jsp?sbranch_fk=2)
- **수요가수**: 실제로 **요금이 청구된 계량기** 수 (실제 사용 중인 계량기 수)
- **배관길이**: **공급관 + 본관**을 모두 포함한 전체 배관 길이
- **공급량**: 여기서는 **판매량**과 동일한 개념으로 보시면 됩니다.  
  (내부 데이터는 m³ 기준으로 변환해서 활용합니다.)

---

### 🧭 화면 사용 방법

1. **그룹 기준 선택**
   - `회사`를 선택하면 **회사 단위**로 집계/표시됩니다.  
     → 이때 그래프에서는 **'대성' 회사 라인**이 자동으로 **굵게 강조**됩니다.
   - `지역(시도)`를 선택하면 **시도 단위**로 집계/표시됩니다.  
     → 이때 그래프에서는 **'대구' 지역 라인**이 자동으로 **굵게 강조**됩니다.

2. **상품 선택 (멀티 선택)**
   - 선택한 상품 조합은 **수요가수**, **공급량(m³)** 집계에만 영향을 줍니다.
   - **배관길이(m)**는 실제 깔린 배관 길이이기 때문에,  
     **상품 선택과는 무관하게** 회사/지역·연도에 따라 그대로 유지됩니다.

3. **회사 / 지역(시도) 필터**
   - `그룹 기준 = 회사` 인 경우  
     → **회사만 필터**할 수 있고, 지역은 **전체**가 사용됩니다.
   - `그룹 기준 = 지역(시도)` 인 경우  
     → **지역(시도)만 필터**할 수 있고, 회사는 **전체**가 사용됩니다.
   - 이렇게 해서 회사/지역 필터가 섞이지 않도록 해 혼란을 줄였습니다.

4. **공급량 단위 선택**
   - 사이드바에서 **`m³` / `천 m³`** 중 하나를 선택할 수 있습니다.
   - 단위 선택은 **공급량·공급량/수요가수·공급량/배관길이 그래프에만** 적용됩니다.  
     (다운로드 엑셀 데이터는 m³ 기준으로 유지)

---

아래 6개 그래프는 다음 내용을 보여줍니다:

1. **수요가수 추이**
2. **공급량 추이** (단위: m³ 또는 천 m³)
3. **배관길이 추이**
4. **공급량 / 수요가수** (단위: m³/계좌 또는 천 m³/계좌)
5. **공급량 / 배관길이** (단위: m³/m 또는 천 m³/m)
6. **수요가수 / 배관길이** (단위: 계좌/m)
        """
    )

# ----------------------------- 유틸 함수 -----------------------------
def normalize_company(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
         .str.replace(r"\s+", "", regex=True)
         .replace({"대구": "대성", "충남": "CNCITY"})
    )

def normalize_region(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip()

@st.cache_data(ttl=3600)
def load_supply(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")

    # 용도 → 상품
    if "상품" not in df.columns and "용도" in df.columns:
        df = df.rename(columns={"용도": "상품"})

    df["연도"]    = pd.to_numeric(df["연도"], errors="coerce").astype("Int64")
    df["수요가수"] = pd.to_numeric(df["수요가수"], errors="coerce")
    df["공급량"]  = pd.to_numeric(df["공급량"],  errors="coerce")  # 단위: 천 m³
    df["회사"]    = normalize_company(df["회사"])

    # 시도 컬럼 추론
    region_col = None
    for cand in ["시도", "시도명", "지역"]:
        if cand in df.columns:
            region_col = cand
            break
    if region_col:
        df["시도"] = normalize_region(df[region_col])
    else:
        df["시도"] = pd.NA

    if "상품" not in df.columns:
        df["상품"] = "미상"

    df = df.dropna(subset=["연도", "회사"])
    df["공급량(m3)"] = df["공급량"] * 1000.0  # m³로 변환

    return df[["연도", "회사", "시도", "상품", "수요가수", "공급량(m3)"]]

@st.cache_data(ttl=3600)
def load_pipe(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["연도"] = pd.to_numeric(df["연도"], errors="coerce").astype("Int64")
    df["길이"] = pd.to_numeric(df["길이"], errors="coerce")
    df["회사"] = normalize_company(df["회사"])
    if "시도" in df.columns:
        df["시도"] = normalize_region(df["시도"])
    else:
        df["시도"] = pd.NA

    df = df.dropna(subset=["연도", "회사", "길이"])
    g = (
        df.groupby(["연도", "회사", "시도"], as_index=False)["길이"]
          .sum()
          .rename(columns={"길이": "배관길이(m)"})
    )
    return g

def make_excel_bytes(df: pd.DataFrame, dim_col: str) -> bytes:
    """
    각 그래프용 데이터를 시트별로 넣어서 엑셀로 반환
    시트:
      01_수요가수
      02_공급량_m3
      03_배관길이_m
      04_공급량_수요가수비
      05_공급량_배관길이비
      06_수요가수_배관길이비
    """
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        cols_base = ["연도", dim_col]

        sheets = {
            "01_수요가수"            : cols_base + ["수요가수"],
            "02_공급량_m3"          : cols_base + ["공급량(m3)"],
            "03_배관길이_m"         : cols_base + ["배관길이(m)"],
            "04_공급량_수요가수비"  : cols_base + ["공급량/수요가수"],
            "05_공급량_배관길이비" : cols_base + ["공급량/배관길이"],
            "06_수요가수_배관길이비": cols_base + ["수요가수/배관길이"],
        }

        for sheet_name, cols in sheets.items():
            use_cols = [c for c in cols if c in df.columns]
            tmp = df.loc[:, use_cols].copy()
            tmp.to_excel(writer, index=False, sheet_name=sheet_name)

    buf.seek(0)
    return buf.getvalue()

# ----------------------------- 데이터 로드 -----------------------------
supply = load_supply(SUPPLY_CSV)   # 연도, 회사, 시도, 상품, 수요가수, 공급량(m3)
pipe   = load_pipe(PIPE_CSV)       # 연도, 회사, 시도, 배관길이(m)

# 전체 회사/지역 목록 (필터용 준비)
all_companies = sorted(
    normalize_company(supply["회사"]).dropna().unique().tolist()
)
all_regions = sorted(
    normalize_region(supply["시도"]).dropna().unique().tolist()
)
prod_all = sorted(supply["상품"].dropna().unique().tolist())

# ----------------------------- 사이드바 (필터 순서 정리) -----------------------------
st.sidebar.header("기본 설정")

# 1) 그룹 기준
group_by = st.sidebar.radio(
    "그룹 기준",
    ["회사", "지역(시도)"],
    index=0,
    key="group_by"
)

# 2) 공급량 단위
supply_unit = st.sidebar.radio(
    "공급량 단위",
    ["m³", "천 m³"],
    index=0,
    key="supply_unit"
)

# 3) 연도 범위 — 기본 2001년부터
year_min = int(pd.concat([supply["연도"], pipe["연도"]]).min())
year_max = int(pd.concat([supply["연도"], pipe["연도"]]).max())
default_start = max(2001, year_min)
years = st.sidebar.slider(
    "연도 범위",
    year_min, year_max,
    (default_start, year_max),
    key="years"
)

# 4) 회사 또는 지역 필터 (배타적으로 동작)
if group_by == "회사":
    preferred_companies = ["서울", "삼천리", "대성", "해양", "CNCITY", "부산", "인천"]
    default_companies = [c for c in preferred_companies if c in all_companies]
    if not default_companies:
        default_companies = all_companies[:10]

    sel_companies = st.sidebar.multiselect(
        "회사 선택 (필터용, 여러 개)",
        options=all_companies,
        default=default_companies,
        key="sel_companies"
    )
    if not sel_companies:
        sel_companies = all_companies

    sel_regions = all_regions  # 지역은 전체
    st.sidebar.caption("※ 현재 그룹 기준이 '회사'이므로 지역(시도) 필터는 전체가 사용됩니다.")
else:
    preferred_regions = ["서울", "대구", "대전", "부산", "광주", "울산", "인천"]
    default_regions = [r for r in preferred_regions if r in all_regions]
    if not default_regions:
        default_regions = all_regions

    sel_regions = st.sidebar.multiselect(
        "지역(시도) 선택 (필터용, 여러 개)",
        options=all_regions,
        default=default_regions,
        key="sel_regions"
    )
    if not sel_regions:
        sel_regions = all_regions

    sel_companies = all_companies  # 회사는 전체
    st.sidebar.caption("※ 현재 그룹 기준이 '지역(시도)'이므로 회사 필터는 전체가 사용됩니다.")

# 5) 상품 멀티셀렉트 (맨 마지막)
sel_products = st.sidebar.multiselect(
    "상품 선택 (여러 개)",
    options=prod_all,
    default=prod_all,
    key="sel_products"
)
if not sel_products:
    st.warning("최소 1개 이상의 상품을 선택해주세요.")
    st.stop()

# 추가: 차트 높이
chart_height = st.sidebar.slider(
    "그래프 높이(px)",
    min_value=300,
    max_value=900,
    value=450,
    step=50,
    key="chart_h"
)

# ----------------------------- 데이터 전처리 & 집계 -----------------------------
# 1) supply: 상품/연도/회사/시도 필터 후 집계
sup_f = supply[
    (supply["상품"].isin(sel_products)) &

    (supply["연도"] >= years[0]) &
    (supply["연도"] <= years[1]) &
    (supply["회사"].isin(sel_companies)) &
    (supply["시도"].isin(sel_regions))
].copy()

sup_agg = (
    sup_f.groupby(["연도", "회사", "시도"], as_index=False)
          .agg(수요가수=("수요가수", "sum"),
               공급량_m3=("공급량(m3)", "sum"))
          .rename(columns={"공급량_m3": "공급량(m3)"})
)

# 2) pipe: 상품 영향 없음, 연도/회사/지역만 필터
pipe_f = pipe[
    (pipe["연도"] >= years[0]) &
    (pipe["연도"] <= years[1]) &
    (pipe["회사"].isin(sel_companies)) &
    (pipe["시도"].isin(sel_regions))
].copy()

# 3) supply & pipe 병합
base = pd.merge(
    sup_agg,
    pipe_f,
    on=["연도", "회사", "시도"],
    how="outer"
)

if base.empty:
    st.info("선택된 조건에 해당하는 데이터가 없습니다.")
    st.stop()

# ----------------------------- 그룹 기준에 따른 집계 -----------------------------
if group_by == "회사":
    dim_col = "회사"
    grouped = (
        base.groupby(["연도", "회사"], as_index=False)
            .agg(
                수요가수=("수요가수", "sum"),
                공급량_m3=("공급량(m3)", "sum"),
                배관길이_m=("배관길이(m)", "sum"),
            )
            .rename(columns={"공급량_m3": "공급량(m3)", "배관길이_m": "배관길이(m)"})
    )
else:
    dim_col = "지역(시도)"
    grouped = (
        base.groupby(["연도", "시도"], as_index=False)
            .agg(
                수요가수=("수요가수", "sum"),
                공급량_m3=("공급량(m3)", "sum"),
                배관길이_m=("배관길이(m)", "sum"),
            )
            .rename(columns={
                "시도": "지역(시도)",
                "공급량_m3": "공급량(m3)",
                "배관길이_m": "배관길이(m)",
            })
    )

# 비율 계산
den_demand = grouped["수요가수"].replace(0, np.nan)
den_length = grouped["배관길이(m)"].replace(0, np.nan)

grouped["공급량/수요가수"]   = grouped["공급량(m3)"] / den_demand
grouped["공급량/배관길이"]   = grouped["공급량(m3)"] / den_length
grouped["수요가수/배관길이"] = grouped["수요가수"]     / den_length

# 단위에 따른 표시 컬럼
if supply_unit == "m³":
    grouped["공급량_표시"] = grouped["공급량(m3)"]
    grouped["공급량/수요가수_표시"] = grouped["공급량/수요가수"]
    grouped["공급량/배관길이_표시"] = grouped["공급량/배관길이"]
    sup_label    = "공급량 (m³)"
    ratio1_label = "공급량 / 수요가수 (m³/계좌)"
    ratio2_label = "공급량 / 배관길이 (m³/m)"
else:
    grouped["공급량_표시"] = grouped["공급량(m3)"] / 1000.0
    grouped["공급량/수요가수_표시"] = grouped["공급량/수요가수"] / 1000.0
    grouped["공급량/배관길이_표시"] = grouped["공급량/배관길이"] / 1000.0
    sup_label    = "공급량 (천 m³)"
    ratio1_label = "공급량 / 수요가수 (천 m³/계좌)"
    ratio2_label = "공급량 / 배관길이 (천 m³/m)"

grouped = grouped.sort_values(["연도", dim_col])

picked_label = "전체" if set(sel_products) == set(prod_all) else ", ".join(sel_products)
st.markdown(f"**선택 상품:** {picked_label}")
st.markdown(f"**그룹 기준:** {group_by} / **축 컬럼:** `{dim_col}`")
st.markdown(f"**공급량 단위:** {supply_unit}")

# ----------------------------- 6개 그래프 (3 x 2 배치) -----------------------------
def line_chart(df: pd.DataFrame, y_col: str, title: str, y_label: str, container):
    fig = px.line(
        df,
        x="연도",
        y=y_col,
        color=dim_col,
        markers=True,
        render_mode="svg",
    )

    # 기본 하이라이트: 회사 → 대성, 지역 → 대구
    for tr in fig.data:
        if group_by == "회사" and tr.name == "대성":
            tr.update(line=dict(width=5))
            tr.update(marker=dict(size=9))
        elif group_by.startswith("지역") and tr.name == "대구":
            tr.update(line=dict(width=5))
            tr.update(marker=dict(size=9))
        else:
            tr.update(line=dict(width=2))
            tr.update(marker=dict(size=6))

    fig.update_layout(
        height=chart_height,
        yaxis_title=y_label,
        legend_title=dim_col,
        hovermode="x unified",
        margin=dict(l=10, r=10, t=40, b=10),
    )
    fig.update_yaxes(tickformat=",")  # 쉼표 포맷
    with container:
        st.subheader(title)
        st.plotly_chart(fig, use_container_width=True)

# 1,2
col1, col2 = st.columns(2)
line_chart(grouped, "수요가수",                "1) 수요가수 추이",           "수요가수 (계좌 수)",          col1)
line_chart(grouped, "공급량_표시",            "2) 공급량 추이",             sup_label,                    col2)

# 3,4
col3, col4 = st.columns(2)
line_chart(grouped, "배관길이(m)",            "3) 배관길이 추이",           "배관길이 (m)",                col3)
line_chart(grouped, "공급량/수요가수_표시",   "4) 공급량 / 수요가수",       ratio1_label,                 col4)

# 5,6
col5, col6 = st.columns(2)
line_chart(grouped, "공급량/배관길이_표시",   "5) 공급량 / 배관길이",       ratio2_label,                 col5)
line_chart(grouped, "수요가수/배관길이",      "6) 수요가수 / 배관길이",      "수요가수 / 배관길이 (계좌/m)", col6)

# ----------------------------- 집계 데이터 & 엑셀 다운로드 -----------------------------
st.markdown("---")
st.markdown("### 📊 집계 데이터 & 엑셀 다운로드")

with st.expander("집계 데이터 보기 (토글)", expanded=False):
    st.dataframe(grouped, use_container_width=True)

excel_bytes = make_excel_bytes(grouped, dim_col)

st.download_button(
    "엑셀 다운로드 (그래프별 시트 포함)",
    data=excel_bytes,
    file_name=f"수요공급배관_대시보드_{group_by}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.caption(
    "※ 시트별 구성: "
    "01_수요가수, 02_공급량_m3, 03_배관길이_m, "
    "04_공급량_수요가수비, 05_공급량_배관길이비, 06_수요가수_배관길이비"
)

st.divider()
st.caption("※ 로컬 실행: 프로젝트 루트에서 `streamlit run main.py`")
