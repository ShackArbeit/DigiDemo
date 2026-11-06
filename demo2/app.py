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
.katex { font-size: 1.45em !important; }
.step-title { font-size: 1.3rem; font-weight: 800; margin-bottom: 2px; }
.step-why { font-size: 1.0rem; color: #52514e; min-height: 3.2em; }
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
st.markdown(f"**資料：** 虛構城市 8 個區的居民年收入，共 **{len(df):,}** 筆")

tab1, tab2, tab3 = st.tabs(["第一幕：差分攻擊", "第二幕：加入差分隱私", "第三幕：取捨曲線"])


# ---------------------------------------------------------------------------
# 第一幕：差分攻擊
# ---------------------------------------------------------------------------

with tab1:
    st.header("「平均數」真的安全了嗎？")
    st.markdown(f"統計單位發布了兩個貌似不相關的數字。攻擊者只知道：**目標住在{target_district}**。")

    exact = differencing_attack(df, TARGET_ID)
    c1, c2 = st.columns(2)
    c1.metric(f"查詢 A：{target_district}全部居民平均收入",
              money(exact["查詢A_平均"]), f"{exact['查詢A_人數']} 人", delta_color="off")
    c2.metric(f"查詢 B：{target_district}「排除目標」後平均收入",
              money(exact["查詢B_平均"]), f"{exact['查詢B_人數']} 人", delta_color="off")
    st.caption(f"兩個平均數只差 {exact['查詢A_平均'] - exact['查詢B_平均']:,.0f} 元，貌似無關聯……")

    if st.button("🔓 執行差分攻擊", type="primary"):
        st.session_state["attack_run"] = True

    if st.session_state.get("attack_run"):
        # 代數形式：兩個總和相減，剩下的就是目標一個人的收入
        st.latex(r"x_{\text{target}} = n \cdot \bar{A} - (n-1) \cdot \bar{B}")
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

    # --- 四個步驟：公式 + 以目標所在區的實際數字代入（隨 ε 滑桿即時更新） ---
    district_values = df.loc[df["區"] == target_district, "年收入"].to_numpy(dtype=float)
    n = len(district_values)
    n_clipped = int((district_values > DEFAULT_BOUND).sum())
    clipped_mean = clip_values(district_values).mean()
    delta_f = mean_sensitivity(n)
    scale_b = delta_f / eps
    noise_a = dp["查詢A_平均"] - clipped_mean

    def tex_num(x: float) -> str:
        """LaTeX 中的千分位：3{,}000{,}000"""
        return f"{x:,.0f}".replace(",", "{,}")

    st.subheader(f"📐 差分隱私的四個步驟（以{target_district} {n} 人、ε = {eps:g} 為例）")
    s1, s2, s3, s4 = st.columns(4)
    with s1.container(border=True):
        st.markdown('<div class="step-title">① 截斷 Clipping</div>'
                    '<div class="step-why">替收入設上限，讓任何一個人的影響都有天花板</div>',
                    unsafe_allow_html=True)
        st.latex(r"x_i' = \min(\max(x_i,\,0),\; B)")
        st.latex(rf"B = {tex_num(DEFAULT_BOUND)}")
        st.caption(f"{target_district} {n} 人中有 {n_clipped} 人超過上限。"
                   "代價：超過的人被當成 B，平均會略為偏低（偏差）")
    with s2.container(border=True):
        st.markdown('<div class="step-title">② 敏感度 Sensitivity</div>'
                    '<div class="step-why">換掉一個人，平均數最多會改變多少？</div>',
                    unsafe_allow_html=True)
        st.latex(r"\Delta f = \frac{B}{n}")
        st.latex(rf"= \frac{{{tex_num(DEFAULT_BOUND)}}}{{{n}}} = {tex_num(delta_f)}")
        st.caption(f"最極端：把收入 0 的人換成收入 B 的人，平均最多變動 {delta_f:,.0f} 元")
    with s3.container(border=True):
        st.markdown('<div class="step-title">③ 雜訊尺度 Laplace</div>'
                    '<div class="step-why">ε 越小，雜訊越大，隱私越強</div>',
                    unsafe_allow_html=True)
        st.latex(r"b = \frac{\Delta f}{\varepsilon}")
        st.latex(rf"= \frac{{{tex_num(delta_f)}}}{{{eps:g}}} = {tex_num(scale_b)}")
        st.caption("Laplace 分布：中間尖、兩側指數遞減，平均為 0（不會系統性偏高或偏低）")
    with s4.container(border=True):
        st.markdown('<div class="step-title">④ 加雜訊後發布</div>'
                    '<div class="step-why">真實平均 + 隨機抽出的雜訊</div>',
                    unsafe_allow_html=True)
        st.latex(r"\tilde{\mu} = \bar{x}' + \mathrm{Lap}(0,\, b)")
        st.latex(rf"= {tex_num(clipped_mean)} {'+' if noise_a >= 0 else '-'} {tex_num(abs(noise_a))}")
        st.caption(f"這次抽到的雜訊是 {noise_a:+,.0f} 元 → 發布 {dp['查詢A_平均']:,.0f} 元")

    st.markdown("#### 同樣的攻擊再做一次")
    # 兩個查詢都要保留（攻擊需要兩者相減），但縮成一張小表，讓下方「推算 vs 真實」成為主角
    rows = []
    for key, label in [("A", f"查詢 A：{target_district}全部"), ("B", f"查詢 B：排除目標")]:
        true_value, released_value = exact[f"查詢{key}_平均"], dp[f"查詢{key}_平均"]
        rows.append(f"| {label} | {dp[f'查詢{key}_人數']} 人 | {true_value:,.0f} | "
                    f"**{released_value:,.0f}** | {released_value - true_value:+,.0f} |")
    st.markdown("| 發布的統計 | 人數 | 真實平均 | 差分隱私發布 | 誤差 |\n|---|---:|---:|---:|---:|\n"
                + "\n".join(rows))
    worst = max(abs(dp[f"查詢{k}_平均"] - exact[f"查詢{k}_平均"]) / exact[f"查詢{k}_平均"] for k in "AB")
    if worst < 0.1:
        st.caption(f"單獨看，每個發布的平均數都接近真實值（誤差 {worst:.1%} 以內），對統計用途來說夠用。")
    else:
        st.caption(f"ε = {eps:g} 時雜訊太大，連平均數本身都偏差 {worst:.0%}——"
                   "隱私很強，但統計也不準了。這就是第三幕要談的取捨。")

    c1, c2 = st.columns(2)
    c1.metric("攻擊者推算的收入", money(dp["推算收入"]))
    c2.metric("目標的真實收入", money(dp["真實收入"]))

    if dp["相對誤差"] >= 0.2:
        st.success(f"✓ 攻擊失效：推算誤差 {abs(dp['誤差']):,.0f} 元，推算結果沒有參考價值。")
    else:
        # 雜訊是隨機的，偶爾會猜得接近；但攻擊者無從得知哪一次是準的
        st.warning(f"這次推算誤差 {abs(dp['誤差']):,.0f} 元，碰巧接近——"
                   "但攻擊者無法知道哪一次是準的，所以仍然無法確定目標的收入。")


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
    st.subheader(f"ε = {eps3:g} 時，{largest} vs {smallest} 平均收入的發布結果")
    rng = np.random.default_rng([SEED, int(eps3 * 100), 3])
    # 只比較人數最多與最少的兩區（中區 vs 山腳區），對比最明顯、畫面也不擁擠
    order = [largest, smallest]
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

    # 為什麼人少的區誤差大：Laplace(0, b) 的平均絕對值 = b = B / (n·ε)
    f1, f2 = st.columns([1, 1.4])
    with f1:
        st.latex(r"\text{E}\,|\text{noise}| = b = \frac{B}{n \cdot \varepsilon}")
    with f2:
        b_large = DEFAULT_BOUND / (sizes[largest] * eps3)
        b_small = DEFAULT_BOUND / (sizes[smallest] * eps3)
        st.markdown(f"ε = {eps3:g} 時，平均雜訊：**{largest}（{sizes[largest]:,} 人）約 {b_large:,.0f} 元**、"
                    f"**{smallest}（{sizes[smallest]:,} 人）約 {b_small:,.0f} 元**。")
        st.caption("人越少的區，雜訊相對越大——差分隱私適合大群體的統計。")

    st.markdown('<div class="policy-line">ε 越小越保護隱私，但數字越不準——'
                "這是政策需要決定的取捨，不只是技術問題。</div>", unsafe_allow_html=True)
