import pandas as pd
import pytest

from app.strategy.indicators import atr, ema, rsi


def test_ema_matches_manual_calculation():
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = ema(series, period=3)

    # alpha = 2/(3+1) = 0.5, seeded with the first value
    expected = [1.0, 1.5, 2.25, 3.125, 4.0625]
    assert result.tolist() == pytest.approx(expected)


def test_rsi_is_100_when_price_only_rises():
    series = pd.Series(range(1, 40), dtype=float)
    assert rsi(series, period=14).iloc[-1] == pytest.approx(100.0)


def test_rsi_is_zero_when_price_only_falls():
    series = pd.Series(range(40, 1, -1), dtype=float)
    assert rsi(series, period=14).iloc[-1] == pytest.approx(0.0)


def test_rsi_is_neutral_on_a_flat_market():
    series = pd.Series([100.0] * 40)
    assert rsi(series, period=14).iloc[-1] == pytest.approx(50.0)


def test_rsi_stays_nan_during_warmup():
    series = pd.Series(range(1, 10), dtype=float)
    assert rsi(series, period=14).isna().all()


def test_atr_of_constant_range_equals_that_range():
    frame = pd.DataFrame(
        {
            "high": [11.0] * 40,
            "low": [9.0] * 40,
            "close": [10.0] * 40,
        }
    )
    assert atr(frame, period=14).iloc[-1] == pytest.approx(2.0)
