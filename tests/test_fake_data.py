import random

import pytest

from shared.fake_data import generate_tw_id, is_valid_tw_id


# --- 驗證函式 ---------------------------------------------------------------

def test_known_valid_id_passes():
    # A123456789 是常見的教科書範例，加權總和 = 130
    assert is_valid_tw_id("A123456789")


@pytest.mark.parametrize("bad", [
    "A123456788",   # 檢查碼錯誤
    "a123456789",   # 小寫字母
    "A323456789",   # 第 2 碼不是 1 或 2
    "A12345678",    # 少一碼
    "A1234567890",  # 多一碼
    "1123456789",   # 開頭不是字母
    "",
    None,
])
def test_invalid_ids_fail(bad):
    assert not is_valid_tw_id(bad)


# --- 產生函式 ---------------------------------------------------------------

def test_generated_ids_are_valid():
    rng = random.Random(42)
    for _ in range(1000):
        assert is_valid_tw_id(generate_tw_id(rng))


def test_changing_one_digit_makes_id_invalid():
    """把任一位數字 +1（9 變 0），檢查碼就必定失敗。"""
    rng = random.Random(42)
    for _ in range(200):
        id_number = generate_tw_id(rng)
        for pos in range(1, 10):
            new_digit = str((int(id_number[pos]) + 1) % 10)
            tampered = id_number[:pos] + new_digit + id_number[pos + 1:]
            assert not is_valid_tw_id(tampered), f"{id_number} → {tampered}"


def test_gender_and_letter_options():
    rng = random.Random(1)
    male = generate_tw_id(rng, gender="M", letter="A")
    female = generate_tw_id(rng, gender="F", letter="A")
    assert male.startswith("A1") and is_valid_tw_id(male)
    assert female.startswith("A2") and is_valid_tw_id(female)


def test_same_seed_gives_same_ids():
    ids_a = [generate_tw_id(random.Random(7)) for _ in range(5)]
    ids_b = [generate_tw_id(random.Random(7)) for _ in range(5)]
    assert ids_a == ids_b


# --- 社福補助申請名冊 ---------------------------------------------------------

from shared.fake_data import CITY, DISTRICT_WEIGHTS, generate_applicants  # noqa: E402

EXPECTED_COLUMNS = ["姓名", "身分證字號", "性別", "生日", "手機", "Email",
                    "地址", "申請項目", "補助金額", "備註"]


@pytest.fixture(scope="module")
def applicants():
    return generate_applicants(n=500, seed=2026)


def test_applicants_shape_and_columns(applicants):
    assert len(applicants) == 500
    assert list(applicants.columns) == EXPECTED_COLUMNS


def test_applicant_ids_valid_unique_and_match_gender(applicants):
    assert applicants["身分證字號"].map(is_valid_tw_id).all()
    assert applicants["身分證字號"].is_unique
    gender_digit = applicants["身分證字號"].str[1]
    assert ((gender_digit == "1") == (applicants["性別"] == "男")).all()


def test_addresses_in_one_city_few_districts(applicants):
    assert applicants["地址"].str.startswith(CITY).all()
    districts = applicants["地址"].str.extract(rf"{CITY}(\S+?區)")[0]
    assert set(districts) == set(DISTRICT_WEIGHTS)


def test_notes_contain_free_text_pii(applicants):
    notes = applicants["備註"]
    assert notes.str.contains(r"09\d{2}-?\d{3}-?\d{3}").any()   # 手機
    assert notes.str.contains(r"\(02\)").any()                  # 市話
    assert notes.str.contains("@").any()                         # Email
    assert (notes == "").mean() > 0.4                            # 多數空白


def test_applicants_reproducible():
    a = generate_applicants(n=50, seed=99)
    b = generate_applicants(n=50, seed=99)
    assert a.equals(b)


def test_csv_roundtrip_keeps_leading_zero(tmp_path):
    from shared.fake_data import load_applicants, save_applicants_csv
    path = save_applicants_csv(tmp_path / "a.csv", n=20, seed=1)
    df = load_applicants(path)
    assert df["手機"].str.match(r"^09\d{8}$").all()
