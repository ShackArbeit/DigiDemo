"""
個資偵測器

兩種偵測方式：
1. 內容比對：用正規表達式找身分證字號、手機、市話、Email（身分證另外驗證檢查碼）
2. 欄位名稱：姓名、地址、生日很難用規則從內容判斷，改看欄位名稱（不做 NLP）
"""

import re
from dataclasses import dataclass

import pandas as pd

from shared.fake_data import is_valid_tw_id

# ---------------------------------------------------------------------------
# 規則定義
# ---------------------------------------------------------------------------

# 內容比對規則。(?<!...) / (?!...) 確保前後不是英數字，避免從較長的編號中切出一段
CONTENT_PATTERNS = {
    "身分證字號": re.compile(r"(?<![A-Za-z0-9])[A-Z][12]\d{8}(?!\d)"),
    # 手機：09 開頭 10 碼，可有橫線（0912-345-678）
    "手機": re.compile(r"(?<!\d)09\d{2}-?\d{3}-?\d{3}(?!\d)"),
    # 市話：(02)2345-6789 或 02-2345-6789；區碼 02～08，不會跟 09 手機重疊
    "市話": re.compile(r"(?<!\d)(?:\(0[2-8]\d?\)|0[2-8]\d?-)\s?\d{3,4}-?\d{4}(?!\d)"),
    "Email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
}

# 欄位名稱規則：欄位名稱包含這些關鍵字，就整欄視為該類個資
COLUMN_NAME_RULES = {
    "姓名": ["姓名", "名字", "name"],
    "地址": ["地址", "住址", "address"],
    "生日": ["生日", "出生", "birth"],
}


@dataclass
class PiiMatch:
    """一筆偵測結果：類型、命中的文字、在原字串中的起訖位置。"""
    pii_type: str
    value: str
    start: int
    end: int


# ---------------------------------------------------------------------------
# 單一字串
# ---------------------------------------------------------------------------

def find_pii(text: str) -> list[PiiMatch]:
    """
    找出一段文字中所有的個資位置（依出現順序）。
    身分證字號格式相符、但檢查碼錯誤的，不算個資。
    """
    if not isinstance(text, str) or not text:
        return []

    matches = []
    for pii_type, pattern in CONTENT_PATTERNS.items():
        for m in pattern.finditer(text):
            if pii_type == "身分證字號" and not is_valid_tw_id(m.group()):
                continue
            matches.append(PiiMatch(pii_type, m.group(), m.start(), m.end()))

    # 依位置排序；若兩個結果重疊，保留先出現的那個
    matches.sort(key=lambda m: m.start)
    result = []
    for m in matches:
        if result and m.start < result[-1].end:
            continue
        result.append(m)
    return result


def find_rejected_ids(text: str) -> list[str]:
    """找出「格式像身分證、但檢查碼錯誤」而被排除的字串（展示用：說明減少了多少誤判）。"""
    if not isinstance(text, str):
        return []
    return [s for s in CONTENT_PATTERNS["身分證字號"].findall(text) if not is_valid_tw_id(s)]


# ---------------------------------------------------------------------------
# 欄位與整張表
# ---------------------------------------------------------------------------

def detect_by_column_name(column: str) -> str | None:
    """依欄位名稱判斷個資類型；判斷不出來回傳 None。"""
    lowered = column.lower()
    for pii_type, keywords in COLUMN_NAME_RULES.items():
        if any(k.lower() in lowered for k in keywords):
            return pii_type
    return None


def scan_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    對每個欄位輸出偵測摘要：
    偵測方式、個資類型、命中筆數、命中比例、因檢查碼錯誤而排除的筆數。
    命中比例的分母是總筆數（含空白格）。
    """
    total = len(df)
    rows = []
    for column in df.columns:
        values = df[column].fillna("").astype(str)

        name_type = detect_by_column_name(column)
        if name_type:
            hits = int((values.str.strip() != "").sum())
            rows.append({
                "欄位": column, "偵測方式": "欄位名稱", "個資類型": name_type,
                "命中筆數": hits, "命中比例": hits / total if total else 0.0,
                "排除筆數（檢查碼錯誤）": 0,
            })
            continue

        cell_matches = values.map(find_pii)
        hit_rows = int((cell_matches.map(len) > 0).sum())

        # 統計各類型出現次數，依次數多到少排列
        type_counts: dict[str, int] = {}
        for ms in cell_matches:
            for m in ms:
                type_counts[m.pii_type] = type_counts.get(m.pii_type, 0) + 1
        types = sorted(type_counts, key=type_counts.get, reverse=True)

        rejected_rows = int((values.map(find_rejected_ids).map(len) > 0).sum())

        rows.append({
            "欄位": column,
            "偵測方式": "內容比對" if types else "—",
            "個資類型": "、".join(types) if types else "未偵測到",
            "命中筆數": hit_rows,
            "命中比例": hit_rows / total if total else 0.0,
            "排除筆數（檢查碼錯誤）": rejected_rows,
        })
    return pd.DataFrame(rows)


def locate_pii(series: pd.Series) -> pd.DataFrame:
    """
    針對自由文字欄位（例如「備註」），列出每格裡每一個個資的位置。
    回傳欄位：列號、個資類型、內容、起始位置、結束位置。
    """
    records = []
    for row_index, text in series.items():
        for m in find_pii(text):
            records.append({
                "列號": row_index, "個資類型": m.pii_type, "內容": m.value,
                "起始位置": m.start, "結束位置": m.end,
            })
    return pd.DataFrame(records, columns=["列號", "個資類型", "內容", "起始位置", "結束位置"])
