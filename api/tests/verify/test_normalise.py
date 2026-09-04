"""The equivalence rules, tested on their own.

`crewops.verify.normalise` is imported directly by `crewops.eval` for the
scorecard's fact containment grader, so it is a shared contract. These tests
pin the behaviour both consumers rely on.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from crewops.verify.normalise import (
    canonical_currency,
    canonical_date,
    canonical_datetime,
    canonical_duration_minutes,
    canonical_identifier,
    canonical_number,
    canonical_time,
    hours_to_minutes,
    render_duration,
    spelled_number,
)


class TestNumbers:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (61.33, "61.33"),
            ("61.33", "61.33"),
            ("61.330", "61.33"),
            (61.3333333, "61.33"),
            ("18,500", "18500"),
            (18500, "18500"),
            (18500.0, "18500"),
            ("0.50", "0.5"),
            (0, "0"),
            (486, "486"),
            ("1,000,000", "1000000"),
            ("  61.33  ", "61.33"),
        ],
    )
    def test_canonical_forms(self, raw: object, expected: str) -> None:
        assert canonical_number(raw) == expected

    @pytest.mark.parametrize("raw", ["", "abc", None, True, False, "12abc", []])
    def test_non_numbers_return_none(self, raw: object) -> None:
        assert canonical_number(raw) is None

    def test_a_changed_digit_is_a_different_number(self) -> None:
        assert canonical_number(61.33) != canonical_number(61.3)
        assert canonical_number(18500) != canonical_number(18000)

    def test_bool_is_not_a_number(self) -> None:
        # True is an int subclass. It is not the figure 1 in a duty report.
        assert canonical_number(True) is None


class TestCurrency:
    @pytest.mark.parametrize(
        "raw", ["INR 18,500", "18500", "₹18,500", "Rs 18500", "18,500 INR", 18500]
    )
    def test_every_rendering_is_the_same_amount(self, raw: object) -> None:
        assert canonical_currency(raw) == "18500"

    def test_a_different_amount_does_not_match(self) -> None:
        assert canonical_currency("INR 18,000") != canonical_currency("INR 18,500")


class TestDurations:
    def test_the_headline_equivalence(self) -> None:
        """61.33h, 61h20m and 61 hours 20 minutes are the same fact."""
        as_decimal = canonical_duration_minutes(hours=61.33)
        as_hm = canonical_duration_minutes(hours=61, minutes=20)
        assert as_decimal == as_hm == 3680

    @pytest.mark.parametrize(
        ("hours", "minutes", "rendered"),
        [
            (1.33, 80, "1h20m"),  # the Q18 / S2 excess
            (8.25, 495, "8h15m"),  # the Q24 day 2 excess
            (1.08, 65, "1h05m"),  # the C-2087 day 2 excess
            (9.5, 570, "9h30m"),
            (0.75, 45, "45m"),
            (2.0, 120, "2h"),
        ],
    )
    def test_shipped_renderings(
        self, hours: float, minutes: int, rendered: str
    ) -> None:
        assert canonical_duration_minutes(hours=hours) == minutes
        assert render_duration(minutes) == rendered

    def test_rounding_is_half_up_to_the_minute(self) -> None:
        # 1.33 h is 1 h 19.8 min. The keys render it as 1h20m.
        assert hours_to_minutes(1.33) == 80

    def test_a_two_minute_error_is_caught(self) -> None:
        """The tolerance budget is one minute either way, and no more."""
        assert canonical_duration_minutes(hours=61.33) == 3680
        assert canonical_duration_minutes(hours=61.3) == 3678
        assert canonical_duration_minutes(hours=61.33) != canonical_duration_minutes(
            hours=61.3
        )

    def test_display_rounding_still_matches(self) -> None:
        # 61.34 and 61.33 differ by 36 seconds: display rounding, same fact.
        assert canonical_duration_minutes(hours=61.34) == canonical_duration_minutes(
            hours=61.33
        )

    def test_minutes_only(self) -> None:
        assert canonical_duration_minutes(minutes=90) == 90

    def test_nothing_given_is_none(self) -> None:
        assert canonical_duration_minutes() is None

    def test_negative_renders_with_a_sign(self) -> None:
        assert render_duration(-80) == "-1h20m"


class TestDates:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2026-09-15", "2026-09-15"),
            ("2026-09-15T06:00:00Z", "2026-09-15"),
            ("15 Sep 2026", "2026-09-15"),
            ("15 September 2026", "2026-09-15"),
            ("Sep 15, 2026", "2026-09-15"),
            ("15/09/2026", "2026-09-15"),
            (date(2026, 9, 15), "2026-09-15"),
            (datetime(2026, 9, 15, 6, 0), "2026-09-15"),
        ],
    )
    def test_full_dates(self, raw: object, expected: str) -> None:
        assert canonical_date(raw) == expected

    @pytest.mark.parametrize("raw", ["15 Sep", "Sep 15", "15th Sep"])
    def test_partial_dates_keep_the_month_and_day(self, raw: str) -> None:
        assert canonical_date(raw) == "--09-15"

    def test_a_day_shift_is_a_different_date(self) -> None:
        assert canonical_date("2026-09-15") != canonical_date("2026-09-16")
        assert canonical_date("15 Sep") != canonical_date("16 Sep")

    def test_impossible_dates_are_rejected(self) -> None:
        assert canonical_date("2026-02-30") is None
        assert canonical_date("2026-13-01") is None


class TestTimes:
    @pytest.mark.parametrize(
        "raw", ["06:00", "06:00Z", "06:00:00Z", "2026-09-15T06:00:00Z"]
    )
    def test_clock_forms(self, raw: str) -> None:
        assert canonical_time(raw) == "06:00"

    def test_out_of_range_is_rejected(self) -> None:
        assert canonical_time("25:00") is None
        assert canonical_time("06:99") is None

    def test_datetime_splits_into_date_and_clock(self) -> None:
        assert canonical_datetime("2026-09-15T06:00:00Z") == ("2026-09-15", "06:00")
        assert canonical_datetime("not a timestamp") is None


class TestIdentifiers:
    def test_case_and_space_are_normalised(self) -> None:
        assert canonical_identifier(" c-1042 ") == "C-1042"

    def test_a_transposed_id_is_a_different_id(self) -> None:
        assert canonical_identifier("C-3310") != canonical_identifier("C-3301")


class TestSpelled:
    @pytest.mark.parametrize(
        ("word", "value"), [("three", 3), ("Seven", 7), ("twelve", 12), ("zero", 0)]
    )
    def test_known_cardinals(self, word: str, value: int) -> None:
        assert spelled_number(word) == value

    def test_beyond_twelve_is_not_extracted(self) -> None:
        # Documented limitation: digits only above twelve.
        assert spelled_number("thirteen") is None
