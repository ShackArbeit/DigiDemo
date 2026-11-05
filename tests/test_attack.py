import numpy as np
import pytest

from demo2.attack import differencing_attack, query_district_mean
from shared.fake_data import INCOME_DISTRICTS, generate_incomes


@pytest.fixture(scope="module")
def incomes():
    return generate_incomes()


# --- 假資料 -------------------------------------------------------------------

def test_incomes_shape(incomes):
    assert len(incomes) == 5000
    assert list(incomes.columns) == ["id", "區", "年收入"]
    assert incomes["id"].is_unique
    assert (incomes["年收入"] > 0).all()


def test_district_sizes(incomes):
    counts = incomes["區"].value_counts()
    for district, (count, _median) in INCOME_DISTRICTS.items():
        assert counts[district] == count


def test_incomes_right_skewed(incomes):
    # 右偏：平均數 > 中位數
    assert incomes["年收入"].mean() > incomes["年收入"].median()


def test_incomes_reproducible():
    assert generate_incomes(seed=1).equals(generate_incomes(seed=1))


# --- 差分攻擊 -----------------------------------------------------------------

def test_query_excludes_target(incomes):
    target = incomes.iloc[0]
    _, n_all = query_district_mean(incomes, target["區"])
    _, n_excl = query_district_mean(incomes, target["區"], exclude_id=target["id"])
    assert n_excl == n_all - 1


@pytest.mark.parametrize("row", [0, 1, 42, 4999])
def test_attack_recovers_exact_income(incomes, row):
    target_id = int(incomes.iloc[row]["id"])
    result = differencing_attack(incomes, target_id)
    # 推算結果與真實收入一致（只差浮點運算誤差，小於 1 元）
    assert result["推算收入"] == pytest.approx(result["真實收入"], abs=1)


def test_attack_works_on_every_district(incomes):
    for district in INCOME_DISTRICTS:
        target_id = int(incomes[incomes["區"] == district]["id"].iloc[0])
        assert differencing_attack(incomes, target_id)["相對誤差"] < 1e-6


def test_attack_on_highest_earner(incomes):
    # 收入最高的人最怕被知道，攻擊一樣有效
    target_id = int(incomes.loc[incomes["年收入"].idxmax(), "id"])
    result = differencing_attack(incomes, target_id)
    assert result["推算收入"] == pytest.approx(result["真實收入"], abs=1)


def test_attack_accepts_custom_query(incomes):
    # 換成加雜訊的查詢後，推算結果就不再精確（2-B 差分隱私的預告）
    rng = np.random.default_rng(0)
    noisy = lambda v: float(np.mean(v) + rng.laplace(0, 5000))  # noqa: E731
    result = differencing_attack(incomes, 1, mean_query=noisy)
    assert abs(result["誤差"]) > 1000


def test_unknown_target_raises(incomes):
    with pytest.raises(ValueError):
        differencing_attack(incomes, 999_999)
