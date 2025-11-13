# app_company_per_unit_topn.py
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

CSV_PATH = Path(r"D:\Project\전국도시가스용도별수요가수공급량\out\용도별_수요가수_공급량_(2001-현재).csv")

st.set_page_config(page_title="회사별 전당공급량 (TopN 강조)", layout="wide")
st.title("연간 회사별 전당공급량 (TopN)")

# ----------------------------- 데이터 로드/집계 -----------------------------
@st.cache_data(ttl=3600)
def load_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig").rename(columns={"용도": "상품"})
    df["연도"] = pd.to_numeric(df["연도"], errors="coerce").astype("Int64")
    df["수요가수"] = pd.to_numeric(df["수요가수"], errors="coerce")
    df["공급량"]  = pd.to_numeric(df["공급량"],  errors="coerce")
    # 회사 공백 제거 후 표준화: '대구'→'대성', '충남'→'CNCITY'
    df["회사"] = (
        df["회사"].astype(str).str.replace(r"\s+", "", regex=True)
          .replace({"대구": "대성", "충남": "CNCITY"})
    )
    return df.dropna(subset=["연도"])

def agg_company_year_product(df: pd.DataFrame) -> pd.DataFrame:
    g = (
        df.groupby(["연도", "회사", "상품"], as_index=False)
          .agg(수요가수=("수요가수", "sum"), 공급량=("공급량", "sum"))
    )
    # 천 m³ → m³, 전당공급량 계산
    g["공급량(m3)"] = g["공급량"] * 1000.0
    denom = g["수요가수"].replace(0, np.nan)
    g["전당공급량"] = g["공급량(m3)"] / denom
    return g

def pick_topn(df: pd.DataFrame, n: int, mode: str, years: tuple[int, int]) -> list[str]:
    """전당공급량 기준 TopN 회사 (최근연도/평균)"""
    if df.empty:
        return []
    y0, y1 = years
    d = df[(df["연도"] >= y0) & (df["연도"] <= y1)].copy()
    if d.empty:
        return []
    if mode == "최근연도":
        last = int(d["연도"].max())
        t = (
            d[d["연도"] == last]
            .groupby("회사", as_index=False)["전당공급량"].mean()
            .sort_values("전당공급량", ascending=False)
        )
    else:
        t = (
            d.groupby("회사", as_index=False)["전당공급량"].mean()
            .sort_values("전당공급량", ascending=False)
        )
    return t["회사"].head(max(1, n)).tolist()

# ----------------------------- 준비 -----------------------------
raw = load_data(CSV_PATH)
agg_all = agg_company_year_product(raw)

# ----------------------------- 사이드바 -----------------------------
st.sidebar.header("필터")
year_min, year_max = int(agg_all["연도"].min()), int(agg_all["연도"].max())
default_start = max(2010, year_min)  # ✅ 2010년부터 시작
years = st.sidebar.slider("연도 범위", year_min, year_max, (default_start, year_max), key="years")

prod_all = sorted(agg_all["상품"].dropna().unique().tolist())
sel_prod = st.sidebar.selectbox("상품 (단일 선택)", prod_all, index=0, key="prod")

mode = st.sidebar.radio("TopN 기준", ["최근연도", "평균"], horizontal=True, key="mode")
topn = st.sidebar.number_input("TopN (표시 회사 수)", min_value=1, max_value=50, value=10, step=1, key="topn")

# 차트 높이
chart_h = st.sidebar.slider("차트 높이(px)", min_value=480, max_value=1400, value=720, step=40, key="height")

# ----------------------------- 필터링 -----------------------------
dfp = agg_all[
    (agg_all["상품"] == sel_prod) &
    (agg_all["연도"] >= years[0]) &
    (agg_all["연도"] <= years[1])
].copy()

# 기본 회사 선택: 요청 6개(존재하는 것만)
preferred_defaults = ["서울", "삼천리", "대성", "해양", "CNCITY", "부산", "인천"]
all_companies = sorted(dfp["회사"].dropna().unique().tolist())
default_list = [c for c in preferred_defaults if c in all_companies]

# TopN 참고(표시는 사용자가 결정)
top_companies = pick_topn(dfp, topn, mode, years)

sel_companies = st.sidebar.multiselect(
    "회사(멀티 선택) — '대성'은 항상 포함됩니다",
    options=all_companies,
    default=default_list or (top_companies if top_companies else all_companies),
    key="companies"
)

# ✅ '대성' 항상 포함 강제
if "대성" in all_companies and "대성" not in sel_companies:
    sel_companies = sel_companies + ["대성"]

st.sidebar.caption(
    "기본 회사: " + (", ".join(default_list) if default_list else "-")
    + "  | TopN 참고: " + (", ".join(top_companies) if top_companies else "-")
)

plot_df = dfp[dfp["회사"].isin(sel_companies)].copy().sort_values(["연도", "회사"])

# ----------------------------- 시각화 -----------------------------
st.subheader(f"연간 회사별 전당공급량 — 상품: {sel_prod}")
if plot_df.empty:
    st.info("선택된 조건에 해당하는 데이터가 없습니다.")
else:
    fig = px.line(
        plot_df, x="연도", y="전당공급량", color="회사",
        markers=True, render_mode="svg"
    )
    # '대성' 강조
    for tr in fig.data:
        tr.update(line=dict(width=5 if tr.name == "대성" else 2))
        tr.update(marker=dict(size=8 if tr.name == "대성" else 6))

    fig.update_layout(
        height=chart_h,
        yaxis_title="전당공급량 (m³/계좌)",
        legend_title="회사",
        hovermode="x unified",
        margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

    # 상세 표 + 다운로드
    show = (
        plot_df[["연도", "회사", "상품", "수요가수", "공급량(m3)", "전당공급량"]]
        .sort_values(["연도", "회사"])
    )
    st.dataframe(show, use_container_width=True)
    st.download_button(
        "CSV 다운로드 (상세)",
        data=show.to_csv(index=False, encoding="utf-8-sig"),
        file_name=f"회사별_전당공급량_Top{topn}_{sel_prod}.csv",
        mime="text/csv",
        key="dl_detail",
    )

    # ----------------------------- ✅ 전당공급량 피벗 -----------------------------
    st.subheader("전당공급량 피벗 (행=연도, 열=회사, 값=전당공급량)")
    pivot = (
        plot_df.pivot_table(index="연도", columns="회사", values="전당공급량", aggfunc="mean")
               .sort_index()
               .round(2)
    )
    # 선택한 회사 순서대로 열 정렬
    ordered_cols = [c for c in sel_companies if c in pivot.columns]
    other_cols = [c for c in pivot.columns if c not in ordered_cols]
    pivot = pivot[ordered_cols + other_cols] if ordered_cols else pivot

    st.dataframe(pivot, use_container_width=True)
    st.download_button(
        "CSV 다운로드 (피벗)",
        data=pivot.reset_index().to_csv(index=False, encoding="utf-8-sig"),
        file_name=f"전당공급량_피벗_{sel_prod}.csv",
        mime="text/csv",
        key="dl_pivot",
    )
