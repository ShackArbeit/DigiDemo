"""
Demo 2：差分隱私統計發布（Streamlit 介面，分三幕）

執行：.venv\\Scripts\\streamlit.exe run demo2/app.py

第一幕「差分攻擊」：兩個看似無害的平均數，相減就還原出一個人的收入
第二幕「加入差分隱私」：同樣的攻擊，推算結果偏差很大
第三幕「取捨曲線」：ε 越小越保護隱私，但數字越不準
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
from demo2.mechanisms import (DEFAULT_BOUND, attack_with_dp, dp_mean,  # noqa: E402
                              tradeoff_curve)
from shared.fake_data import DATA_DIR, generate_incomes, load_incomes  # noqa: E402

SEED = 2026
TARGET_ID = 1               # 攻擊目標：港區 1 號居民（虛構人物「王先生」）
TARGET_LABEL = "王先生"

# 狀態色（與 Demo 1 一致，只用於警示／成功）
COLOR_CRITICAL = "#d03b3b"
COLOR_GOOD = "#0ca30c"
# 資料色：DP 發布值用藍色；真實值是「參考基準」，用中性灰
COLOR_DP = "#2a78d6"
COLOR_TRUE = "#a3a29a"
COLOR_AXIS = "#52514e"
COLOR_GRID = "#e1e0d9"

# 滑桿的 ε 選項（對數尺度上大致等距，數字好念）
ATTACK_EPSILONS = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
CURVE_EPSILONS = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0]

POLICY_SENTENCE = ("ε 越小越保護隱私，但數字越不準——"
                   "這是政策需要決定的取捨，不只是技術問題。")

st.set_page_config(page_title="Demo 2｜差分隱私統計發布", layout="wide")

# 錄影用：放大字體（與 Demo 1 相同）
st.markdown("""
<style>
html, body, [class*="css"], .stMarkdown p, .stMarkdown li { font-size: 20px; }
h1 { font-size: 2.6rem !important; }
h2 { font-size: 2.0rem !important; }
h3 { font-size: 1.6rem !important; }
button[data-baseweb="tab"] p { font-size: 1.4rem !important; font-weight: 600; }
[data-testid="stMetricValue"] { font-size: 2.6rem !important; }
[data-testid="stMetricLabel"] p { font-size: 1.15rem !important; }
.formula { font-size: 24px; line-height: 2.0; background: #f6f5f1; padding: 12px 20px;
           border-radius: 8px; }
