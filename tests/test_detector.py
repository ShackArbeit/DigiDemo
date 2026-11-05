import pandas as pd
import pytest

from demo1.detector import (detect_by_column_name, find_pii, find_rejected_ids,
                            locate_pii, scan_dataframe)
from shared.fake_data import generate_applicants


# --- find_pii：自由文字 -------------------------------------------------------

def test_mobile_in_free_text_with_position():
    text = "聯絡家屬陳大文 0912345678"
    [m] = find_pii(text)
    assert (m.pii_type, m.value) == ("手機", "0912345678")
    assert text[m.start:m.end] == "0912345678"


@pytest.mark.parametrize("text, pii_type, value", [
    ("請改撥家屬手機 0912-345-678", "手機", "0912-345-678"),
    ("請改撥市話 (02)2345-6789", "市話", "(02)2345-6789"),
    ("市話 02-2345-6789 白天可接", "市話", "02-2345-6789"),
    ("補件請寄 test.user@example.com 謝謝", "Email", "test.user@example.com"),
    ("代理人身分證 A123456789", "身分證字號", "A123456789"),
])
def test_each_pii_type_detected(text, pii_type, value):
    [m] = find_pii(text)
    assert (m.pii_type, m.value) == (pii_type, value)


def test_invalid_checksum_id_is_not_pii():
    # 格式相符但檢查碼錯誤 → 不算個資，但會列入「排除」
    text = "案件編號 A123456788，已轉社工追蹤"
    assert find_pii(text) == []
    assert find_rejected_ids(text) == ["A123456788"]


def test_no_match_inside_longer_codes():
    assert find_pii("訂單 XA123456789") == []        # 前面接英文字母
    assert find_pii("序號 091234567890") == []      # 數字太長，不是手機


def test_multiple_pii_in_order():
    text = "代理人 A123456789，手機 0912345678，信箱 a@b.com"
    assert [m.pii_type for m in find_pii(text)] == ["身分證字號", "手機", "Email"]


def test_empty_and_non_string():
    assert find_pii("") == []
    assert find_pii(None) == []


# --- 欄位名稱 -----------------------------------------------------------------

@pytest.mark.parametrize("column, expected", [
    ("姓名", "姓名"), ("申請人姓名", "姓名"), ("地址", "地址"),
    ("生日", "生日"), ("出生日期", "生日"), ("補助金額", None),
])
def test_detect_by_column_name(column, expected):
    assert detect_by_column_name(column) == expected


# --- 整張表 -------------------------------------------------------------------

def test_scan_dataframe_small():
    df = pd.DataFrame({
        "姓名": ["王小明", "李大華", ""],
        "電話": ["0912345678", "無", "(02)2345-6789"],
        "備註": ["案件編號 A123456788", "", "a@b.com"],
    })
    report = scan_dataframe(df).set_index("欄位")

    assert report.loc["姓名", "偵測方式"] == "欄位名稱"
    assert report.loc["姓名", "命中筆數"] == 2              # 空白不算

    assert report.loc["電話", "個資類型"] == "手機、市話"
    assert report.loc["電話", "命中比例"] == pytest.approx(2 / 3)

    assert report.loc["備註", "個資類型"] == "Email"
    assert report.loc["備註", "排除筆數（檢查碼錯誤）"] == 1


def test_scan_generated_applicants():
    report = scan_dataframe(generate_applicants()).set_index("欄位")
    for column in ["身分證字號", "手機", "Email", "姓名", "地址", "生日"]:
        assert report.loc[column, "命中比例"] == 1.0, column
    assert report.loc["補助金額", "命中筆數"] == 0
    assert report.loc["備註", "命中筆數"] > 0
    assert report.loc["備註", "排除筆數（檢查碼錯誤）"] > 0


def test_locate_pii_returns_positions():
    series = pd.Series(["無", "聯絡家屬陳大文 0912345678"])
    located = locate_pii(series)
    assert len(located) == 1
    row = located.iloc[0]
    assert row["列號"] == 1
    assert series[1][row["起始位置"]:row["結束位置"]] == "0912345678"
