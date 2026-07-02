from __future__ import annotations

from typing import Any


def _clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _level(score: int) -> str:
    if score >= 80:
        return "excellent"
    if score >= 65:
        return "good"
    if score >= 45:
        return "fair"
    return "weak"


def _risk_to_fit(score: float | int | None) -> int:
    if score is None:
        return 55
    return _clamp_score(100 - float(score))


def _duration_seconds(route: dict[str, Any]) -> int | None:
    duration = route.get("duration")
    if isinstance(duration, str) and duration.endswith("s"):
        try:
            return int(float(duration[:-1]))
        except ValueError:
            return None
    return None


def _recommended_lodging_prices(route: dict[str, Any]) -> list[float]:
    prices: list[float] = []
    for segment in route.get("segments") or []:
        lodging = segment.get("recommended_lodging") or {}
        price = lodging.get("total_price_lkr") or lodging.get("price_lkr") or lodging.get("current_price_lkr")
        try:
            if price is not None:
                prices.append(float(price))
        except (TypeError, ValueError):
            continue
    return prices


def _recommended_lodging_ratings(route: dict[str, Any]) -> list[float]:
    ratings: list[float] = []
    for segment in route.get("segments") or []:
        lodging = segment.get("recommended_lodging") or {}
        rating = lodging.get("review_score") or lodging.get("score") or lodging.get("rating")
        try:
            if rating is not None:
                ratings.append(float(rating))
        except (TypeError, ValueError):
            continue
    return ratings


