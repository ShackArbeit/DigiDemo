"""
Demo 2：差分隱私統計發布（Streamlit 介面，分三幕）

執行：.venv\\Scripts\\streamlit.exe run demo2/app.py
"""

import sys
from pathlib import Path

# 讓 `streamlit run demo2/app.py` 也能 import 專案內的模組
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from demo2.attack import differencing_attack  # noqa: E402
from demo2.mechanisms import (DEFAULT_BOUND, attack_with_dp, clip_values,  # noqa: E402
                              dp_mean, mean_sensitivity, tradeoff_curve)
from shared.fake_data import DATA_DIR, generate_incomes, load_incomes  # noqa: E402

TARGET_ID = 1          # 攻擊目標：港區居民 #1
SEED = 2026            # 固定 seed，錄影時每次畫面都一樣
EPSILON_OPTIONS = [0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]

# 狀態色（固定用途）與類別色（依固定順序指派）
COLOR_CRITICAL = "#d03b3b"
COLOR_GOOD = "#0ca30c"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
COLOR_NEUTRAL = "#a9a89e"
COLOR_GRID = "#e1e0d9"
COLOR_TEXT_2 = "#52514e"

st.set_page_config(page_title="Demo 2｜差分隱私統計發布", layout="wide")

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
.stButton button p { font-size: 1.3rem; font-weight: 600; }
.big-formula { font-size: 1.5rem; line-height: 2.2; padding: 8px 20px;
               background: #f5f5f2; border-radius: 8px; }
.policy-line { font-size: 1.6rem; font-weight: 700; padding: 18px 24px;
               border-left: 6px solid #2a78d6; background: #eef4fc; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 資料（不對 DataFrame 做快取雜湊，避免 UnhashableParamError）
# ---------------------------------------------------------------------------

@st.cache_data
def load_data() -> pd.DataFrame:
    if (DATA_DIR / "incomes.csv").exists():
        return load_incomes()
    return generate_incomes()


@st.cache_data
def load_curve() -> pd.DataFrame:
    return tradeoff_curve(load_data())


def money(x: float) -> str:
    return f"{x:,.0f} 元"


def eps_label(eps: float) -> str:
    return f"{eps:g}"


df = load_data()
target_district = df.loc[df["id"] == TARGET_ID, "區"].iloc[0]

st.title("📊 Demo 2｜差分隱私統計發布")
st.markdown(f"**資料：** 虛構城市 8 個區的居民年收入，共 **{len(df):,}** 筆（程式產生的合成資料）")

tab1, tab2, tab3 = st.tabs(["第一幕：差分攻擊", "第二幕：加入差分隱私", "第三幕：取捨曲線"])


# ---------------------------------------------------------------------------
# 第一幕：差分攻擊
# ---------------------------------------------------------------------------

with tab1:
    st.header("只發布「平均數」，就安全了嗎？")
    st.markdown(f"統計單位發布了兩個看似無害的數字。攻擊者只知道：**目標住在{target_district}**。")

    exact = differencing_attack(df, TARGET_ID)
    c1, c2 = st.columns(2)
    c1.metric(f"查詢 A：{target_district}全部居民平均收入",
              money(exact["查詢A_平均"]), f"{exact['查詢A_人數']} 人", delta_color="off")
    c2.metric(f"查詢 B：{target_district}「排除目標」後平均收入",
              money(exact["查詢B_平均"]), f"{exact['查詢B_人數']} 人", delta_color="off")
    st.caption(f"兩個平均數只差 {exact['查詢A_平均'] - exact['查詢B_平均']:,.0f} 元，看起來無關緊要……")

    if st.button("🔓 執行差分攻擊", type="primary"):
        st.session_state["attack_run"] = True

    if st.session_state.get("attack_run"):
        st.markdown(f"""
<div class="big-formula">
目標收入 = 平均A × {exact['查詢A_人數']} − 平均B × {exact['查詢B_人數']}<br>
　　　　 = {exact['查詢A_平均'] * exact['查詢A_人數']:,.0f} − {exact['查詢B_平均'] * exact['查詢B_人數']:,.0f}<br>
　　　　 = <b>{exact['推算收入']:,.0f} 元</b>
</div>""", unsafe_allow_html=True)
        st.write("")
        c1, c2 = st.columns(2)
        c1.metric("攻擊者推算的收入", money(exact["推算收入"]))
        c2.metric("目標的真實收入", money(exact["真實收入"]))
        st.error(f"⚠️ 攻擊成功：推算結果與真實收入誤差 {abs(exact['誤差']):,.0f} 元。"
                 "「只發布統計數字」也會洩漏個資。")


# ---------------------------------------------------------------------------
# 第二幕：加入差分隱私
# ---------------------------------------------------------------------------

with tab2:
    st.header("發布前加入「剛好夠用」的雜訊")
    st.markdown(f"收入先限制在 **[0, {DEFAULT_BOUND / 10_000:,.0f} 萬]**，"
                "再加入 Laplace 雜訊：**雜訊大小 = (上限 ÷ 人數) ÷ ε**。同樣的攻擊再做一次：")

    eps = st.select_slider("ε（隱私預算）：越小越保護隱私", options=EPSILON_OPTIONS, value=1.0,
                           format_func=eps_label, key="eps_act2")
    # 每個 ε 用固定 seed → 錄影時同一個 ε 永遠顯示同樣的數字
    dp = attack_with_dp(df, TARGET_ID, eps, rng=np.random.default_rng([SEED, int(eps * 100)]))

    c1, c2 = st.columns(2)
    c1.metric("查詢 A（差分隱私發布）", money(dp["查詢A_平均"]),
              f"真實 {money(exact['查詢A_平均'])}", delta_color="off")
    c2.metric("查詢 B（差分隱私發布）", money(dp["查詢B_平均"]),
              f"真實 {money(exact['查詢B_平均'])}", delta_color="off")
    st.caption("發布的平均數仍然接近真實值，對統計用途來說夠用。")

    c1, c2 = st.columns(2)
    c1.metric("攻擊者推算的收入", money(dp["推算收入"]))
    c2.metric("目標的真實收入", money(dp["真實收入"]))

    if dp["相對誤差"] >= 0.2:
        st.success(f"✓ 攻擊失效：推算誤差 {abs(dp['誤差']):,.0f} 元，推算結果沒有參考價值。")
    else:
        # 雜訊是隨機的，偶爾會猜得接近；但攻擊者無從得知哪一次是準的
        st.warning(f"這次推算誤差 {abs(dp['誤差']):,.0f} 元，碰巧接近——"
                   "但攻擊者無法知道哪一次是準的，所以仍然無法確定目標的收入。")
    st.caption(f"為什麼？攻擊要把平均乘以人數（{dp['查詢A_人數']}）還原成總和，"
               f"雜訊也被放大 {dp['查詢A_人數']} 倍。這次攻擊做了 2 次查詢，共消耗隱私預算 2ε = {2 * eps:g}。")


# ---------------------------------------------------------------------------
# 第三幕：取捨曲線
# ---------------------------------------------------------------------------

with tab3:
    st.header("隱私強度 vs 準確度")
    curve = load_curve()

    eps3 = st.select_slider("ε（隱私預算）", options=EPSILON_OPTIONS, value=1.0,
                            format_func=eps_label, key="eps_act3")

    # --- 折線圖：ε vs 平均相對誤差（對數尺度） ---
    sizes = df["區"].value_counts()
    largest, smallest = sizes.idxmax(), sizes.idxmin()
    lines = [("全部平均", "8 區平均"),
             (largest, f"{largest}（{sizes[largest]:,} 人）"),
             (smallest, f"{smallest}（{sizes[smallest]:,} 人）")]

    fig = go.Figure()
    for (column, label), color in zip(lines, SERIES):
        fig.add_scatter(
            x=curve["ε"], y=curve[column] * 100, mode="lines", name=label,
            line=dict(color=color, width=3),
            hovertemplate=f"{label}<br>ε = %{{x:.2g}}<br>平均相對誤差 %{{y:.2f}}%<extra></extra>",
        )
        # 在線尾直接標上名稱
        fig.add_annotation(x=np.log10(curve["ε"].iloc[-1]), y=np.log10(curve[column].iloc[-1] * 100),
                           text=label, showarrow=False, xanchor="left", xshift=8,
                           font=dict(size=16, color=COLOR_TEXT_2))
    fig.add_vline(x=eps3, line_dash="dash", line_color=COLOR_TEXT_2, line_width=2,
                  annotation_text=f"目前 ε = {eps3:g}", annotation_position="top",
                  annotation_font_size=18)
    fig.update_layout(
        height=430, margin=dict(t=50, b=50, l=60, r=170), plot_bgcolor="#ffffff",
        xaxis=dict(type="log", title="ε（對數尺度）　← 隱私較強　｜　數字較準 →",
                   title_font_size=18, tickfont_size=16, gridcolor=COLOR_GRID,
                   tickvals=[0.01, 0.1, 1, 10], ticktext=["0.01", "0.1", "1", "10"]),
        yaxis=dict(type="log", title="平均相對誤差（%，對數尺度）", title_font_size=18,
                   tickfont_size=16, gridcolor=COLOR_GRID,
                   tickvals=[0.1, 1, 10, 100, 1000], ticktext=["0.1%", "1%", "10%", "100%", "1000%"]),
        legend=dict(orientation="h", y=1.14, x=0, font_size=18),
        hovermode="x unified",
    )
    st.plotly_chart(fig, width="stretch")

    # --- 長條圖：各區真實平均 vs 差分隱私發布平均 ---
    st.subheader(f"ε = {eps3:g} 時，各區平均收入的發布結果")
    rng = np.random.default_rng([SEED, int(eps3 * 100), 3])
    order = sizes.index.tolist()   # 依人數由多到少
    true_means, released = [], []
    for district in order:
        values = df.loc[df["區"] == district, "年收入"].to_numpy(dtype=float)
        true_means.append(values.mean())
        released.append(dp_mean(values, eps3, rng=rng))
    labels = [f"{d}<br>{sizes[d]:,} 人" for d in order]
    rel_err = [abs(r - t) / t * 100 for r, t in zip(released, true_means)]

    bar = go.Figure()
    bar.add_bar(x=labels, y=np.array(true_means) / 10_000, name="真實平均", marker_color=COLOR_NEUTRAL,
                hovertemplate="%{x}<br>真實平均 %{y:.1f} 萬<extra></extra>")
    bar.add_bar(x=labels, y=np.array(released) / 10_000, name="差分隱私發布", marker_color=SERIES[0],
                customdata=rel_err,
                hovertemplate="%{x}<br>發布值 %{y:.1f} 萬<br>誤差 %{customdata:.1f}%<extra></extra>")
    bar.update_layout(
        height=400, barmode="group", bargap=0.25, bargroupgap=0.05,
        margin=dict(t=50, b=40, l=60, r=20), plot_bgcolor="#ffffff",
        xaxis=dict(tickfont_size=16),
        yaxis=dict(title="平均年收入（萬元）", title_font_size=18, tickfont_size=16, gridcolor=COLOR_GRID),
        legend=dict(orientation="h", y=1.14, x=0, font_size=18),
    )
    st.plotly_chart(bar, width="stretch")
    st.caption("人越少的區，雜訊相對越大——差分隱私適合大群體的統計。")

    st.markdown('<div class="policy-line">ε 越小越保護隱私，但數字越不準——'
                "這是政策需要決定的取捨，不只是技術問題。</div>", unsafe_allow_html=True)
