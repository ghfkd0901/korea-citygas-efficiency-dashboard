# app_supply_per_length.py
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ---- 파일 경로 ----
SUPPLY_CSV = Path(r"D:\Project\전국도시가스용도별수요가수공급량\out\용도별_수요가수_공급량_(2001-현재).csv")
PIPE_CSV   = Path(r"D:\Project\전국도시가스용도별수요가수공급량\out\배관실적_tidy_all.csv")

st.set_page_config(page_title="회사/지역별 길이당 공급량", layout="wide")
st.title("연간 길이당 공급량 (공급량 ÷ 배관길이) — 회사/지역 전환")

# ---- 유틸 ----
def normalize_company(s: pd.Series) -> pd.Series:
    # 공백 제거 후 표준화
    return (
        s.astype(str).str.replace(r"\s+", "", regex=True)
         .replace({"대구": "대성", "충남": "CNCITY"})
    )

def normalize_region(s: pd.Series) -> pd.Series:
    # 시도 표기 단순 정리(필요시 매핑 추가)
    return s.astype(str).str.strip()

@st.cache_data(ttl=3600)
def load_supply(path: Path) -> pd.DataFrame:
    # 예상 주요 컬럼: 연도, 회사, (선택적) 시도/시도명/지역, 공급량(천 m³), 용도
    df = pd.read_csv(path, encoding="utf-8-sig")

    # 용도 → 상품 이름 통일
    if "상품" not in df.columns and "용도" in df.columns:
        df = df.rename(columns={"용도": "상품"})

    # 기본 컬럼들 전처리
    df["연도"] = pd.to_numeric(df["연도"], errors="coerce").astype("Int64")
    df["공급량"] = pd.to_numeric(df["공급량"], errors="coerce")   # 단위: 천 m³
    df["회사"] = normalize_company(df["회사"])

    # 시도 컬럼 유추
    region_col = None
    for cand in ["시도", "시도명", "지역"]:
        if cand in df.columns:
            region_col = cand
            break
    if region_col:
        df["시도"] = normalize_region(df[region_col])
    else:
        df["시도"] = pd.NA

    # 상품 컬럼 없으면 임시 이름
    if "상품" not in df.columns:
        df["상품"] = "미상"

    df = df.dropna(subset=["연도", "회사", "공급량"])
    # 천 m³ → m³
    df["공급량(m3)"] = df["공급량"] * 1000.0

    # 아직 집계하지 않고 상품 단위까지 유지해서 반환
    return df[["연도", "회사", "시도", "상품", "공급량(m3)"]]

@st.cache_data(ttl=3600)
def load_pipe(path: Path) -> pd.DataFrame:
    # 컬럼: 연도, 시도, 회사, 구분, 길이
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["연도"] = pd.to_numeric(df["연도"], errors="coerce").astype("Int64")
    df["길이"] = pd.to_numeric(df["길이"], errors="coerce")
    df["회사"] = normalize_company(df["회사"])
    if "시도" not in df.columns:
        df["시도"] = pd.NA
    else:
        df["시도"] = normalize_region(df["시도"])
    df = df.dropna(subset=["연도", "회사", "길이"])
    # 회사·연도·(시도) 기준 배관 총 길이(본관+공급관 합)
    g = df.groupby(["연도", "회사", "시도"], as_index=False)["길이"].sum()
    g = g.rename(columns={"길이": "배관길이(m)"})
    return g

# ---- 데이터 준비 ----
supply = load_supply(SUPPLY_CSV)   # 연도, 회사, 시도, 상품, 공급량(m3)
pipe   = load_pipe(PIPE_CSV)       # 연도, 회사, 시도, 배관길이(m)

# ---- 사이드바: 기본 필터 ----
st.sidebar.header("필터")

group_by = st.sidebar.radio(
    "그룹 기준",
    ["회사", "지역(시도)"],
    index=0,
    key="group_by"
)

# ✅ 상품 전체 선택 옵션 + 일부 선택
product_all = sorted(supply["상품"].dropna().unique().tolist())