def build_package_explanation(plan: dict[str, Any]) -> dict[str, Any]:
    """Explain package quality without changing the generated package."""
    recommended_route = plan.get("recommended_route") or {}
    budget_summary = plan.get("budget_summary") or {}
    crowd_signals = plan.get("crowd_signals") or {}
    weather_summary = (plan.get("weather_data") or {}).get("summary") or recommended_route.get("weather_summary") or {}
    traffic_data = plan.get("traffic_data") or recommended_route.get("traffic_data") or {}
    transport_cost = plan.get("transport_cost") or {}

    total_budget = budget_summary.get("total_budget_lkr")
    accommodation_budget = budget_summary.get("accommodation_budget_lkr")
    nightly_budget = budget_summary.get("nightly_lodging_budget_lkr")
    selected_flight_cost = budget_summary.get("selected_flight_budget_lkr_estimated")
    lodging_prices = _recommended_lodging_prices(recommended_route)
    lodging_ratings = _recommended_lodging_ratings(recommended_route)

    spent_estimate = 0.0
    spent_parts: list[str] = []
    if selected_flight_cost is not None:
        spent_estimate += float(selected_flight_cost)
        spent_parts.append("selected flight estimate")
    if lodging_prices:
        spent_estimate += sum(lodging_prices)
        spent_parts.append("selected accommodation prices")
    if transport_cost.get("estimated_total_lkr") is not None:
        spent_estimate += float(transport_cost["estimated_total_lkr"])
        spent_parts.append("bus-fare estimate")

    if total_budget:
        budget_score = _clamp_score(100 - max(0.0, (spent_estimate - float(total_budget)) / float(total_budget) * 100))
        budget_reason = (
            f"Estimated tracked spend is about LKR {spent_estimate:,.0f} against the LKR {float(total_budget):,.0f} total budget."
        )
    elif accommodation_budget and lodging_prices:
        lodging_total = sum(lodging_prices)
        budget_score = _clamp_score(100 - max(0.0, (lodging_total - float(accommodation_budget)) / float(accommodation_budget) * 100))
        budget_reason = (
            f"Selected lodging totals about LKR {lodging_total:,.0f} against the LKR {float(accommodation_budget):,.0f} accommodation budget."
        )
    elif nightly_budget:
        budget_score = 70
        budget_reason = f"Nightly lodging budget is available at about LKR {float(nightly_budget):,.0f}, but selected stay prices are incomplete."
    else:
        budget_score = 55
        budget_reason = "No explicit usable budget comparison was available, so budget fit is treated as neutral."

    distance_km = (plan.get("route_data") or {}).get("distance_km")
    duration_seconds = _duration_seconds(recommended_route)
    if distance_km is None:
        meters = recommended_route.get("distance_meters")
        distance_km = round(float(meters or 0) / 1000, 1)
    distance_value = float(distance_km or 0)
    if distance_value <= 120:
        distance_score = 86
    elif distance_value <= 250:
        distance_score = 72
    elif distance_value <= 400:
        distance_score = 58
    else:
        distance_score = 43
    distance_reason = f"Route distance is about {distance_value:.1f} km."
    if duration_seconds:
        distance_reason += f" Drive duration is roughly {round(duration_seconds / 3600, 1)} hours."

    if lodging_ratings:
        average_rating = sum(lodging_ratings) / len(lodging_ratings)
        comfort_score = _clamp_score(average_rating * 10)
        comfort_reason = f"Selected stays average about {average_rating:.1f}/10 from available review scores."
    elif lodging_prices:
        comfort_score = 68
        comfort_reason = "Accommodation choices have usable prices, but review-score data is incomplete."
    else:
        comfort_score = 55
        comfort_reason = "Accommodation quality data is incomplete for this package."

    crowd_score = _risk_to_fit(crowd_signals.get("signal_score"))
    crowd_reason = (
        f"Crowd pressure is {crowd_signals.get('risk_level') or 'unknown'}"
        f" with signal score {crowd_signals.get('signal_score') if crowd_signals.get('signal_score') is not None else 'unknown'}."
    )

    weather_score = _risk_to_fit(weather_summary.get("average_weather_risk_score") or weather_summary.get("max_weather_risk_score"))
    weather_reason = (
        f"Weather risk is {weather_summary.get('risk_level') or 'unknown'}"
        f" with average score {weather_summary.get('average_weather_risk_score') if weather_summary.get('average_weather_risk_score') is not None else 'unknown'}."
    )

    traffic_risk = traffic_data.get("risk_score") or traffic_data.get("delay_score")
    traffic_score = _risk_to_fit(traffic_risk)
    traffic_reason = (
        f"Traffic signal is {traffic_data.get('risk_level') or traffic_data.get('status') or 'unknown'}."
    )

    components = {
        "budget_fit": {
            "score": budget_score,
            "level": _level(budget_score),
            "reason": budget_reason,
            "inputs_used": spent_parts,
        },
        "distance_efficiency": {
            "score": distance_score,
            "level": _level(distance_score),
            "reason": distance_reason,
        },
        "comfort": {
            "score": comfort_score,
            "level": _level(comfort_score),
            "reason": comfort_reason,
        },
        "crowd_fit": {
            "score": crowd_score,
            "level": _level(crowd_score),
            "reason": crowd_reason,
        },
        "weather_fit": {
            "score": weather_score,
            "level": _level(weather_score),
            "reason": weather_reason,
        },
        "traffic_fit": {
            "score": traffic_score,
            "level": _level(traffic_score),
            "reason": traffic_reason,
        },
    }

    weights = {
        "budget_fit": 0.24,
        "distance_efficiency": 0.18,
        "comfort": 0.18,
        "crowd_fit": 0.16,
        "weather_fit": 0.16,
        "traffic_fit": 0.08,
    }
    overall_score = _clamp_score(sum(components[key]["score"] * weight for key, weight in weights.items()))
    strongest = sorted(components.items(), key=lambda item: item[1]["score"], reverse=True)[:2]
    weakest = sorted(components.items(), key=lambda item: item[1]["score"])[:2]

    return {
        "version": "package_explanation_v1",
        "mode": "read_only",
        "overall_score": overall_score,
        "overall_level": _level(overall_score),
        "summary": (
            f"This package scores {overall_score}/100 overall. "
            f"Strongest signals: {strongest[0][0].replace('_', ' ')} and {strongest[1][0].replace('_', ' ')}. "
            f"Watch points: {weakest[0][0].replace('_', ' ')} and {weakest[1][0].replace('_', ' ')}."
        ),
        "weights": weights,
        "components": components,
        "package_mutation": {
            "allowed": False,
            "note": "This explanation does not change flights, hotels, route geometry, attractions, or budgets.",
        },
    }
