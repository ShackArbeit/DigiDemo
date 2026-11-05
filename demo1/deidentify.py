"""
去識別化：遮罩、泛化、自由文字標籤替換、刪除

- 遮罩（mask）：保留部分字元，其餘以符號取代 → 還看得出「是哪種資料」，但看不出是誰
- 泛化（generalize）：把精確值變成較粗的分類 → 生日變年齡層、地址只留到區
- 標籤替換（redact）：自由文字中的個資換成 [手機] 等標籤
- 刪除（drop）：整欄移除
"""

import re
from datetime import date

import pandas as pd

from demo1.detector import find_pii
from shared.fake_data import REFERENCE_DATE

# ---------------------------------------------------------------------------
# 遮罩
# ---------------------------------------------------------------------------

def mask_id(id_number: str) -> str:
    """身分證：A123456789 → A12****789（保留前 3、後 3 碼）。"""
    if len(id_number) != 10:
        return id_number
    return id_number[:3] + "****" + id_number[-3:]


def mask_phone(phone: str) -> str:
    """手機：0912345678 或 0912-345-678 → 0912***678（先去掉橫線再遮罩）。"""
    digits = re.sub(r"\D", "", phone)
    if len(digits) != 10:
        return phone
    return digits[:4] + "***" + digits[-3:]


def mask_name(name: str) -> str:
    """姓名：王小明 → 王○明；王明 → 王○；歐陽小明 → 歐○○明（保留第一個與最後一個字）。"""
    if len(name) <= 1:
        return name
    if len(name) == 2:
        return name[0] + "○"
    return name[0] + "○" * (len(name) - 2) + name[-1]


def mask_email(email: str) -> str:
    """Email：只留網域 → ***@example.com。"""
    if "@" not in email:
        return email
    return "***@" + email.split("@", 1)[1]


# ---------------------------------------------------------------------------
# 泛化
# ---------------------------------------------------------------------------

def birthday_to_age_band(birthday: str, reference: date = REFERENCE_DATE) -> str:
    """生日 → 10 歲一組的年齡層，例如 1961-09-29 → 60-69歲。"""
    born = date.fromisoformat(birthday)
    had_birthday = (reference.month, reference.day) >= (born.month, born.day)
    age = reference.year - born.year - (0 if had_birthday else 1)
    low = age // 10 * 10
    return f"{low}-{low + 9}歲"


def address_to_district(address: str) -> str:
    """地址 → 只留到區：臺北市大安區復興南路一段12號3樓 → 臺北市大安區。"""
    m = re.match(r"^(.+?[市縣])(.+?[區鄉鎮市])", address)
    return m.group(0) if m else address


# ---------------------------------------------------------------------------
# 自由文字
# ---------------------------------------------------------------------------

PII_LABELS = {"身分證字號": "[身分證]", "手機": "[手機]", "市話": "[市話]", "Email": "[Email]"}


def redact_text(text: str) -> str:
    """把自由文字中偵測到的個資換成標籤：聯絡家屬陳大文 0912345678 → 聯絡家屬陳大文 [手機]。"""
    # 從後往前替換，前面的位置才不會因為字串長度改變而跑掉
    for m in reversed(find_pii(text)):
        text = text[:m.start] + PII_LABELS[m.pii_type] + text[m.end:]
    return text


# ---------------------------------------------------------------------------
# 整張表
# ---------------------------------------------------------------------------

# 每個欄位的處理方式：(動作, 處理後的欄位名稱)
# 動作可以是 "mask_id" 等函式名稱、"drop"（刪除整欄）；沒列出的欄位保持不變
DEFAULT_RULES = {
    "姓名": ("mask_name", "姓名"),
    "身分證字號": ("mask_id", "身分證字號"),
    "生日": ("age_band", "年齡層"),
    "手機": ("mask_phone", "手機"),
    "Email": ("mask_email", "Email"),
    "地址": ("district", "居住區"),
    "備註": ("redact", "備註"),
}

ACTIONS = {
    "mask_name": mask_name,
    "mask_id": mask_id,
    "mask_phone": mask_phone,
    "mask_email": mask_email,
    "age_band": birthday_to_age_band,
    "district": address_to_district,
    "redact": redact_text,
}


def deidentify_dataframe(df: pd.DataFrame, rules: dict | None = None) -> pd.DataFrame:
    """依規則對每個欄位做去識別化，回傳新的 DataFrame（不修改原始資料）。"""
    rules = DEFAULT_RULES if rules is None else rules
    result = pd.DataFrame(index=df.index)
    for column in df.columns:
        if column not in rules:
            result[column] = df[column]
            continue
        action, new_name = rules[column]
        if action == "drop":
            continue
        func = ACTIONS[action]
        # 空白格不處理，避免把 "" 變成奇怪的結果
        result[new_name] = df[column].map(lambda v: func(v) if isinstance(v, str) and v else v)
    return result
