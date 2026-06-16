import pytest

from app.core.intent import GLOBAL_DIMS, labelled, score


def test_global_dims_match_rust_order():
    assert GLOBAL_DIMS[0] == "cash_flow"
    assert GLOBAL_DIMS[-1] == "growth"
    assert len(GLOBAL_DIMS) == 8


def test_labelled_zips_dims():
    v = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    out = labelled(v)
    assert out["cash_flow"] == 0.1
    assert out["growth"] == 0.8


def test_labelled_rejects_wrong_length():
    with pytest.raises(ValueError):
        labelled([0.1, 0.2])


def test_score_is_mean_times_100():
    assert score([1.0] * 8) == 100.0
    assert score([0.0] * 8) == 0.0
    assert score([0.5] * 8) == 50.0
