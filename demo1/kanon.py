"""
k-匿名檢查

概念：把「準識別欄位」（單獨不能識別、組合起來可能識別出一個人的欄位）相同的人分成一組。
若每一組都至少有 k 人，就稱為滿足 k-匿名：攻擊者最多只能把目標縮小到 k 人之中。
"""

import pandas as pd

# 預設準識別欄位：去識別化後的年齡層、性別、居住區
DEFAULT_QUASI_IDENTIFIERS = ["年齡層", "性別", "居住區"]


def group_sizes(df: pd.DataFrame, quasi_identifiers: list[str]) -> pd.Series:
    """每筆紀錄所在群組的人數（與 df 同樣的列順序）。"""
    return df.groupby(quasi_identifiers)[quasi_identifiers[0]].transform("size")


def find_violations(df: pd.DataFrame, k: int,
                    quasi_identifiers: list[str] = DEFAULT_QUASI_IDENTIFIERS) -> pd.DataFrame:
    """回傳群組人數 < k 的紀錄，並加上「群組人數」欄位，依人數由少到多排序。"""
    sizes = group_sizes(df, quasi_identifiers)
    violations = df[sizes < k].copy()
    violations["群組人數"] = sizes[sizes < k]
    return violations.sort_values(["群組人數", *quasi_identifiers])


def kanon_summary(df: pd.DataFrame, k: int,
                  quasi_identifiers: list[str] = DEFAULT_QUASI_IDENTIFIERS) -> dict:
    """
    風險摘要（給介面顯示用）：
    - 總筆數、群組數、不滿足 k 的群組數
    - 不滿足 k 的紀錄數與比例
    - 可被唯一識別的紀錄數（群組只有自己一人）
    - 目前資料實際達到的 k 值（最小群組人數）
    """
    sizes = group_sizes(df, quasi_identifiers)
    total = len(df)
    violating = int((sizes < k).sum())
    groups = df.groupby(quasi_identifiers).size()
    return {
        "總筆數": total,
        "群組數": int(len(groups)),
        "不滿足k的群組數": int((groups < k).sum()),
        "不滿足k的紀錄數": violating,
        "不滿足k的比例": violating / total if total else 0.0,
        "可唯一識別的紀錄數": int((sizes == 1).sum()),
        "實際k值": int(sizes.min()) if total else 0,
    }


def suppress(df: pd.DataFrame, k: int,
             quasi_identifiers: list[str] = DEFAULT_QUASI_IDENTIFIERS) -> tuple[pd.DataFrame, float]:
    """
    抑制：直接移除不滿足 k 的紀錄。
    回傳 (保留下來的資料, 資料損失比例)。
    """
    sizes = group_sizes(df, quasi_identifiers)
    kept = df[sizes >= k]
    loss = 1 - len(kept) / len(df) if len(df) else 0.0
    return kept, loss
