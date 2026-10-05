from app import edition
from app.config import AppConfig, RiskConfig


def test_pro_limits_lower_a_risky_config_and_never_raise_one():
    risk = RiskConfig(risk_per_trade_pct=5.0, max_daily_loss_pct=20.0, max_open_positions=12, max_position_pct=80.0)
    changed = edition.clamp_risk(risk, edition.LIMITS["pro"])
    assert risk.risk_per_trade_pct == 1.0 and risk.max_daily_loss_pct == 3.0
    assert risk.max_open_positions == 5 and risk.max_position_pct == 25.0
    assert len(changed) == 4

    careful = RiskConfig(risk_per_trade_pct=0.25, max_daily_loss_pct=1.0, max_open_positions=1, max_position_pct=5.0)
    assert edition.clamp_risk(careful, edition.LIMITS["pro"]) == []
    assert careful.risk_per_trade_pct == 0.25


def test_personal_copy_has_no_caps():
    risk = RiskConfig(risk_per_trade_pct=5.0, max_daily_loss_pct=20.0)
    assert edition.clamp_risk(risk, edition.LIMITS["personal"]) == []
    assert edition.LIMITS["personal"].telegram and not edition.LIMITS["pro"].telegram
    assert edition.LIMITS["pro"].max_bots < edition.LIMITS["personal"].max_bots


def test_running_from_source_is_the_personal_copy():
    assert edition.NAME == "personal" and not edition.PRO


def test_an_old_midas_config_starts_on_practice_money():
    assert AppConfig(mode="signal").mode == "paper"
