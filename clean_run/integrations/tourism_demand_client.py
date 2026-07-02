from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any
import csv


DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "tourism" / "sltda_weekly_arrivals.csv"


@dataclass(frozen=True)
class DailyArrivalRow:
    day: date
    arrivals: int
    source: str


@dataclass(frozen=True)
class WeeklyArrivalRow:
    year: int
    week_start: date
    week_end: date
    arrivals: int
    source: str

    @property
    def days(self) -> int:
        return (self.week_end - self.week_start).days + 1

    @property
    def daily_average(self) -> float:
        return self.arrivals / max(self.days, 1)

    @property
    def equivalent_week_arrivals(self) -> float:
        return self.daily_average * 7

    @property
    def month_week_index(self) -> int:
        return ((self.week_start.day - 1) // 7) + 1


SLTDA_DAILY_ARRIVALS: dict[int, dict[int, list[int | None]]] = {
    2024: {
        1: [5912, 6204, 7251, 6253, 6833, 6834, 6016, 6521, 6019, 7027, 6537, 6982, 7771, 6661, 8541, 6262, 7318, 6504, 6505, 7336, 6875, 7009, 5682, 7218, 7032, 7466, 6880, 6125, 6815, 5298, 6566],
        2: [6862, 6765, 7785, 7081, 8282, 7007, 8579, 7761, 7716, 8515, 7858, 7398, 6846, 9443, 7432, 7460, 8083, 7862, 7587, 6553, 7289, 6866, 7230, 10014, 6744, 7253, 6213, 6958, 6908],
        3: [6878, 8085, 6704, 7124, 5832, 6254, 6344, 6721, 6780, 6393, 6348, 5680, 6141, 5920, 6145, 7068, 6866, 7873, 5697, 6831, 7492, 7268, 8534, 8073, 6782, 5834, 6205, 7621, 6150, None, None],
        4: [5363, 4761, 5551, 5618, 6174, 7157, 5173, 5347, 5394, 5281, 6582, 5200, 5256, 3411, 6263, 4563, 3658, 3230, 4418, 4987, 4279, 4495, 3977, 4166, 4390, 4899, 5372, 4091, 5757, 4054],
        5: [5119, 4348, 4090, 4105, 4382, 3646, 2836, 3106, 3583, 3980, 3648, 3199, 3125, 3072, 5781, 3699, 4005, 3997, 3191, 3434, 3085, 2750, 3554, 4180, 3842, 3133, 3140, 2639, 2739, 3257, 3463],
        6: [3374, 3312, 3199, 3035, 2746, 3376, 3713, 3495, 3035, 3132, 2895, 3224, 4691, 5602, 5824, 4180, 3779, 3910, 3303, 3893, 3734, 3578, 3353, 3741, 3542, 3349, 4357, 4749, 4942, 4407],
        7: [5135, 5047, 4886, 6232, 6835, 7550, 7518, 6937, 5953, 5014, 6040, 5926, 6021, 6549, 5970, 5418, 6296, 6383, 6406, 6335, 5841, 6293, 5729, 5994, 6332, 6235, 6135, 6082, 6209, None, None],
        8: [6751, 6593, 7191, 6354, 6486, 6844, 6398, 6533, 6621, 7200, 6402, 5850, 5689, 6721, 6986, 5275, 5265, 4525, 4139, 4525, 4623, 4624, 4242, 4089, 3694, 3501, 3375, 2804, 3649, 3842, 3818],
        9: [3877, 4303, 4246, 4868, 3779, 4050, 4116, 3866, 4076, 4176, 3619, 4228, 5338, 4754, 3658, 3860, 3863, 3099, 3561, 4042, 3987, 3510, 3763, 3944, 3372, 4284, 4814, 4963, 3994, 4130],
        10: [4531, 4375, 4269, 4503, 4280, 4007, 3849, 3693, 3369, 4404, 5024, 4859, 4189, 4565, 3573, 3352, 4385, 5396, 5166, 4046, 4833, 4081, 3871, 4213, 5556, 4800, 3951, 4604, 4174, 4876, 5113],
        11: [6606, 6423, 6175, 6304, 5111, 5854, 5675, 6575, 5963, 7081, 7240, 4889, 5062, 5196, 6490, 6136, 6535, 6217, 5282, 6147, 5569, 6915, 6136, 6088, 6052, 4453, 5516, 6015, 7594, 8859],
        12: [6415, 7164, 4703, 5676, 5258, 6058, 5917, 5984, 6119, 5507, 9847, 6222, 7584, 6863, 7798, 8425, 7135, 7852, 8653, 10649, 10734, 10820, 11284, 9420, 9378, 10493, 11232, 10050, 9847, 8900, 6605],
    },
    2025: {
        1: [6879, 9391, 8974, 6990, 7180, 8065, 7372, 8333, 7756, 8477, 8373, 8219, 8715, 7687, 8196, 8050, 8710, 8322, 8069, 8511, 7608, 7516, 8091, 9788, 9224, 8332, 8769, 7615, 7383, 7790, 8376],
        2: [9099, 9096, 9974, 7897, 8224, 8236, 9138, 9174, 8837, 9300, 7730, 7836, 10497, 9789, 9040, 7942, 9323, 7964, 8003, 8333, 9001, 10815, 8738, 8851, 6569, 6450, 6482, 7879],
        3: [7667, 8375, 8187, 6595, 6945, 7311, 8033, 9073, 8263, 7439, 6127, 6383, 7457, 7897, 7778, 7752, 8002, 6589, 6594, 6516, 8228, 7479, 7627, 7058, 5789, 6819, 7010, 8619, 8259, 7143, 6284],
        4: [6053, 6027, 6178, 6516, 6934, 6613, 6293, 5634, 5460, 6192, 6348, 7585, 6307, 6063, 4851, 6321, 6491, 7170, 5791, 5118, 5204, 4830, 5164, 5177, 5655, 5661, 5469, 4008, 4194, 5301],
        5: [6311, 5505, 4591, 4115, 4246, 4248, 4895, 3961, 4594, 4495, 5864, 3377, 3553, 3573, 4021, 4494, 4364, 4214, 4071, 3767, 3526, 4124, 4803, 4314, 4186, 3768, 3504, 3636, 3953, 4528, 4318],
        6: [3898, 3752, 4064, 4158, 5421, 5211, 5043, 4535, 3911, 3969, 3551, 4014, 4122, 4138, 4069, 3678, 3533, 3503, 4098, 4836, 4906, 5076, 5083, 4993, 5807, 7100, 6012, 5617, 5101, 5042],
        7: [5335, 5046, 6640, 6325, 6775, 5881, 6231, 6067, 5047, 6322, 6722, 6952, 6428, 6724, 6456, 5814, 6795, 6944, 7167, 6337, 6956, 6312, 5912, 6930, 7521, 7579, 6692, 6737, 6387, 6070, 7140],
        8: [8140, 8481, 7711, 8441, 7274, 6494, 7676, 7223, 8204, 7838, 6605, 7188, 8131, 7987, 7998, 7367, 6468, 5833, 5713, 5983, 5080, 5235, 5038, 4658, 4007, 4250, 3946, 4369, 4150, 5022, 5725],
        9: [5278, 5414, 4796, 5940, 5596, 5222, 5249, 4936, 5098, 4716, 5495, 6080, 5953, 5585, 5029, 5380, 4625, 5447, 5389, 5954, 4642, 4614, 5379, 4561, 4666, 5891, 6150, 5588, 4959, 5339],
        10: [6751, 6021, 6146, 5802, 4847, 4478, 4429, 4216, 4177, 5259, 5378, 5235, 4376, 4098, 4442, 4911, 5768, 6552, 5976, 4626, 5041, 5535, 5604, 7145, 5443, 5618, 4583, 5577, 5028, 5216, 6915],
        11: [7412, 7205, 6173, 6330, 5695, 7021, 7159, 7742, 7153, 7292, 7102, 5986, 6922, 6510, 7463, 7558, 6757, 7245, 8058, 7562, 7764, 8530, 7653, 6856, 6512, 6272, 7425, 6410, 6793, 8346],
        12: [6328, 8178, 5221, 5319, 5927, 6026, 6977, 6245, 6768, 6271, 6763, 7610, 7461, 7936, 7305, 7720, 7561, 9142, 9525, 10081, 10245, 10636, 10281, 9215, 11111, 11756, 12397, 11203, 10177, 10425, 7118],
    },
}


@lru_cache(maxsize=1)
def load_daily_arrivals() -> tuple[DailyArrivalRow, ...]:
    rows: list[DailyArrivalRow] = []
    for year, months in SLTDA_DAILY_ARRIVALS.items():
        for month, arrivals_by_day in months.items():
            for day_index, arrivals in enumerate(arrivals_by_day, start=1):
                if arrivals is None:
                    continue
                rows.append(
                    DailyArrivalRow(
                        day=date(year, month, day_index),
                        arrivals=arrivals,
                        source=f"SLTDA daily tourist arrivals {date(year, month, day_index):%B %Y}",
                    )
                )
    return tuple(sorted(rows, key=lambda row: row.day))


@lru_cache(maxsize=1)
def load_weekly_arrivals() -> tuple[WeeklyArrivalRow, ...]:
    rows: list[WeeklyArrivalRow] = []
    with DATA_FILE.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for item in reader:
            rows.append(
                WeeklyArrivalRow(
                    year=int(item["year"]),
                    week_start=date.fromisoformat(item["week_start"]),
                    week_end=date.fromisoformat(item["week_end"]),
                    arrivals=int(item["arrivals"]),
                    source=item["source"],
                )
            )
    return tuple(rows)


def _percentile_rank(value: float, population: list[float]) -> float:
    if not population:
        return 0.0
    below_or_equal = sum(1 for item in population if item <= value)
    return round((below_or_equal / len(population)) * 100, 1)


def _level_from_percentile(percentile: float) -> str:
    if percentile >= 80:
        return "high"
    if percentile >= 55:
        return "medium"
    return "low"


def _score_from_percentile(percentile: float) -> int:
    if percentile >= 90:
        return 30
    if percentile >= 80:
        return 26
    if percentile >= 65:
        return 20
    if percentile >= 55:
        return 16
    if percentile >= 35:
        return 10
    return 5


def _find_exact_row(target_date: date, rows: tuple[WeeklyArrivalRow, ...]) -> WeeklyArrivalRow | None:
    for row in rows:
        if row.week_start <= target_date <= row.week_end:
            return row
    return None


def _find_seasonal_proxy(target_date: date, rows: tuple[WeeklyArrivalRow, ...]) -> WeeklyArrivalRow | None:
    latest_year = max((row.year for row in rows), default=None)
    if latest_year is None:
        return None

    month_week_index = ((target_date.day - 1) // 7) + 1
    candidates = [
        row
        for row in rows
        if row.year == latest_year
        and row.week_start.month == target_date.month
        and row.month_week_index == month_week_index
    ]
    if candidates:
        return candidates[0]

    month_candidates = [
        row for row in rows if row.year == latest_year and row.week_start.month == target_date.month
    ]
    if not month_candidates:
        return None

    return min(month_candidates, key=lambda row: abs(row.month_week_index - month_week_index))


def _find_previous_year_comparison(row: WeeklyArrivalRow, rows: tuple[WeeklyArrivalRow, ...]) -> WeeklyArrivalRow | None:
    previous_year = row.year - 1
    candidates = [
        item
        for item in rows
        if item.year == previous_year
        and item.week_start.month == row.week_start.month
        and item.month_week_index == row.month_week_index
    ]
    return candidates[0] if candidates else None


def _find_exact_daily_row(target_date: date, rows: tuple[DailyArrivalRow, ...]) -> DailyArrivalRow | None:
    for row in rows:
        if row.day == target_date:
            return row
    return None


def _find_daily_seasonal_proxy(target_date: date, rows: tuple[DailyArrivalRow, ...]) -> DailyArrivalRow | None:
    latest_year = max((row.day.year for row in rows), default=None)
    if latest_year is None:
        return None

    same_day_candidates = [
        row
        for row in rows
        if row.day.year == latest_year
        and row.day.month == target_date.month
        and row.day.day == target_date.day
    ]
    if same_day_candidates:
        return same_day_candidates[0]

    month_candidates = [
        row for row in rows if row.day.year == latest_year and row.day.month == target_date.month
    ]
    if not month_candidates:
        return None

    return min(month_candidates, key=lambda row: abs(row.day.day - target_date.day))


def _find_previous_year_daily_comparison(
    row: DailyArrivalRow,
    rows: tuple[DailyArrivalRow, ...],
) -> DailyArrivalRow | None:
    previous_year = row.day.year - 1
    for item in rows:
        if item.day.year == previous_year and item.day.month == row.day.month and item.day.day == row.day.day:
            return item
    return None


def _daily_payload(
    *,
    row: DailyArrivalRow,
    rows: tuple[DailyArrivalRow, ...],
    iso_date: str,
    is_proxy: bool,
) -> dict[str, Any]:
    population = [item.arrivals for item in rows]
    percentile = _percentile_rank(row.arrivals, population)
    score = _score_from_percentile(percentile)
    level = _level_from_percentile(percentile)
    previous = _find_previous_year_daily_comparison(row, rows)
    yoy_change_percent = None

    if previous and previous.arrivals:
        yoy_change_percent = round(((row.arrivals - previous.arrivals) / previous.arrivals) * 100, 1)
        if yoy_change_percent >= 15 and score < 30:
            score += 3
        elif yoy_change_percent <= -15:
            score = max(score - 2, 0)

    summary = (
        f"SLTDA daily arrivals indicate {level} national tourism demand for this date "
        f"({row.arrivals:,} arrivals)."
    )
    if is_proxy:
        summary += f" Using {row.day.isoformat()} as the latest same-season daily proxy."
    if yoy_change_percent is not None:
        direction = "up" if yoy_change_percent >= 0 else "down"
        summary += f" Demand is {direction} {abs(yoy_change_percent)}% versus the comparable 2024 date."

    return {
        "level": _level_from_percentile(percentile),
        "score": min(score, 30),
        "summary": summary,
        "date": iso_date,
        "granularity": "daily",
        "matched_date": row.day.isoformat(),
        "arrivals": row.arrivals,
        "percentile": percentile,
        "year_over_year_change_percent": yoy_change_percent,
        "source": row.source,
        "is_seasonal_proxy": is_proxy,
    }


def _weekly_payload(
    *,
    row: WeeklyArrivalRow,
    rows: tuple[WeeklyArrivalRow, ...],
    iso_date: str,
    is_proxy: bool,
) -> dict[str, Any]:
    population = [item.equivalent_week_arrivals for item in rows if item.days >= 7]
    percentile = _percentile_rank(row.equivalent_week_arrivals, population)
    score = _score_from_percentile(percentile)
    level = _level_from_percentile(percentile)
    previous = _find_previous_year_comparison(row, rows)
    yoy_change_percent = None

    if previous and previous.equivalent_week_arrivals:
        yoy_change_percent = round(
            ((row.equivalent_week_arrivals - previous.equivalent_week_arrivals) / previous.equivalent_week_arrivals)
            * 100,
            1,
        )
        if yoy_change_percent >= 15 and score < 30:
            score += 3
        elif yoy_change_percent <= -15:
            score = max(score - 2, 0)

    summary = (
        f"SLTDA weekly arrivals indicate {level} national tourism demand for this season "
        f"({round(row.equivalent_week_arrivals):,} equivalent weekly arrivals)."
    )
    if yoy_change_percent is not None:
        direction = "up" if yoy_change_percent >= 0 else "down"
        summary += f" Demand is {direction} {abs(yoy_change_percent)}% versus the comparable 2024 week."

    return {
        "level": _level_from_percentile(percentile),
        "score": min(score, 30),
        "summary": summary,
        "date": iso_date,
        "granularity": "weekly",
        "matched_week_start": row.week_start.isoformat(),
        "matched_week_end": row.week_end.isoformat(),
        "arrivals": row.arrivals,
        "daily_average": round(row.daily_average, 1),
        "equivalent_week_arrivals": round(row.equivalent_week_arrivals),
        "percentile": percentile,
        "year_over_year_change_percent": yoy_change_percent,
        "source": row.source,
        "is_seasonal_proxy": is_proxy,
    }


def get_tourism_demand_for_date(iso_date: str) -> dict[str, Any]:
    target_date = date.fromisoformat(iso_date)
    daily_rows = load_daily_arrivals()
    daily_row = _find_exact_daily_row(target_date, daily_rows)

    if daily_row is not None:
        return _daily_payload(row=daily_row, rows=daily_rows, iso_date=iso_date, is_proxy=False)

    daily_proxy = _find_daily_seasonal_proxy(target_date, daily_rows)
    if daily_proxy is not None:
        return _daily_payload(row=daily_proxy, rows=daily_rows, iso_date=iso_date, is_proxy=True)

    rows = load_weekly_arrivals()
    row = _find_exact_row(target_date, rows)
    is_proxy = False

    if row is None:
        row = _find_seasonal_proxy(target_date, rows)
        is_proxy = True

    if row is None:
        return {
            "level": "unknown",
            "score": 0,
            "summary": "SLTDA tourism demand data is unavailable for this date.",
            "source": "unavailable",
            "is_seasonal_proxy": False,
        }

    return _weekly_payload(row=row, rows=rows, iso_date=iso_date, is_proxy=is_proxy)
