"""SM-2 spaced-repetition scheduling.

The implementation follows the original Anki-style rules used by the product:
quality below 3 starts the card over, while successful repetitions use the
1 -> 6 -> interval * ease-factor progression.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Mapping


QUALITY_LABELS = {
    1: "重来",
    3: "困难",
    4: "良好",
    5: "简单",
}


def normalize_quality(value: Any) -> int:
    """Accept numeric qualities and the four labels used by the UI."""

    if isinstance(value, str):
        text = value.strip().lower()
        labels = {"重来": 1, "再来": 1, "again": 1, "hard": 3, "困难": 3, "good": 4, "良好": 4, "easy": 5, "简单": 5}
        if text in labels:
            return labels[text]
        try:
            value = int(text)
        except ValueError as exc:
            raise ValueError("quality must be one of 1, 3, 4, 5") from exc
    try:
        quality = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("quality must be one of 1, 3, 4, 5") from exc
    if quality not in (1, 3, 4, 5):
        raise ValueError("quality must be one of 1, 3, 4, 5")
    return quality


def schedule_review(
    review: Mapping[str, Any],
    quality: int,
    reviewed_on: date | None = None,
) -> dict[str, Any]:
    """Calculate the next review state without mutating the input mapping."""

    q = normalize_quality(quality)
    repetitions = int(review.get("repetitions", 0) or 0)
    interval = int(review.get("interval", 0) or 0)
    ease_factor = float(review.get("ease_factor", 2.5) or 2.5)
    reviewed_on = reviewed_on or date.today()

    # SM-2 ease-factor update. It applies to failed recalls too, bounded at 1.3.
    ease_factor = max(
        1.3,
        ease_factor + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02),
    )

    if q < 3:
        repetitions = 0
        interval = 1
    else:
        repetitions += 1
        if repetitions == 1:
            interval = 1
        elif repetitions == 2:
            interval = 6
        else:
            interval = max(1, round(interval * ease_factor))
    due_date = reviewed_on + timedelta(days=interval)
    return {
        "ease_factor": round(ease_factor, 4),
        "interval": int(interval),
        "repetitions": int(repetitions),
        "due_date": due_date.isoformat(),
    }


# Friendly aliases for callers/tests that use the conventional naming.
sm2 = schedule_review
sm2_update = schedule_review


def mastery_score(review: Mapping[str, Any]) -> float:
    """Return a conservative 0..100 score for dashboards.

    A card is considered mastered after three successful repetitions, with
    interval and ease factor contributing gradually thereafter.
    """

    reps = max(0, int(review.get("repetitions", 0) or 0))
    interval = max(0, int(review.get("interval", 0) or 0))
    ease = max(1.3, float(review.get("ease_factor", 2.5) or 2.5))
    if reps == 0:
        return 0.0
    rep_component = min(reps / 3, 1.0) * 60
    interval_component = min(interval / 30, 1.0) * 30
    # Untouched cards have the default ease but no demonstrated mastery.
    ease_component = min(max((ease - 1.3) / 1.2, 0.0), 1.0) * 10 if reps > 0 else 0
    return round(min(100.0, rep_component + interval_component + ease_component), 1)


__all__ = ["QUALITY_LABELS", "mastery_score", "normalize_quality", "schedule_review", "sm2", "sm2_update"]
