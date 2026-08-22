from signal_checklist import evaluate_checklist


def test_entry_setup_requires_all_observable_checks():
    result = evaluate_checklist("gold", {
        "above_sma20": True,
        "return_5d_pct": 2.0,
        "volume_ratio_20d": 1.4,
        "rsi14": 61,
    }, {
        "gold": {"return_5d_pct": 1.2},
        "dollar": {"return_5d_pct": -0.3},
    })
    assert result["passed"] == 5
    assert result["status"] == "ENTRY SETUP READY"


def test_extended_setup_is_not_labeled_ready():
    result = evaluate_checklist("energy", {
        "above_sma20": True,
        "return_5d_pct": 2.0,
        "volume_ratio_20d": 1.4,
        "rsi14": 77,
    }, {
        "oil": {"return_5d_pct": 1.2},
        "dollar": {"return_5d_pct": -0.3},
    })
    assert result["status"] == "EXTENDED"
