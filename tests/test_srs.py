"""Unit tests for the SM-2 spaced-repetition algorithm in backend/srs.py."""

from __future__ import annotations

from datetime import date

import pytest

from backend.srs import QUALITY_LABELS, mastery_score, normalize_quality, schedule_review


# ---------------------------------------------------------------------------
# normalize_quality


@pytest.mark.parametrize("value,expected", [
    (1, 1), (3, 3), (4, 4), (5, 5),
    ("1", 1), ("3", 3), ("4", 4), ("5", 5),
    ("重来", 1), ("再来", 1), ("again", 1),
    ("困难", 3), ("hard", 3),
    ("良好", 4), ("good", 4),
    ("简单", 5), ("easy", 5),
    (" 良好 ", 4),  # surrounding whitespace is stripped
])
def test_normalize_quality_accepts_valid_values(value, expected):
    assert normalize_quality(value) == expected


@pytest.mark.parametrize("value", [0, 2, 6, -1, "2", "0", "unknown", "", None, 2.0])
def test_normalize_quality_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        normalize_quality(value)


# ---------------------------------------------------------------------------
# schedule_review


def _card(**overrides):
    base = {"repetitions": 0, "interval": 0, "ease_factor": 2.5}
    base.update(overrides)
    return base


def test_again_resets_card_and_dues_tomorrow():
    result = schedule_review(_card(repetitions=5, interval=60, ease_factor=2.5), quality=1, reviewed_on=date(2026, 8, 10))
    assert result["repetitions"] == 0
    assert result["interval"] == 1
    assert result["due_date"] == "2026-08-11"


def test_again_lowers_ease_factor():
    result = schedule_review(_card(), quality=1, reviewed_on=date(2026, 8, 10))
    # 2.5 -> 2.5 + 0.1 - 4 * (0.08 + 0.08) = 1.96
    assert result["ease_factor"] == pytest.approx(1.96)


def test_ease_factor_never_below_floor():
    result = schedule_review(_card(ease_factor=1.31), quality=1, reviewed_on=date(2026, 8, 10))
    assert result["ease_factor"] >= 1.3


def test_first_success_interval_one_day():
    for quality in (3, 4, 5):
        result = schedule_review(_card(), quality=quality, reviewed_on=date(2026, 8, 10))
        assert result["repetitions"] == 1
        assert result["interval"] == 1
        assert result["due_date"] == "2026-08-11"


def test_second_success_interval_six_days():
    result = schedule_review(_card(repetitions=1, interval=1), quality=4, reviewed_on=date(2026, 8, 10))
    assert result["repetitions"] == 2
    assert result["interval"] == 6
    assert result["due_date"] == "2026-08-16"


def test_third_success_scales_by_ease_factor():
    result = schedule_review(_card(repetitions=2, interval=6, ease_factor=2.5), quality=4, reviewed_on=date(2026, 8, 10))
    assert result["repetitions"] == 3
    assert result["interval"] == 15  # round(6 * 2.5)
    assert result["due_date"] == "2026-08-25"


def test_easy_raises_ease_factor_good_keeps_it_steady():
    easy = schedule_review(_card(), quality=5)
    good = schedule_review(_card(), quality=4)
    assert easy["ease_factor"] == pytest.approx(2.6)
    assert good["ease_factor"] == pytest.approx(2.5)


def test_interval_never_shrinks_below_one_on_success():
    result = schedule_review(_card(repetitions=10, interval=1, ease_factor=1.3), quality=5)
    assert result["interval"] >= 1


def test_pure_function_does_not_mutate_input():
    card = _card(repetitions=3, interval=30, ease_factor=2.5)
    snapshot = dict(card)
    schedule_review(card, quality=1)
    assert card == snapshot


def test_default_reviewed_on_is_today():
    from datetime import datetime
    expected = date.today().isoformat()
    result = schedule_review(_card(repetitions=0, interval=0), quality=1)
    # q=1 -> interval 1 -> tomorrow
    assert result["due_date"] != expected
    assert result["due_date"] == (date.today() + __import__("datetime").timedelta(days=1)).isoformat()


# ---------------------------------------------------------------------------
# mastery_score


def test_unreviewed_card_scores_zero():
    assert mastery_score({"repetitions": 0, "interval": 0, "ease_factor": 2.5}) == 0.0


def test_mastery_score_grows_with_repetitions():
    low = mastery_score({"repetitions": 1, "interval": 1, "ease_factor": 2.5})
    high = mastery_score({"repetitions": 3, "interval": 30, "ease_factor": 2.5})
    assert low < high


def test_mastery_score_caps_at_100():
    score = mastery_score({"repetitions": 9, "interval": 120, "ease_factor": 2.5})
    assert score == 100.0


def test_negative_or_missing_fields_are_safe():
    assert mastery_score({}) == 0.0
    assert mastery_score({"repetitions": -5, "interval": -1, "ease_factor": 0.1}) == 0.0


# ---------------------------------------------------------------------------
# QUALITY_LABELS


def test_quality_labels_expose_the_four_buttons():
    assert set(QUALITY_LABELS) == {1, 3, 4, 5}
