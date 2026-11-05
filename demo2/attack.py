"""
差分攻擊（differencing attack）示範

情境：統計單位只發布「平均收入」和「人數」，看起來沒有發布任何個人資料。
但攻擊者若能查詢兩次——
  查詢 A：某區全部居民的平均收入（n 人）
  查詢 B：同一區「排除某人」後的平均收入（n-1 人）
就能反推那個人的收入：
  某人收入 = A 的總和 - B 的總和 = 平均A × n - 平均B × (n-1)

「排除某人」在現實中常常不需要明講，例如：
「本月 vs 上月（他剛搬走）」「全體員工 vs 不含主管」「全部 vs 年資滿 1 年者」。
"""

from typing import Callable

import numpy as np
import pandas as pd

# 平均值查詢函式：輸入一串收入，回傳發布的平均值。
# 預設是「精確平均」；Demo 2-B 會換成加入雜訊的差分隱私版本，攻擊流程完全不用改。
MeanQuery = Callable[[np.ndarray], float]


def exact_mean(values: np.ndarray) -> float:
    return float(np.mean(values))


def query_district_mean(df: pd.DataFrame, district: str, exclude_id: int | None = None,
                        mean_query: MeanQuery = exact_mean) -> tuple[float, int]:
    """
    統計查詢：回傳 (平均收入, 人數)。
    exclude_id 有值時，排除該 id 後再計算。
    """
    rows = df[df["區"] == district]
    if exclude_id is not None:
        rows = rows[rows["id"] != exclude_id]
    values = rows["年收入"].to_numpy(dtype=float)
    return mean_query(values), len(values)


def differencing_attack(df: pd.DataFrame, target_id: int,
                        mean_query: MeanQuery = exact_mean) -> dict:
    """
    對 target_id 執行差分攻擊，回傳攻擊過程與結果。
    攻擊者只需要知道目標住在哪一區（這在現實中很容易知道）。
    """
    target = df[df["id"] == target_id]
    if target.empty:
        raise ValueError(f"找不到 id={target_id}")
    district = target["區"].iloc[0]
    actual = float(target["年收入"].iloc[0])

    mean_a, n_a = query_district_mean(df, district, mean_query=mean_query)
    mean_b, n_b = query_district_mean(df, district, exclude_id=target_id, mean_query=mean_query)

    inferred = mean_a * n_a - mean_b * n_b
    return {
        "目標id": target_id,
        "區": district,
        "查詢A_平均": mean_a,
        "查詢A_人數": n_a,
        "查詢B_平均": mean_b,
        "查詢B_人數": n_b,
        "推算收入": inferred,
        "真實收入": actual,
        "誤差": inferred - actual,
        "相對誤差": abs(inferred - actual) / actual,
    }