select_all_products = st.sidebar.checkbox(
    "상품 전체 선택",
    value=True,
    key="product_select_all"
)

if select_all_products:
    sel_products = product_all  # 전체 선택
else:
    sel_products = st.sidebar.multiselect(
        "상품 선택 (여러 개)",
        options=product_all,
        default=product_all,   # 기본은 전체 선택 상태에서 시작
        key="sel_products"
    )

if not sel_products:
    st.warning("최소 1개 이상의 상품을 선택해주세요.")
    st.stop()

# 선택한 상품만 남기기
supply_filtered = supply[supply["상품"].isin(sel_products)].copy()

if supply_filtered.empty:
    st.info("선택한 상품에 해당하는 공급 데이터가 없습니다.")
    st.stop()

# ---- 연도 범위 ----
year_min = int(pd.concat([supply_filtered["연도"], pipe["연도"]]).min())
year_max = int(pd.concat([supply_filtered["연도"], pipe["연도"]]).max())
default_start = max(2010, year_min)
years = st.sidebar.slider(
    "연도 범위",
    year_min, year_max,
    (default_start, year_max),
    key="years"
)

# ---- 병합 로직 (회사 기준 vs 지역 기준) ----
if group_by == "회사":
    # 회사·연도 기준으로 집계 후 병합 (선택한 상품만 반영)
    sup_g = supply_filtered.groupby(["연도", "회사"], as_index=False)["공급량(m3)"].sum()
    pip_g = pipe.groupby(["연도", "회사"], as_index=False)["배관길이(m)"].sum()
    merged = pd.merge(sup_g, pip_g, on=["연도", "회사"], how="inner")
    dim_col = "회사"
    emph_value = "대성"
    # 기본 선택: 메이저 + 데이터 상위
    dim_all = sorted(merged[dim_col].unique().tolist())
    default_dim = [c for c in ["서울", "삼천리", "대성", "해양", "CNCITY", "부산", "인천"] if c in dim_all]
    if not default_dim and len(dim_all) > 0:
        default_dim = (
            merged.groupby(dim_col)["공급량(m3)"]
                  .sum()
                  .sort_values(ascending=False)
                  .head(10)
                  .index
                  .tolist()
        )
else:
    # 지역·연도 기준으로 집계 후 병합 (두 데이터 모두 시도 있어야 함)
    if supply_filtered["시도"].isna().all() or pipe["시도"].isna().all():
        st.error("지역(시도) 정보가 공급/배관 데이터에 없어 지역 기준 보기가 불가합니다. (공급 또는 배관 CSV에 '시도' 컬럼 필요)")
        st.stop()
    sup_g = supply_filtered.groupby(["연도", "시도"], as_index=False)["공급량(m3)"].sum()
    pip_g = pipe.groupby(["연도", "시도"], as_index=False)["배관길이(m)"].sum()
    merged = pd.merge(sup_g, pip_g, on=["연도", "시도"], how="inner")
    merged = merged.rename(columns={"시도": "지역(시도)"})
    dim_col = "지역(시도)"
    emph_value = "대구"  # 선택적 강조 지역
    dim_all = sorted(merged[dim_col].unique().tolist())
    # 기본 선택: 상위 10개 지역
    if len(dim_all) > 0:
        default_dim = (
            merged.groupby(dim_col)["공급량(m3)"]
                  .sum()
                  .sort_values(ascending=False)
                  .head(10)
                  .index
                  .tolist()
        )
    else:
        default_dim = []

if merged.empty:
    st.info("선택한 상품/그룹 기준에 해당하는 집계 결과가 없습니다.")
    st.stop()

# ---- 길이당공급량 계산 ----
denom = merged["배관길이(m)"].replace(0, np.nan)
merged["길이당공급량(m3/m)"] = merged["공급량(m3)"] / denom

# ---- 연도 필터 적용 ----
merged = merged[(merged["연도"] >= years[0]) & (merged["연도"] <= years[1])].copy()

sel_dims = st.sidebar.multiselect(
    f"{group_by} 선택 (여러 개)",
    options=dim_all,
    default=default_dim if default_dim else dim_all[:10],
    key="sel_dims"
)

