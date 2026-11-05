from datetime import date

import pandas as pd
import pytest

from demo1.deidentify import (address_to_district, birthday_to_age_band,
                              deidentify_dataframe, mask_email, mask_id,
                              mask_name, mask_phone, redact_text)
from demo1.detector import find_pii
from demo1.kanon import find_violations, kanon_summary, suppress
from shared.fake_data import generate_applicants


# --- 遮罩 ---------------------------------------------------------------------

def test_mask_id():
    assert mask_id("A123456789") == "A12****789"


@pytest.mark.parametrize("phone", ["0912345678", "0912-345-678"])
def test_mask_phone(phone):
    assert mask_phone(phone) == "0912***678"


@pytest.mark.parametrize("name, expected", [
    ("王小明", "王○明"), ("王明", "王○"), ("歐陽小明", "歐○○明"), ("王", "王"),
])
def test_mask_name(name, expected):
    assert mask_name(name) == expected


def test_mask_email():
    assert mask_email("wang.xm@example.com") == "***@example.com"


# --- 泛化 ---------------------------------------------------------------------

@pytest.mark.parametrize("birthday, expected", [
    ("1961-09-29", "60-69歲"),   # 2026-11-01 時 65 歲
    ("1966-11-01", "60-69歲"),   # 當天生日 → 剛好 60 歲
    ("1966-11-02", "50-59歲"),   # 明天才生日 → 還是 59 歲
])
def test_birthday_to_age_band(birthday, expected):
    assert birthday_to_age_band(birthday, reference=date(2026, 11, 1)) == expected


def test_address_to_district():
    assert address_to_district("臺北市大安區復興南路一段12號3樓") == "臺北市大安區"
    assert address_to_district("新竹縣竹北市光明六路10號") == "新竹縣竹北市"


# --- 自由文字 -----------------------------------------------------------------

def test_redact_text():
    assert redact_text("聯絡家屬陳大文 0912345678") == "聯絡家屬陳大文 [手機]"
    assert (redact_text("代理人 A123456789，信箱 a@b.com，市話 (02)2345-6789")
            == "代理人 [身分證]，信箱 [Email]，市話 [市話]")
    # 檢查碼錯誤的案件編號不是個資，保留原樣
    assert redact_text("案件編號 A123456788") == "案件編號 A123456788"


# --- 整張表 -------------------------------------------------------------------

@pytest.fixture(scope="module")
def applicants():
    return generate_applicants()


@pytest.fixture(scope="module")
def deidentified(applicants):
    return deidentify_dataframe(applicants)


def test_deidentify_dataframe_columns(applicants, deidentified):
    assert "年齡層" in deidentified and "生日" not in deidentified
    assert "居住區" in deidentified and "地址" not in deidentified
    # 未列在規則中的欄位保持不變
    assert deidentified["補助金額"].equals(applicants["補助金額"])
    # 不修改原始資料
    assert applicants["姓名"].iloc[0] != deidentified["姓名"].iloc[0]


def test_no_pii_left_after_deidentify(deidentified):
    for column in deidentified.columns:
        leaked = deidentified[column].astype(str).map(find_pii).map(len).sum()
        assert leaked == 0, f"{column} 仍有個資"


def test_drop_rule():
    df = pd.DataFrame({"姓名": ["王小明"], "性別": ["男"]})
    result = deidentify_dataframe(df, rules={"姓名": ("drop", "姓名")})
    assert list(result.columns) == ["性別"]


def test_generated_ages_match_subsidy_item(deidentified):
    elderly = deidentified[deidentified["申請項目"] == "中低收入老人生活津貼"]
    assert elderly["年齡層"].str[:2].astype(int).min() >= 60


# --- k-匿名 -------------------------------------------------------------------

@pytest.fixture
def small_df():
    # 群組：(A,男) 3 人、(A,女) 2 人、(B,男) 1 人
    return pd.DataFrame({
        "年齡層": ["A", "A", "A", "A", "A", "B"],
        "性別": ["男", "男", "男", "女", "女", "男"],
        "居住區": ["X"] * 6,
    })


def test_find_violations(small_df):
    v = find_violations(small_df, k=3)
    assert len(v) == 3
    assert list(v["群組人數"]) == [1, 2, 2]


def test_kanon_summary(small_df):
    s = kanon_summary(small_df, k=3)
    assert s["群組數"] == 3
    assert s["不滿足k的群組數"] == 2          # (A,女) 2 人、(B,男) 1 人
    assert s["不滿足k的紀錄數"] == 3
    assert s["可唯一識別的紀錄數"] == 1
    assert s["實際k值"] == 1


def test_suppress(small_df):
    kept, loss = suppress(small_df, k=3)
    assert len(kept) == 3
    assert loss == pytest.approx(0.5)
    assert kanon_summary(kept, k=3)["不滿足k的紀錄數"] == 0


def test_larger_k_means_more_violations(deidentified):
    counts = [kanon_summary(deidentified, k)["不滿足k的紀錄數"] for k in range(2, 11)]
    assert counts == sorted(counts)
    assert counts[0] > 0