.policy { font-size: 26px; font-weight: 700; text-align: center; padding: 18px;
          border: 3px solid #2a78d6; border-radius: 10px; margin: 8px 0 16px 0; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 資料與計算（全部快取，拉滑桿時不用重算；所有亂數都有固定 seed，錄影可重現）
# ---------------------------------------------------------------------------

@st.cache_data
def load_data() -> pd.DataFrame:
    if (DATA_DIR / "incomes.csv").exists():
        return load_incomes()
    return generate_incomes(seed=SEED)


def eps_key(epsilon: float) -> int:
    """把 ε 轉成整數，當作亂數 seed 的一部分（同一個 ε 每次都得到同樣的雜訊）。"""
    return int(round(epsilon * 1000))


@st.cache_data
def dp_attack_once(epsilon: float, attempt: int) -> dict:
    """第 attempt 次的 DP 攻擊；同樣的 (ε, 次數) 每次結果都一樣。"""
    rng = np.random.default_rng([SEED, eps_key(epsilon), attempt])
    return attack_with_dp(load_data(), TARGET_ID, epsilon, rng=rng)


@st.cache_data
def dp_attack_many(epsilon: float, trials: int = 200) -> np.ndarray:
    """重複攻擊 trials 次，回傳每次的推算收入（用來畫「攻擊者猜到的值」分布）。"""
    rng = np.random.default_rng([SEED, eps_key(epsilon), 999])
    df = load_data()
    return np.array([attack_with_dp(df, TARGET_ID, epsilon, rng=rng)["推算收入"]
                     for _ in range(trials)])


@st.cache_data
def curve(epsilons: tuple[float, ...]) -> pd.DataFrame:
    return tradeoff_curve(load_data(), epsilons=list(epsilons), seed=SEED)


@st.cache_data
def district_release(epsilon: float) -> pd.DataFrame:
    """各區：人數、真實平均、DP 發布平均、相對誤差（依人數由多到少排序）。"""
    rng = np.random.default_rng([SEED, eps_key(epsilon), 7])
    rows = []
    for name, group in load_data().groupby("區", sort=False):
        values = group["年收入"].to_numpy(dtype=float)
        true_mean = values.mean()
        released = dp_mean(values, epsilon, rng=rng)
        rows.append({"區": name, "人數": len(values), "真實平均": true_mean,
                     "DP發布平均": released,
                     "相對誤差": abs(released - true_mean) / true_mean})
    return pd.DataFrame(rows).sort_values("人數", ascending=False).reset_index(drop=True)


def money(value: float) -> str:
    """金額格式：547,000 元；負數用全形減號，畫面上比較醒目。"""
    sign = "−" if value < 0 else ""
    return f"{sign}{abs(value):,.0f} 元"


def base_layout(fig: go.Figure, height: int) -> None:
    fig.update_layout(height=height, margin=dict(t=50, b=50, l=60, r=20),
                      plot_bgcolor="#ffffff", hoverlabel=dict(font_size=18),
                      legend=dict(orientation="h", y=1.14, x=0, font_size=18))
    fig.update_xaxes(title_font=dict(size=18, color=COLOR_AXIS), tickfont_size=16,
                     linecolor=COLOR_AXIS)
    fig.update_yaxes(title_font=dict(size=18, color=COLOR_AXIS), tickfont_size=16,
                     gridcolor=COLOR_GRID)


df = load_data()
target = df[df["id"] == TARGET_ID].iloc[0]
district = target["區"]

with st.sidebar:
    st.header("資料")
    st.markdown(f"虛構城市「某市」居民年收入\n\n共 **{len(df):,}** 筆、{df['區'].nunique()} 區")
    st.markdown(f"**攻擊目標：** {district} {TARGET_ID} 號居民（{TARGET_LABEL}）")
    st.markdown(f"**收入上限 B：** {DEFAULT_BOUND:,} 元")
    st.caption("⚠️ 本 demo 所有資料皆為程式產生的合成資料，城市與區名皆為虛構，"
               "不含任何真實個人資料。")

st.title("📊 Demo 2｜差分隱私統計發布")
st.markdown("情境：統計單位只公布各區的**平均年收入**與**人數**——沒有任何人的姓名或收入。這樣安全嗎？")

tab1, tab2, tab3 = st.tabs(["① 差分攻擊", "② 加入差分隱私", "③ 取捨曲線"])


# ---------------------------------------------------------------------------
# 第一幕：差分攻擊
# ---------------------------------------------------------------------------

with tab1:
    st.header("第一幕：只公布平均數，也會洩漏個資")
    exact = differencing_attack(df, TARGET_ID)

    st.subheader("統計單位公布了兩個數字")
    c1, c2 = st.columns(2)
    c1.metric(f"查詢 A：{district}全體平均年收入（{exact['查詢A_人數']} 人）",
              money(exact["查詢A_平均"]))
    c2.metric(f"查詢 B：{district}「除了{TARGET_LABEL}以外」的平均（{exact['查詢B_人數']} 人）",
              money(exact["查詢B_平均"]))
    st.caption(f"兩個平均數只差 {exact['查詢A_平均'] - exact['查詢B_平均']:,.0f} 元，"
               "看起來無關緊要。（現實中「排除某人」常常是：本月 vs 上月、全體 vs 不含主管）")

    if st.button("🔓 執行差分攻擊", type="primary"):
        st.session_state["attack_done"] = True

    if st.session_state.get("attack_done"):
        st.markdown(
            f"<div class='formula'>"
            f"{TARGET_LABEL}的收入 ＝ 查詢 A × {exact['查詢A_人數']} 人 − "
            f"查詢 B × {exact['查詢B_人數']} 人<br>"
            f"＝ {exact['查詢A_平均']:,.2f} × {exact['查詢A_人數']} − "
            f"{exact['查詢B_平均']:,.2f} × {exact['查詢B_人數']}"
            f"</div>", unsafe_allow_html=True)
        st.write("")
        c1, c2, c3 = st.columns(3)
        c1.metric("攻擊者推算的收入", money(exact["推算收入"]))
        c2.metric(f"{TARGET_LABEL}的真實收入", money(exact["真實收入"]))
        c3.metric("誤差", money(abs(exact["誤差"])))
        st.error(f"🚨 **攻擊成功：推算結果與真實收入完全相同。** "
                 f"只靠兩個公開的平均數，就還原出{TARGET_LABEL}的年收入。")


# ---------------------------------------------------------------------------
# 第二幕：加入差分隱私
# ---------------------------------------------------------------------------

with tab2:
    st.header("第二幕：發布前先加入雜訊（差分隱私）")
    st.markdown(f"同樣的兩個查詢，但每個平均數發布前都先 **clip 到 [0, {DEFAULT_BOUND // 10_000} 萬]**，"
                "再加入 **Laplace 雜訊**（大小 ＝ 敏感度 B/n ÷ ε）。攻擊程式一行都沒改。")

    epsilon = st.select_slider("隱私預算 ε（越小越保護隱私）", options=ATTACK_EPSILONS,
                               value=1.0, key="eps_attack")
    attempt = st.session_state.setdefault("attempt", 0)
    if st.button("🔁 再攻擊一次（新的雜訊）"):
        st.session_state["attempt"] = attempt = attempt + 1

    dp = dp_attack_once(epsilon, attempt)

    st.subheader("統計單位公布的數字（已加雜訊）")
    c1, c2 = st.columns(2)
    c1.metric(f"查詢 A：{district}全體平均（{dp['查詢A_人數']} 人）", money(dp["查詢A_平均"]))
    c2.metric(f"查詢 B：除了{TARGET_LABEL}以外的平均（{dp['查詢B_人數']} 人）",
              money(dp["查詢B_平均"]))
    st.caption(f"真實的全區平均是 {money(exact['查詢A_平均'])}——"
               "發布的平均數本身仍然大致可用。")

    c1, c2, c3 = st.columns(3)
    c1.metric("攻擊者推算的收入", money(dp["推算收入"]))
    c2.metric(f"{TARGET_LABEL}的真實收入", money(dp["真實收入"]))
    c3.metric("誤差", money(abs(dp["誤差"])))

    if dp["相對誤差"] >= 0.2:
        st.success(f"🛡️ **攻擊失效：推算結果偏差 {money(abs(dp['誤差']))}。** "
                   "雜訊被「乘以人數」放大，個人的收入被藏起來了。")
    else:
        st.warning("這次的推算剛好比較接近——但攻擊者無從得知哪一次是準的。"
                   "看下圖：重複攻擊 200 次，猜測值散布得很廣。")

    # 200 次攻擊的推算值分布：真實收入只是其中一條線，攻擊者無法從分布中鎖定它
    guesses = dp_attack_many(epsilon) / 10_000   # 換算成萬元，數字比較好讀
    fig = go.Figure()
    fig.add_histogram(x=guesses, nbinsx=40, marker_color=COLOR_DP,
                      marker_line=dict(color="#ffffff", width=2),
                      hovertemplate="推算值 %{x} 萬元<br>%{y} 次<extra></extra>")
    fig.add_vline(x=dp["真實收入"] / 10_000, line_color=COLOR_CRITICAL, line_width=3,
                  annotation_text=f"真實收入 {dp['真實收入'] / 10_000:.1f} 萬",
                  annotation_position="top right", annotation_font_size=18)
    base_layout(fig, 360)
    fig.update_layout(title=dict(text=f"重複攻擊 200 次，攻擊者推算的收入（ε = {epsilon:g}）",
                                 font_size=20), showlegend=False, bargap=0.05)
    fig.update_xaxes(title="推算收入（萬元）")
    fig.update_yaxes(title="次數")
    st.plotly_chart(fig, width="stretch")

    st.info(f"💡 這次攻擊查詢了 2 次，消耗了 **2ε = {2 * epsilon:g}** 的隱私預算。"
            "查詢越多次，雜訊越容易被平均掉——所以 ε 是「預算」，用完就不能再查。")


# ---------------------------------------------------------------------------
# 第三幕：取捨曲線
# ---------------------------------------------------------------------------

with tab3:
    st.header("第三幕：隱私與準確度的取捨")
    st.markdown(f"<div class='policy'>{POLICY_SENTENCE}</div>", unsafe_allow_html=True)

    epsilon3 = st.select_slider("隱私預算 ε", options=CURVE_EPSILONS, value=1.0,
                                key="eps_curve")

    # 折線圖：各區平均收入的「平均相對誤差」（8 區平均、每個 ε 跑 200 次）
    line = curve(tuple(np.logspace(-2, 1, 31)))
    point = curve((epsilon3,)).iloc[0]
    fig = go.Figure()
    fig.add_scatter(x=line["ε"], y=line["全部平均"], mode="lines",
                    line=dict(color=COLOR_DP, width=3),
                    hovertemplate="ε = %{x:.3g}<br>平均相對誤差 %{y:.1%}<extra></extra>")
    fig.add_scatter(x=[epsilon3], y=[point["全部平均"]], mode="markers+text",
                    marker=dict(color=COLOR_DP, size=16, line=dict(color="#ffffff", width=3)),
                    text=[f"ε = {epsilon3:g}：誤差 {point['全部平均']:.1%}"],
                    textposition="top right", textfont_size=20,
                    hovertemplate="ε = %{x:g}<br>平均相對誤差 %{y:.1%}<extra></extra>")
    fig.add_annotation(x=np.log10(0.012), y=np.log10(0.004), text="◀ 隱私強、數字不準",
                       showarrow=False, xanchor="left", font=dict(size=18, color=COLOR_AXIS))
    fig.add_annotation(x=np.log10(9), y=np.log10(3), text="數字準、隱私弱 ▶",
                       showarrow=False, xanchor="right", font=dict(size=18, color=COLOR_AXIS))
    base_layout(fig, 400)
    fig.update_layout(showlegend=False,
                      title=dict(text="各區平均收入的平均相對誤差（每個 ε 模擬 200 次）",
                                 font_size=20))
    fig.update_xaxes(type="log", title="隱私預算 ε（對數尺度）",
                     tickvals=[0.01, 0.1, 1, 10], ticktext=["0.01", "0.1", "1", "10"])
    # 固定範圍 0.2%～500%：曲線（約 0.6%～150%）與兩側標註都放得下
    fig.update_yaxes(type="log", title="平均相對誤差（對數尺度）", range=[-2.7, 0.7],
                     tickvals=[0.001, 0.01, 0.1, 1, 10],
                     ticktext=["0.1%", "1%", "10%", "100%", "1000%"])
    st.plotly_chart(fig, width="stretch")

    # 長條圖：各區真實平均 vs DP 發布平均
    release = district_release(epsilon3)
    labels = [f"{r['區']}<br>{r['人數']:,} 人" for _, r in release.iterrows()]
    fig = go.Figure()
    fig.add_bar(x=labels, y=release["真實平均"] / 10_000, name="真實平均",
                marker_color=COLOR_TRUE, marker_line=dict(color="#ffffff", width=2),
                hovertemplate="%{x}<br>真實平均 %{y:.1f} 萬元<extra></extra>")
    fig.add_bar(x=labels, y=release["DP發布平均"] / 10_000, name="差分隱私發布",
                marker_color=COLOR_DP, marker_line=dict(color="#ffffff", width=2),
                text=[f"誤差 {e:.0%}" if e >= 0.01 else "誤差 <1%" for e in release["相對誤差"]],
                textposition="outside", textfont=dict(size=16, color="#0b0b0b"),
                cliponaxis=False,
                hovertemplate="%{x}<br>發布值 %{y:.1f} 萬元<extra></extra>")
    base_layout(fig, 440)
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.05,
                      uniformtext=dict(minsize=16, mode="show"),   # 柱上文字大小一致
                      legend=dict(x=1, xanchor="right"),
                      title=dict(text=f"各區平均年收入：真實 vs 差分隱私發布（ε = {epsilon3:g}，"
                                      "依人數由多到少）", font_size=20, x=0, xanchor="left"))
    fig.update_xaxes(tickfont_size=17)
    fig.update_yaxes(title="平均年收入（萬元）", zeroline=True, zerolinecolor=COLOR_AXIS)
    st.plotly_chart(fig, width="stretch")

    big, small = release.iloc[0], release.iloc[-1]
    comparison = (f"ε = {epsilon3:g} 時，{big['區']}（{big['人數']:,} 人）誤差 "
                  f"{big['相對誤差']:.1%}，{small['區']}（{small['人數']:,} 人）誤差 "
                  f"{small['相對誤差']:.1%}。")
    if small["相對誤差"] > big["相對誤差"]:
        st.markdown(f"**人越少的區，誤差越大：** {comparison}"
                    "差分隱私適合大群體的統計；要細分到小區域，就得花更多預算或接受更大的誤差。")
    else:
        # ε 很大時雜訊幾乎消失，剩下的誤差主要來自 clip（高所得者被截到 B）
        st.markdown(f"**ε 很大時雜訊幾乎消失：** {comparison}"
                    f"剩下的誤差主要來自 clip——收入超過 {DEFAULT_BOUND // 10_000} 萬的人"
                    "被當成上限計算，高所得者多的區平均會略為偏低。")
