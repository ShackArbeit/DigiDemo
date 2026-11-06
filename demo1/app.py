"""
Demo 1：個資偵測與去識別化（Streamlit 介面）

執行：.venv\\Scripts\\streamlit.exe run demo1/app.py
"""

import html
import io
import sys
from pathlib import Path

# 讓 `streamlit run demo1/app.py` 也能 import 專案內的模組
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from demo1.deidentify import deidentify_dataframe  # noqa: E402
from demo1.detector import find_pii, scan_dataframe  # noqa: E402
from demo1.kanon import DEFAULT_QUASI_IDENTIFIERS, kanon_summary, suppress  # noqa: E402

# 狀態色（固定用途，不拿來當一般系列色）
COLOR_CRITICAL = "#d03b3b"
COLOR_WARNING = "#fab219"

# 直接識別個資 → 高風險；可間接識別 → 中風險
HIGH_RISK_TYPES = {"身分證字號", "手機", "市話", "Email", "姓名"}
MEDIUM_RISK_TYPES = {"生日", "地址"}

st.set_page_config(page_title="Demo 1｜個資偵測與去識別化", layout="wide")

# 錄影用：放大字體
st.markdown("""
<style>
html, body, [class*="css"], .stMarkdown p, .stMarkdown li { font-size: 20px; }
h1 { font-size: 2.6rem !important; }
h2 { font-size: 2.0rem !important; }
h3 { font-size: 1.6rem !important; }
button[data-baseweb="tab"] p { font-size: 1.4rem !important; font-weight: 600; }
[data-testid="stMetricValue"] { font-size: 2.6rem !important; }
[data-testid="stMetricLabel"] p { font-size: 1.15rem !important; }
.stDataFrame { font-size: 18px; }
mark.pii { background: #fde2e2; color: #8a1c1c; padding: 0 4px; border-radius: 4px;
           font-weight: 600; }
.note-row { font-size: 20px; line-height: 2.0; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 資料
# ---------------------------------------------------------------------------

@st.cache_data
def prepare(file_bytes: bytes) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    讀取上傳的 CSV → 偵測 → 去識別化，結果快取起來，拉滑桿時不用重算。
    快取的鍵是「上傳檔案的位元組」，而不是 DataFrame：
    Streamlit 雜湊 DataFrame 在部分 pandas 版本會失敗（UnhashableParamError）。
    所有欄位都當文字讀入，手機開頭的 0 才不會不見。
    """
    raw = pd.read_csv(io.BytesIO(file_bytes), dtype=str, keep_default_na=False, encoding="utf-8-sig")
    return raw, scan_dataframe(raw), deidentify_dataframe(raw)


def risk_level(pii_types: str) -> str:
    types = set(pii_types.split("、"))
    if types & HIGH_RISK_TYPES:
        return "高"
    if types & MEDIUM_RISK_TYPES:
        return "中"
    return "—"


def color_risk(value: str) -> str:
    colors = {"高": COLOR_CRITICAL, "中": COLOR_WARNING}
    if value in colors:
        text = "#0b0b0b" if value == "中" else "#ffffff"
        return f"background-color: {colors[value]}; color: {text}; font-weight: 700"
    return ""


def highlight_pii(text: str) -> str:
    """把自由文字中的個資用 <mark> 標起來（先跳脫 HTML，避免注入）。"""
    parts, last = [], 0
    for m in find_pii(text):
        parts.append(html.escape(text[last:m.start]))
        parts.append(f'<mark class="pii">{html.escape(m.value)}</mark>'
                     f'<small>（{m.pii_type}）</small>')
        last = m.end
    parts.append(html.escape(text[last:]))
    return "".join(parts)


# ---------------------------------------------------------------------------
# 側邊欄：資料來源
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("資料來源")
    uploaded = st.file_uploader("上傳 CSV 檔案", type="csv")
    st.caption("⚠️ 本 demo 所有資料皆為程式產生的合成資料，不含任何真實個人資料。")

st.title("🔍 Demo 1｜個資偵測與去識別化")

# 一開始畫面空白：等使用者上傳 CSV 後才開始分析
if uploaded is None:
    st.info("👈 請從左側上傳 CSV 檔案，系統會自動偵測個資、去識別化，並檢查 k-匿名風險。")
    st.stop()

try:
    raw, scan_report, deid = prepare(uploaded.getvalue())
except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as e:
    st.error(f"無法讀取「{uploaded.name}」，請確認是 UTF-8 編碼的 CSV 檔案。（{type(e).__name__}）")
    st.stop()

st.markdown(f"**資料：** {uploaded.name}，共 **{len(raw):,}** 筆、{len(raw.columns)} 個欄位")

tab1, tab2, tab3 = st.tabs(["① 偵測", "② 去識別化", "③ 風險檢查"])


# ---------------------------------------------------------------------------
# 步驟一：偵測
# ---------------------------------------------------------------------------

with tab1:
    st.header("步驟一：哪些欄位有個資？")
    report = scan_report.copy()
    report.insert(3, "風險", report["個資類型"].map(risk_level))

    pii_columns = int((report["命中筆數"] > 0).sum())
    rejected = int(report["排除筆數（檢查碼錯誤）"].sum())
    free_text = report[(report["偵測方式"] == "內容比對")
                       & (report["命中比例"] < 1) & (report["命中筆數"] > 0)]

    c1, c2, c3 = st.columns(3)
    c1.metric("含個資的欄位", f"{pii_columns} / {len(report)}")
    if len(free_text):
        row = free_text.iloc[0]
        c2.metric(f"「{row['欄位']}」欄含個資", f"{row['命中筆數']} 筆", f"{row['命中比例']:.0%}",
                  delta_color="off")
    c3.metric("檢查碼排除的誤判", f"{rejected} 筆")

    styled = (report.style
              .map(color_risk, subset=["風險"])
              .format({"命中比例": "{:.0%}"}))
    st.dataframe(styled, hide_index=True, width="stretch",
                 height=40 * (len(report) + 1))

    if len(free_text):
        column = free_text.iloc[0]["欄位"]
        st.subheader(f"自由文字欄位「{column}」裡的個資")
        samples = raw.loc[raw[column].map(lambda t: len(find_pii(t)) > 0), column].head(6)
        st.markdown("<div class='note-row'>" +
                    "<br>".join(f"• {highlight_pii(t)}" for t in samples) + "</div>",
                    unsafe_allow_html=True)
        st.info("個資不只在「個資欄位」裡——承辦人隨手寫的備註也常有個資。")


# ---------------------------------------------------------------------------
# 步驟二：去識別化
# ---------------------------------------------------------------------------

DISPLAY_PAIRS = [  # (原始欄位, 處理後欄位)
    ("姓名", "姓名"), ("身分證字號", "身分證字號"), ("生日", "年齡層"),
    ("手機", "手機"), ("地址", "居住區"), ("備註", "備註"),
]

with tab2:
    st.header("步驟二：遮罩、泛化、標籤替換")

    pairs = [(a, b) for a, b in DISPLAY_PAIRS if a in raw.columns and b in deid.columns]
    left, right = st.columns(2)
    with left:
        st.subheader("處理前（原始）")
        st.dataframe(raw[[a for a, _ in pairs]].head(10), hide_index=True,
                     width="stretch", height=420)
    with right:
        st.subheader("處理後（去識別化）")
        st.dataframe(deid[[b for _, b in pairs]].head(10), hide_index=True,
                     width="stretch", height=420)

    st.markdown("""
| 方法 | 欄位 | 結果 |
|---|---|---|
| **遮罩** | 姓名、身分證、手機、Email | 王○明、A12\\*\\*\\*\\*789、0912\\*\\*\\*678、\\*\\*\\*@example.com |
| **泛化** | 生日、地址 | 60-69歲、臺北市大安區 |
| **標籤替換** | 備註 | 請改撥家屬手機 [手機] |
""")


# ---------------------------------------------------------------------------
# 步驟三：風險檢查（k-匿名）
# ---------------------------------------------------------------------------

with tab3:
    st.header("步驟三：去識別化之後，還認得出來嗎？")
    qis = [c for c in DEFAULT_QUASI_IDENTIFIERS if c in deid.columns]

    if len(qis) < len(DEFAULT_QUASI_IDENTIFIERS):
        st.warning(f"資料缺少準識別欄位：{', '.join(set(DEFAULT_QUASI_IDENTIFIERS) - set(qis))}，"
                   "無法進行 k-匿名檢查。")
        st.stop()

    st.markdown(f"以準識別欄位 **{'、'.join(qis)}** 分組。"
                "每一組至少要有 **k** 人，才能「躲在人群裡」。")

    k = st.slider("k 值", min_value=2, max_value=10, value=5)
    summary = kanon_summary(deid, k, qis)

    c1, c2, c3 = st.columns(3)
    c1.metric(f"不滿足 k={k} 的紀錄", f"{summary['不滿足k的紀錄數']} 筆",
              f"佔 {summary['不滿足k的比例']:.1%}", delta_color="off")
    c2.metric(f"不滿足 k={k} 的群組", f"{summary['不滿足k的群組數']} / {summary['群組數']} 組")
    c3.metric("可被唯一識別（組內只有 1 人）", f"{summary['可唯一識別的紀錄數']} 筆")
    c3.caption("不受 k 值影響：這些人在任何 k 值下都是唯一的")

    if summary["不滿足k的紀錄數"]:
        st.error(f"⚠️ 姓名、身分證都遮罩了，仍有 **{summary['不滿足k的紀錄數']} 筆**紀錄"
                 f"所在的群組不到 {k} 人，可能被認出來。")

    # 趨勢圖：x = k 值（2～10），y = 不滿足 k 的紀錄數；目前的 k 以大圓點標出
    k_values = list(range(2, 11))
    trend = [kanon_summary(deid, kv, qis)["不滿足k的紀錄數"] for kv in k_values]
    current = trend[k_values.index(k)]
    fig = go.Figure()
    fig.add_scatter(x=k_values, y=trend, mode="lines+markers", name="不滿足 k 的紀錄數",
                    line=dict(color=COLOR_CRITICAL, width=3), marker=dict(size=9),
                    hovertemplate="k = %{x}<br>不滿足 k 的紀錄 %{y} 筆<extra></extra>")
    # 目前選擇的 k：放大的圓點＋白色外框＋直接標註數字
    fig.add_scatter(x=[k], y=[current], mode="markers", showlegend=False, hoverinfo="skip",
                    marker=dict(size=20, color=COLOR_CRITICAL, line=dict(color="#ffffff", width=3)))
    fig.add_annotation(x=k, y=current, text=f"<b>k = {k}：{current} 筆</b>", showarrow=True,
                       arrowhead=0, ax=0, ay=-45, font=dict(size=20, color="#0b0b0b"),
                       bgcolor="#ffffff", bordercolor="#c3c2b7", borderpad=4)
    fig.update_layout(
        title=dict(text="k 越大，越多紀錄不滿足 k-匿名", font_size=20, x=0),
        height=420, margin=dict(t=60, b=50, l=60, r=30), showlegend=False,
        xaxis=dict(title="k 值（每組至少要有幾人）", dtick=1, title_font_size=18,
                   tickfont_size=16, showgrid=False, range=[1.6, 10.4]),
        yaxis=dict(title="不滿足 k 的紀錄數（筆）", title_font_size=18, tickfont_size=16,
                   gridcolor="#e1e0d9", rangemode="tozero"),
        plot_bgcolor="#ffffff",
    )
    st.plotly_chart(fig, width="stretch")

    st.subheader("處理方式：抑制（移除不滿足 k 的紀錄）")
    use_suppress = st.checkbox("啟用抑制")
    output = deid
    if use_suppress:
        output, loss = suppress(deid, k, qis)
        c1, c2 = st.columns(2)
        c1.metric("保留紀錄", f"{len(output)} 筆")
        c2.metric("資料損失", f"{loss:.1%}", delta_color="off")
        st.warning(f"k 越大越安全，但要刪掉的資料越多——k={k} 時損失 {loss:.1%}。")

    st.download_button(
        "⬇️ 下載處理後 CSV", data=output.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"applicants_deid_k{k}{'_suppressed' if use_suppress else ''}.csv",
        mime="text/csv",
    )

    st.info("**k-匿名的限制：** 如果同一組的人申請項目全部相同，就算認不出是誰，"
            "也能推出「他一定領這項補助」（同質性攻擊）。→ 這正是《隱私強化技術應用指引》"
            "提到差分隱私等更強技術的原因。")
