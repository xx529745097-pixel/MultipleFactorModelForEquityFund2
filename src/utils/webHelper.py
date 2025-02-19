import io
import streamlit as st

# ------------------------------------------------------
# 将Dataframe转为为Excel的Helper函数
# ------------------------------------------------------
def convert_df(df):
    f =io.BytesIO()
    df.to_excel(f)
    return f

# ------------------------------------------------------
# web控制header距顶部的距离
# ------------------------------------------------------
def set_top_padding(height: str = "20px") -> None:
    styl = f"""
    <style>
    .main>.block-container {{
    padding-top: {height};
    }}
    </style>
    """
    st.markdown(styl, unsafe_allow_html=True)