f = merged[merged[dim_col].isin(sel_dims)].copy().sort_values(["연도", dim_col])

# 선택한 상품 표시
st.caption("선택된 상품: " + ", ".join(sel_products))

# ---- 테이블 & 다운로드 ----
st.subheader("집계 테이블")
show = f[["연도", dim_col, "공급량(m3)", "배관길이(m)", "길이당공급량(m3/m)"]]
st.dataframe(show, use_container_width=True)
st.download_button(
    "CSV 다운로드 (집계)",
    data=show.to_csv(index=False, encoding="utf-8-sig"),
    file_name=f"{group_by}_길이당공급량_집계.csv",
    mime="text/csv",
    key="dl_summary"
)

# ---- 시각화 ----
if f.empty:
    st.info("선택된 조건에 해당하는 데이터가 없습니다.")
else:
    # 공통 차트 높이 슬라이더
    chart_h = st.sidebar.slider("차트 높이(px)", 480, 1400, 720, 40, key="chart_h")

    # 1) 길이당공급량 추이 (m³/m) — 꺾은선
    st.subheader(f"1) 길이당공급량 추이 (m³/m) — {group_by}별")
    fig1 = px.line(
        f, x="연도", y="길이당공급량(m3/m)", color=dim_col,
        markers=True, render_mode="svg"
    )
    for tr in fig1.data:
        tr.update(line=dict(width=5 if tr.name == emph_value else 2))
        tr.update(marker=dict(size=8 if tr.name == emph_value else 6))
    fig1.update_layout(
        height=chart_h,
        hovermode="x unified",
        yaxis_title="길이당공급량 (m³/m)",
        legend_title=group_by,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(fig1, use_container_width=True)

    # 2) 길이당공급량 피벗테이블 (행=연도, 열=회사/지역)
    st.subheader(f"2) 길이당공급량 피벗테이블 (행=연도, 열={group_by})")
    pivot = (
        f.pivot_table(
            index="연도",
            columns=dim_col,
            values="길이당공급량(m3/m)",
            aggfunc="mean"
        )
        .sort_index()
        .round(2)
    )
    ordered_cols = [c for c in sel_dims if c in pivot.columns]
    other_cols = [c for c in pivot.columns if c not in ordered_cols]
    pivot = pivot[ordered_cols + other_cols] if ordered_cols else pivot
    st.dataframe(pivot, use_container_width=True)
    st.download_button(
        "CSV 다운로드 (피벗: 길이당공급량)",
        data=pivot.reset_index().to_csv(index=False, encoding="utf-8-sig"),
        file_name=f"{group_by}_길이당공급량_피벗.csv",
        mime="text/csv",
        key="dl_pivot"
    )

    # 3) 배관 길이 추이 — 꺾은선
    st.subheader(f"3) 배관길이 추이 (m) — {group_by}별")
    fig_len = px.line(
        f, x="연도", y="배관길이(m)", color=dim_col,
        markers=True, render_mode="svg"
    )
    for tr in fig_len.data:
        tr.update(line=dict(width=5 if tr.name == emph_value else 2))
        tr.update(marker=dict(size=8 if tr.name == emph_value else 6))
    fig_len.update_layout(
        height=int(chart_h * 0.8),
        yaxis_title="배관길이 (m)",
        legend_title=group_by,
        hovermode="x unified",
        margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(fig_len, use_container_width=True)

    # 4) 공급량 추이 — 꺾은선
    st.subheader(f"4) 공급량 추이 (m³) — {group_by}별")
    fig_sup = px.line(
        f, x="연도", y="공급량(m3)", color=dim_col,
        markers=True, render_mode="svg"
    )
    for tr in fig_sup.data:
        tr.update(line=dict(width=5 if tr.name == emph_value else 2))
        tr.update(marker=dict(size=8 if tr.name == emph_value else 6))
    fig_sup.update_layout(
        height=int(chart_h * 0.8),
        yaxis_title="공급량 (m³)",
        legend_title=group_by,
        hovermode="x unified",
        margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(fig_sup, use_container_width=True)
