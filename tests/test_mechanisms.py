import numpy as np
import pytest

from demo2.attack import differencing_attack
from demo2.mechanisms import (DEFAULT_BOUND, attack_error_by_epsilon, attack_with_dp,
                              clip_values, dp_mean, mean_sensitivity, tradeoff_curve)
from shared.fake_data import INCOME_DISTRICTS, generate_incomes


@pytest.fixture(scope="module")
def incomes():
    return generate_incomes()


# --- 基本元件 -----------------------------------------------------------------

def test_clip_values():
    values = np.array([-100, 500_000, 3_000_000, 8_000_000])
    assert list(clip_values(values)) == [0, 500_000, 3_000_000, 3_000_000]


def test_mean_sensitivity():
    assert mean_sensitivity(100) == DEFAULT_BOUND / 100


def test_clip_bounds_one_person_effect():
    """clip 之後，把任一個人換成任意收入，平均值的變化都不超過 B / n。"""
    rng = np.random.default_rng(0)
    values = rng.lognormal(13, 0.65, size=200)
    base = clip_values(values).mean()
    for extreme in [0, 1e9]:
        changed = values.copy()
        changed[0] = extreme
        assert abs(clip_values(changed).mean() - base) <= mean_sensitivity(200) + 1e-6


def test_dp_mean_invalid_input():
    with pytest.raises(ValueError):
        dp_mean([1, 2, 3], epsilon=0)
    with pytest.raises(ValueError):
        dp_mean([], epsilon=1)


def test_dp_mean_reproducible_with_seed():
    values = np.full(100, 500_000.0)
    a = dp_mean(values, 1.0, rng=np.random.default_rng(7))
    b = dp_mean(values, 1.0, rng=np.random.default_rng(7))
    assert a == b


def test_dp_mean_noise_scale_matches_theory():
    """Laplace(0, b) 的平均絕對值 = b，其中 b = (B/n)/ε。"""
    values = np.full(100, 500_000.0)
    rng = np.random.default_rng(1)
    eps = 0.5
    noise = np.array([dp_mean(values, eps, rng=rng) for _ in range(20_000)]) - 500_000
    expected_scale = DEFAULT_BOUND / 100 / eps
    assert np.mean(np.abs(noise)) == pytest.approx(expected_scale, rel=0.03)
    assert np.mean(noise) == pytest.approx(0, abs=expected_scale * 0.05)   # 無偏


# --- 同樣的攻擊，加上差分隱私 -------------------------------------------------

def test_attack_fails_with_dp(incomes):
    target_id = int(incomes[incomes["區"] == "港區"]["id"].iloc[0])
    exact = differencing_attack(incomes, target_id)
    assert abs(exact["誤差"]) < 1                      # 沒有 DP：精確推算

    errors = [abs(attack_with_dp(incomes, target_id, 1.0, rng=np.random.default_rng(s))["誤差"])
              for s in range(200)]
    # 有 DP（ε=1）：兩次查詢的雜訊各被放大 n 倍，推算誤差平均達數百萬元，遠大於一般人的收入
    assert np.mean(errors) > 1_000_000


def test_attack_error_shrinks_as_epsilon_grows(incomes):
    result = attack_error_by_epsilon(incomes, 1, [0.1, 1, 10], trials=100)
    errors = list(result["攻擊平均誤差"])
    assert errors[0] > errors[1] > errors[2]


def test_repeated_queries_leak_privacy():
    """隱私預算為什麼會被消耗：同一個問題問很多次再取平均，雜訊會被抵消。"""
    values = np.full(100, 500_000.0)
    rng = np.random.default_rng(3)
    one = [abs(dp_mean(values, 1.0, rng=rng) - 500_000) for _ in range(500)]
    avg_of_100 = [abs(np.mean([dp_mean(values, 1.0, rng=rng) for _ in range(100)]) - 500_000)
                  for _ in range(500)]
    # 問 100 次取平均，誤差約縮小為 1/√100 = 1/10
    assert np.mean(avg_of_100) < np.mean(one) / 5


# --- 取捨曲線 -----------------------------------------------------------------

def test_tradeoff_curve_shape(incomes):
    curve = tradeoff_curve(incomes)
    assert len(curve) == 31
    assert curve["ε"].iloc[0] == pytest.approx(0.01)
    assert curve["ε"].iloc[-1] == pytest.approx(10)
    assert set(INCOME_DISTRICTS) | {"ε", "全部平均"} == set(curve.columns)


def test_tradeoff_error_decreases_with_epsilon(incomes):
    curve = tradeoff_curve(incomes, epsilons=[0.01, 0.1, 1, 10])
    errors = list(curve["全部平均"])
    assert errors == sorted(errors, reverse=True)


def test_small_district_has_larger_error(incomes):
    curve = tradeoff_curve(incomes, epsilons=[0.5])
    assert curve["山腳區"].iloc[0] > curve["中區"].iloc[0]
