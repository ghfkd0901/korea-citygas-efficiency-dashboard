# main.py
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="도시가스 대시보드", layout="wide")

st.title("도시가스 대시보드")
st.caption("전국 도시가스 데이터 · 네비게이션 홈")

st.divider()

cols = st.columns(2)

with cols[0]:
    st.subheader("공급량 추이")
    st.page_link(
        "pages/전국도시가스공급량추이.py",
        label="전국도시가스공급량추이", icon="📈"
    )

with cols[1]:
    st.subheader("전당공급량 추이")
    st.page_link(
        "pages/전국도시가스전당공급량추이.py",
        label="전국도시가스전당공급량추이", icon="👥"
    )

st.divider()
st.caption("※ 실행: 프로젝트 루트에서 `streamlit run main.py`")
