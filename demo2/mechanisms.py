"""
差分隱私：Laplace 機制（只用 numpy 自己實作，不用外部差分隱私套件）

核心想法：發布統計數字前，先加入「刻意設計過大小」的隨機雜訊，
讓「資料庫裡有你」和「沒有你」的發布結果幾乎分不出來。

平均收入的作法：
1. 收入先 clip 到 [0, B]：限制任何一個人對結果的最大影響
2. 敏感度 = B / n：換掉一個人，平均值最多改變 B / n
3. 雜訊 ~ Laplace(0, 敏感度 / ε)：ε 越小，雜訊越大，隱私越強
"""

from typing import Callable

import numpy as np
import pandas as pd

from demo2.attack import differencing_attack

DEFAULT_BOUND = 3_000_000  # B：收入上限 300 萬


def clip_values(values: np.ndarray, bound: float = DEFAULT_BOUND) -> np.ndarray:
    """
    把收入限制在 [0, B]：超過 B 的一律當作 B。
    為什麼要 clip：如果收入沒有上限，一位億萬富翁就能讓平均值大幅改變，
    敏感度變成無限大，需要的雜訊也無限大。clip 之後，每個人的影響都有上限。
    """
    return np.clip(values, 0, bound)


def mean_sensitivity(n: int, bound: float = DEFAULT_BOUND) -> float:
    """平均值的敏感度：n 人中換掉一個人，平均值最多改變 B / n。"""
    return bound / n


def laplace_noise(scale: float, rng: np.random.Generator, size: int | None = None):
    """Laplace(0, scale) 雜訊：以 0 為中心、兩側對稱的尖峰分布。scale 越大，雜訊越大。"""
    return rng.laplace(loc=0.0, scale=scale, size=size)


def dp_mean(values: np.ndarray, epsilon: float, bound: float = DEFAULT_BOUND,
            rng: np.random.Generator | None = None) -> float:
    """
    差分隱私平均值：clip → 計算平均 → 加入 Laplace(0, (B/n)/ε) 雜訊。
    假設人數 n 是公開資訊（統計報表通常會公布樣本數）。
    """
    if epsilon <= 0:
        raise ValueError("ε 必須大於 0")
    values = np.asarray(values, dtype=float)
    n = len(values)
    if n == 0:
        raise ValueError("沒有資料，無法計算平均")
    rng = rng or np.random.default_rng()

    true_mean = clip_values(values, bound).mean()
    scale = mean_sensitivity(n, bound) / epsilon
    return float(true_mean + laplace_noise(scale, rng))


def make_dp_query(epsilon: float, bound: float = DEFAULT_BOUND,
                  rng: np.random.Generator | None = None) -> Callable[[np.ndarray], float]:
    """包成 attack.py 用的查詢函式，讓同一套攻擊流程可以直接換成差分隱私版本。"""
    rng = rng or np.random.default_rng()
    return lambda values: dp_mean(values, epsilon, bound, rng)


def attack_with_dp(df: pd.DataFrame, target_id: int, epsilon: float,
                   bound: float = DEFAULT_BOUND, rng: np.random.Generator | None = None) -> dict:
    """
    對差分隱私發布的統計數字做同樣的差分攻擊。
    注意：攻擊做了 2 次查詢，總共消耗 2ε 的隱私預算。
    """
    return differencing_attack(df, target_id, mean_query=make_dp_query(epsilon, bound, rng))


def attack_error_by_epsilon(df: pd.DataFrame, target_id: int, epsilons, trials: int = 200,
                            bound: float = DEFAULT_BOUND, seed: int = 2026) -> pd.DataFrame:
    """對每個 ε 重複攻擊 trials 次，回傳攻擊推算值的平均絕對誤差（元）。"""
    rng = np.random.default_rng(seed)
    rows = []
    for eps in epsilons:
        errors = [abs(attack_with_dp(df, target_id, eps, bound, rng)["誤差"]) for _ in range(trials)]
        rows.append({"ε": eps, "攻擊平均誤差": float(np.mean(errors))})
    return pd.DataFrame(rows)


def tradeoff_curve(df: pd.DataFrame, epsilons=None, trials: int = 200,
                   bound: float = DEFAULT_BOUND, seed: int = 2026) -> pd.DataFrame:
    """
    取捨曲線：對每個 ε，把「各區平均收入」用差分隱私發布 trials 次，
    計算相對誤差 |發布值 - 真實平均| / 真實平均 的平均。

    回傳寬表：每列一個 ε；欄位為各區的平均相對誤差，以及「全部平均」。
    真實平均用「未 clip 的原始平均」，所以誤差也包含 clip 造成的偏差（這是真實的代價）。
    """
    if epsilons is None:
        epsilons = np.logspace(-2, 1, 31)   # 0.01 ～ 10，對數等距 31 個點
    rng = np.random.default_rng(seed)

    districts = {name: group["年收入"].to_numpy(dtype=float)
                 for name, group in df.groupby("區", sort=False)}
    rows = []
    for eps in epsilons:
        row = {"ε": float(eps)}
        for name, values in districts.items():
            true_mean = values.mean()
            clipped_mean = clip_values(values, bound).mean()
            scale = mean_sensitivity(len(values), bound) / eps
            # 一次產生 trials 個雜訊（向量化，比迴圈呼叫 dp_mean 快很多，結果在統計上相同）
            released = clipped_mean + laplace_noise(scale, rng, size=trials)
            row[name] = float(np.mean(np.abs(released - true_mean)) / true_mean)
        row["全部平均"] = float(np.mean([row[name] for name in districts]))
        rows.append(row)
    return pd.DataFrame(rows)
