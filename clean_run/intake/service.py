from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime
from pathlib import Path
from typing import Iterable, Protocol

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from .schemas import (
    ChatResponse,
    ChatSessionState,
    ChatTurnResult,
    ConversationTurn,
    FlightIntakeOutput,
    IntakePhase,
    TripIntakeOutput,
    TripRequirements,
)

CLEAN_RUN_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(CLEAN_RUN_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".env")

UNKNOWN_VALUES = {
    "",
    "unknown",
    "not provided",
    "not specified",
    "none",
    "null",
    "n/a",
    "na",
    "unspecified",
    "tbd",
    "to be decided",
}

FLIGHT_EXTRACTION_SYSTEM_PROMPT = """
You are the Gatekeeper and Flight Intake Extractor for a Sri Lanka travel planner.
Your job is to filter out conversational chatter and extract flight-phase fields.

RULES FOR GATEKEEPING (is_valid_input):
1. If the user says "Hi", "Hello", "Hey", or makes a conversational statement without travel details, set is_valid_input = False.
2. If the user gives a vague update like "change it to 4 days" but misses key info required for the prompt, set is_valid_input = False.
3. If is_valid_input = False, you MUST provide a friendly conversational_reply asking for the missing info (e.g. "Hi there! I'm your AI Sri Lanka guide. 🇱🇰 Where are you flying from?").
4. If the user provides valid flight information (origin, date, passengers, budget, cabin), set is_valid_input = True.

RULES FOR EXTRACTION (if is_valid_input is True):
1. Extract flight_origin_input, flight_origin, flight_departure_date, flight_passengers, flight_cabin_class, total_budget_lkr.
2. The flight destination is fixed to Colombo / CMB. Never extract it.
3. Map obvious city/airport names to likely IATA codes in flight_origin.
4. If the latest message is short, use the chat history to decide which flight field it answers.
5. Leave unclear or missing values null. Do not invent.
"""

TRIP_EXTRACTION_SYSTEM_PROMPT = """
You are the Gatekeeper and Trip Intake Extractor for a Sri Lanka travel planner.
Your job is to filter out conversational chatter and extract trip-phase fields.

RULES FOR GATEKEEPING (is_valid_input):
1. If the user says "Hi", "Hello", "Hey", or makes a conversational statement without travel details, set is_valid_input = False.
2. If the user gives a vague update like "I want to go" without a destination, set is_valid_input = False.
3. If is_valid_input = False, you MUST provide a friendly conversational_reply asking for the missing info (e.g. "I'd love to help! Where in Sri Lanka do you want to go?").
4. If the user provides valid trip information (origin, destination, duration), set is_valid_input = True.

RULES FOR EXTRACTION (if is_valid_input is True):
1. Extract origin, destination, duration.
2. origin means the Sri Lanka trip start location, not the international flight origin.
3. destination means the Sri Lanka trip destination.
4. Understand route phrases like "Colombo to Badulla", "from Colombo to Badulla".
5. Ignore flight details such as Dubai, passengers, cabin class, and flight date.
6. Leave unclear or missing values null. Do not invent.
"""

YES_HINTS = {
    "yes",
    "yeah",
    "yep",
    "sure",
    "please do",
    "with flights",
    "need flights",
    "look for flights",
    "find flights",
}

NO_HINTS = {
    "no",
    "nope",
    "nah",
    "no flight",
    "no flights",
    "no flight needed",
    "no flights needed",
    "without flights",
    "skip flights",
    "dont need flights",
    "don't need flights",
    "no need for flights",
}

AIRPORT_ALIASES = {
    "dubai": "DXB",
    "dubai international": "DXB",
    "dubai airport": "DXB",
    "dxb": "DXB",
    "doha": "DOH",
    "doha airport": "DOH",
    "hamad": "DOH",
    "hamad international": "DOH",
    "doh": "DOH",
    "colombo": "CMB",
    "colombo airport": "CMB",
    "bandaranaike": "CMB",
    "bandaranaike international airport": "CMB",
    "katunayake": "CMB",
    "cmb": "CMB",
    "singapore": "SIN",
    "changi": "SIN",
    "sin": "SIN",
    "mumbai": "BOM",
    "bombay": "BOM",
    "bom": "BOM",
    "delhi": "DEL",
    "new delhi": "DEL",
    "del": "DEL",
    "bangkok": "BKK",
    "suvarnabhumi": "BKK",
    "bkk": "BKK",
    "kuala lumpur": "KUL",
    "kul": "KUL",
    "male": "MLE",
    "malé": "MLE",
    "mle": "MLE",
}

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

FLIGHT_DETAIL_BOUNDARY = (
    r"(?:\s+on\s+[A-Za-z0-9,\-/ ]+|\s*,\s*[A-Za-z0-9,\-/ ]+|"
    r"\s+for\s+\d+\s+passengers?|\s+(?:economy|premium economy|business|first)(?:\s+class)?|\s*$)"
)

REQUIRED_FIELD_ORDER = [
    "flight_origin",
    "flight_departure_date",
    "flight_passengers",
    "flight_cabin_class",
    "total_budget_lkr",
    "origin",
    "destination",
    "duration",
]

FLIGHT_FIELD_ORDER = [
    "flight_origin",
    "flight_departure_date",
    "flight_passengers",
    "flight_cabin_class",
    "total_budget_lkr",
]

TRIP_FIELD_ORDER = [
    "origin",
    "destination",
    "duration",
]


class StructuredExtractionChain(Protocol):
    def invoke(self, payload: dict[str, str]) -> object: ...


def _normalize_requirement_value(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", value).strip(" ,.-")
    if not normalized:
        return None
    if normalized.lower() in UNKNOWN_VALUES:
        return None
    return normalized


def _normalize_date_value(value: str | None) -> str | None:
    normalized = _normalize_requirement_value(value)
    if not normalized:
        return None

    candidate = normalized.replace("/", "-")
    candidate = re.sub(r",", " ", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip()

    for date_format in (
        "%Y-%m-%d",
        "%Y %B %d",
        "%Y %b %d",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d %Y",
        "%b %d %Y",
    ):
        try:
            return datetime.strptime(candidate, date_format).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return normalized if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized) else None


def _normalize_budget_value(value: float | int | str | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if float(value) > 0 else None

    normalized = str(value).strip().lower()
    if not normalized or normalized in UNKNOWN_VALUES:
        return None

    cleaned = re.sub(r"[^0-9.]", "", normalized)
    if not cleaned:
        return None
    try:
        amount = float(cleaned)
    except ValueError:
        return None
    return amount if amount > 0 else None


def _normalize_needs_flights(value: bool | str | None) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None

    normalized = " ".join(str(value).strip().lower().split())
    if not normalized or normalized in UNKNOWN_VALUES:
        return None
    if normalized in YES_HINTS:
        return True
    if normalized in NO_HINTS:
        return False
    return None


def _normalize_airport_code(value: str | None) -> str | None:
    normalized = _normalize_requirement_value(value)
    if not normalized:
        return None

    compact = " ".join(normalized.lower().split())
    if compact in YES_HINTS or compact in NO_HINTS:
        return None
    if re.fullmatch(r"[A-Za-z]{3}", normalized):
        return normalized.upper()
    return AIRPORT_ALIASES.get(compact)


def _looks_like_flight_detail_message(message: str) -> bool:
    lowered = " ".join(message.lower().strip().split())
    flight_cues = (
        "flying from",
        "fly from",
        "flights from",
        "flight from",
        "flight origin",
        "passenger",
        "economy",
        "business",
        "premium economy",
        "first class",
        "departure date",
        "flight date",
    )
    return any(cue in lowered for cue in flight_cues)


def _parse_passenger_value(value: str) -> int | None:
    normalized = " ".join(value.lower().strip().split())
    if not normalized:
        return None

    digits_match = re.fullmatch(r"\d+", normalized)
    if digits_match:
        try:
            parsed = int(digits_match.group(0))
        except ValueError:
            return None
        return parsed if parsed > 0 else None

    if normalized in NUMBER_WORDS:
        return NUMBER_WORDS[normalized]

    passengers_match = re.search(
        r"\b(\d+)\s+(?:pass(?:enger|anger)s?|travell?ers?)\b",
        normalized,
    )
    if passengers_match:
        try:
            parsed = int(passengers_match.group(1))
        except ValueError:
            return None
        return parsed if parsed > 0 else None

    word_passenger_match = re.search(
        r"\b(" + "|".join(NUMBER_WORDS.keys()) + r")\s+(?:pass(?:enger|anger)s?|travell?ers?)\b",
        normalized,
    )
    if word_passenger_match:
        return NUMBER_WORDS.get(word_passenger_match.group(1))

    return None


def _parse_cabin_class(value: str) -> str | None:
    normalized = " ".join(value.lower().strip().split())
    if not normalized:
        return None

    cabin_patterns = [
        (r"\bpremium economy\b", "premium_economy"),
        (r"\beconomy(?:\s+class)?\b", "economy"),
        (r"\bbusiness(?:\s+class)?\b", "business"),
        (r"\bfirst(?:\s+class)?\b", "first"),
    ]
    for pattern, normalized_value in cabin_patterns:
        if re.search(pattern, normalized):
            return normalized_value
    return None


def _history_to_text(history: Iterable[ConversationTurn]) -> str:
    items = list(history)
    if not items:
        return "No previous conversation."
    return "\n".join(f"{turn.role.title()}: {turn.content}" for turn in items)


def _format_missing_fields_text(missing_fields: list[str]) -> str:
    if not missing_fields:
        return "None"
    return ", ".join(missing_fields)


def _merge_trip_requirements(current: TripRequirements, incoming: TripRequirements) -> TripRequirements:
    incoming_flight_origin_input = _normalize_requirement_value(incoming.flight_origin_input)
    current_flight_origin_input = _normalize_requirement_value(current.flight_origin_input)
    incoming_flight_origin_code = _normalize_airport_code(incoming.flight_origin or incoming_flight_origin_input)
    current_flight_origin_code = _normalize_airport_code(current.flight_origin or current_flight_origin_input)

    return TripRequirements(
        needs_flights=(
            _normalize_needs_flights(incoming.needs_flights)
            if _normalize_needs_flights(incoming.needs_flights) is not None
            else _normalize_needs_flights(current.needs_flights)
        ),
        origin=_normalize_requirement_value(incoming.origin) or _normalize_requirement_value(current.origin),
        destination=_normalize_requirement_value(incoming.destination)
        or _normalize_requirement_value(current.destination),
        duration=_normalize_requirement_value(incoming.duration) or _normalize_requirement_value(current.duration),
        accommodation_budget_lkr=_normalize_budget_value(incoming.accommodation_budget_lkr)
        or _normalize_budget_value(current.accommodation_budget_lkr),
        total_budget_lkr=_normalize_budget_value(incoming.total_budget_lkr)
        or _normalize_budget_value(current.total_budget_lkr),
        flight_origin_input=incoming_flight_origin_input or current_flight_origin_input,
        flight_origin=incoming_flight_origin_code or current_flight_origin_code,
        flight_departure_date=_normalize_date_value(incoming.flight_departure_date)
        or _normalize_date_value(current.flight_departure_date),
        flight_search_mode=_normalize_requirement_value(incoming.flight_search_mode)
        or _normalize_requirement_value(current.flight_search_mode),
        flight_passengers=(
            incoming.flight_passengers
            if incoming.flight_passengers and incoming.flight_passengers > 0
            else current.flight_passengers
        ),
        flight_cabin_class=_normalize_requirement_value(incoming.flight_cabin_class)
        or _normalize_requirement_value(current.flight_cabin_class),
    )


def _require_flights(details: TripRequirements) -> TripRequirements:
    payload = details.model_dump()
    payload["needs_flights"] = True
    return TripRequirements(**payload)


def _flight_output_to_requirements(output: object) -> TripRequirements:
    if isinstance(output, TripRequirements):
        flight_origin_input = _normalize_requirement_value(output.flight_origin_input)
        flight_origin = _normalize_airport_code(output.flight_origin or flight_origin_input)
        return TripRequirements(
            needs_flights=True,
            total_budget_lkr=_normalize_budget_value(output.total_budget_lkr),
            flight_origin_input=flight_origin_input,
            flight_origin=flight_origin,
            flight_departure_date=_normalize_date_value(output.flight_departure_date),
            flight_passengers=output.flight_passengers if output.flight_passengers and output.flight_passengers > 0 else None,
            flight_cabin_class=_normalize_requirement_value(output.flight_cabin_class),
        )
    if not isinstance(output, FlightIntakeOutput):
        return TripRequirements()

    flight_origin_input = _normalize_requirement_value(output.flight_origin_input)
    flight_origin = _normalize_airport_code(output.flight_origin or flight_origin_input)
    return TripRequirements(
        needs_flights=True,
        total_budget_lkr=_normalize_budget_value(output.total_budget_lkr),
        flight_origin_input=flight_origin_input,
        flight_origin=flight_origin,
        flight_departure_date=_normalize_date_value(output.flight_departure_date),
        flight_passengers=output.flight_passengers if output.flight_passengers and output.flight_passengers > 0 else None,
        flight_cabin_class=_normalize_requirement_value(output.flight_cabin_class),
    )


def _trip_output_to_requirements(output: object) -> TripRequirements:
    if isinstance(output, TripRequirements):
        return TripRequirements(
            origin=_normalize_requirement_value(output.origin),
            destination=_normalize_requirement_value(output.destination),
            duration=_normalize_requirement_value(output.duration),
        )
    if not isinstance(output, TripIntakeOutput):
        return TripRequirements()

    return TripRequirements(
        origin=_normalize_requirement_value(output.origin),
        destination=_normalize_requirement_value(output.destination),
        duration=_normalize_requirement_value(output.duration),
    )


def _has_flight_info(details: TripRequirements) -> bool:
    return any(
        (
            _normalize_requirement_value(details.flight_origin_input),
            _normalize_airport_code(details.flight_origin),
            _normalize_date_value(details.flight_departure_date),
            details.flight_passengers if details.flight_passengers and details.flight_passengers > 0 else None,
            _normalize_requirement_value(details.flight_cabin_class),
            _normalize_budget_value(details.total_budget_lkr),
        )
    )


def _has_trip_info(details: TripRequirements) -> bool:
    return any(
        (
            _normalize_requirement_value(details.origin),
            _normalize_requirement_value(details.destination),
            _normalize_requirement_value(details.duration),
        )
    )


def _find_missing_fields(details: TripRequirements) -> list[str]:
    missing: list[str] = []
    if not _normalize_airport_code(details.flight_origin or details.flight_origin_input):
        missing.append("flight_origin")
    if not _normalize_date_value(details.flight_departure_date):
        missing.append("flight_departure_date")
    if not details.flight_passengers or details.flight_passengers <= 0:
        missing.append("flight_passengers")
    if not _normalize_requirement_value(details.flight_cabin_class):
        missing.append("flight_cabin_class")
    if _normalize_budget_value(details.total_budget_lkr) is None:
        missing.append("total_budget_lkr")
    if not _normalize_requirement_value(details.origin):
        missing.append("origin")
    if not _normalize_requirement_value(details.destination):
        missing.append("destination")
    if not _normalize_requirement_value(details.duration):
        missing.append("duration")
    return missing


def _find_flight_missing_fields(details: TripRequirements) -> list[str]:
    return [field for field in FLIGHT_FIELD_ORDER if field in _find_missing_fields(details)]


def _find_trip_missing_fields(details: TripRequirements) -> list[str]:
    return [field for field in TRIP_FIELD_ORDER if field in _find_missing_fields(details)]


def _current_intake_stage(details: TripRequirements) -> IntakePhase:
    if _find_flight_missing_fields(details):
        return "flight"
    if _find_trip_missing_fields(details):
        return "trip"
    return "complete"


def _find_active_phase_missing_fields(details: TripRequirements) -> list[str]:
    stage = _current_intake_stage(details)
    if stage == "flight":
        return _find_flight_missing_fields(details)
    if stage == "trip":
        return _find_trip_missing_fields(details)
    return []


def _next_required_field(missing_fields: list[str]) -> str | None:
    for field in REQUIRED_FIELD_ORDER:
        if field in missing_fields:
            return field
    return None


def _looks_like_greeting(message: str) -> bool:
    normalized = " ".join(message.lower().strip().split())
    return normalized in {
        "hi",
        "hello",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
        "yo",
        "hiya",
        "sup",
    }


def _clean_place_fragment(value: str | None) -> str | None:
    return _normalize_requirement_value(value)


def _extract_route_pair(text: str, *, allow_generic_from_to: bool) -> tuple[str | None, str | None]:
    explicit_patterns = [
        r"\b(?:trip|journey|route|itinerary)\s+(?:starts?|begins?)\s+(?:in|at|from)\s+"
        r"(?P<origin>.+?)(?:\s*,\s*|\s+and\s+)(?:ends?|finishes?)\s+(?:in|at|to)\s+"
        r"(?P<destination>.+?)(?:\s*,?\s+for\s+|\s*,?\s+in\s+|[.!?]|$)",
        r"\b(?:starts?|begins?|starting|beginning)\s+(?:in|at|from)\s+"
        r"(?P<origin>.+?)(?:\s*,\s*|\s+and\s+)(?:ends?|ending|finishes?|finishing)\s+(?:in|at|to)\s+"
        r"(?P<destination>.+?)(?:\s*,?\s+for\s+|\s*,?\s+in\s+|[.!?]|$)",
        r"\btrip\s+from\s+(?P<origin>.+?)\s+to\s+(?P<destination>.+?)(?:\s+for\s+|\s+in\s+|[.!?]|$)",
        r"\bitinerary\s+from\s+(?P<origin>.+?)\s+to\s+(?P<destination>.+?)(?:\s+for\s+|\s+in\s+|[.!?]|$)",
        r"\btravel(?:ling)?\s+from\s+(?P<origin>.+?)\s+to\s+(?P<destination>.+?)(?:\s+for\s+|\s+in\s+|[.!?]|$)",
        r"\bjourney\s+from\s+(?P<origin>.+?)\s+to\s+(?P<destination>.+?)(?:\s+for\s+|\s+in\s+|[.!?]|$)",
        r"\broute\s+from\s+(?P<origin>.+?)\s+to\s+(?P<destination>.+?)(?:\s+for\s+|\s+in\s+|[.!?]|$)",
    ]

    for pattern in explicit_patterns:
        matches = list(re.finditer(pattern, text, flags=re.IGNORECASE))
        if matches:
            match = matches[-1]
            return (
                _clean_place_fragment(match.group("origin")),
                _clean_place_fragment(match.group("destination")),
            )

    if allow_generic_from_to:
        generic_patterns = [
            r"^\s*(?:from\s+)?(?P<origin>[A-Za-z][A-Za-z .'-]*?)\s+to\s+(?P<destination>[A-Za-z][A-Za-z .'-]*?)(?:\s+for\s+|\s+in\s+|\s+\d+\s*(?:day|days|week|weeks)\b|\s*$)",
            r"\bfrom\s+(?P<origin>.+?)\s+to\s+(?P<destination>.+?)(?:\s+for\s+|\s+in\s+|[.!?]|$)",
        ]
        for pattern in generic_patterns:
            matches = list(re.finditer(pattern, text, flags=re.IGNORECASE))
            if matches:
                match = matches[-1]
                return (
                    _clean_place_fragment(match.group("origin")),
                    _clean_place_fragment(match.group("destination")),
                )

    return None, None


def _extract_embedded_trip_route_pair(text: str) -> tuple[str | None, str | None]:
    patterns = [
        r"\bfrom\s+(?P<origin>[A-Za-z][A-Za-z .'-]*?)\s+to\s+"
        r"(?P<destination>[A-Za-z][A-Za-z .'-]*?)(?:\s+for\s+\d+\s*(?:day|days|week|weeks)\b)",
        r"(?:^|[.!?]\s+)(?P<origin>[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,3})\s+to\s+"
        r"(?P<destination>[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,3})\s+for\s+\d+\s*(?:day|days|week|weeks)\b",
    ]
    matches = []
    for pattern in patterns:
        matches.extend(re.finditer(pattern, text, flags=re.IGNORECASE))
    if not matches:
        return None, None
    match = matches[-1]
    return (
        _clean_place_fragment(match.group("origin")),
        _clean_place_fragment(match.group("destination")),
    )


def _heuristic_trip_requirements(
    message: str,
    *,
    current_details: TripRequirements | None = None,
    current_missing_fields: list[str] | None = None,
) -> TripRequirements:
    text = " ".join(message.strip().split())
    lowered = text.lower()
    missing_fields = current_missing_fields or []
    next_required_field = _next_required_field(missing_fields)
    current_details = current_details or TripRequirements()
    contextual_flight_collection = (
        _normalize_needs_flights(current_details.needs_flights) is True
        and any(
            field in missing_fields
            for field in ("flight_origin", "flight_departure_date", "flight_passengers", "flight_cabin_class")
        )
    )
    budget_keywords_present = bool(re.search(r"\b(budget|lkr|rs\.?|rupees?)\b", lowered))
    passenger_keywords_present = bool(re.search(r"\bpass(?:enger|anger)s?\b", lowered))
    budget_only_mode = next_required_field == "total_budget_lkr" and (
        budget_keywords_present or missing_fields == ["total_budget_lkr"]
    )

    needs_flights = None
    origin = None
    destination = None
    duration = None
    accommodation_budget_lkr = None
    total_budget_lkr = None
    flight_origin = None
    flight_origin_input = None
    flight_departure_date = None
    flight_passengers = None
    flight_cabin_class = None

    duration_match = re.search(r"\b(\d+)\s*(day|days|week|weeks)\b", lowered)
    if duration_match:
        duration = f"{duration_match.group(1)} {duration_match.group(2)}"
    elif next_required_field == "duration":
        bare_duration_match = re.fullmatch(r"\s*(\d{1,2})\s*", text)
        if bare_duration_match:
            duration = f"{bare_duration_match.group(1)} days"

    if any(hint in lowered for hint in ("flying from", "flight date", "flight departure", "economy", "business", "premium economy", "first class", "first")):
        needs_flights = True
    for hint in NO_HINTS:
        if hint in lowered:
            needs_flights = False
            break
    if needs_flights is None:
        for hint in YES_HINTS:
            if hint in lowered:
                needs_flights = True
                break

    origin, destination = _extract_route_pair(
        text,
        allow_generic_from_to=not _looks_like_flight_detail_message(text),
    )
    if (not origin or not destination) and duration:
        embedded_origin, embedded_destination = _extract_embedded_trip_route_pair(text)
        origin = origin or embedded_origin
        destination = destination or embedded_destination

    if not destination and not _looks_like_flight_detail_message(text):
        dest_match = re.search(r"\bto\s+(.+?)(?:\s+for\s+|\s+in\s+|\s*$)", text, flags=re.IGNORECASE)
        if dest_match:
            destination = _clean_place_fragment(dest_match.group(1))

    if not origin and not (_looks_like_flight_detail_message(text) or contextual_flight_collection):
        origin_match = re.search(r"\bfrom\s+(.+?)(?:\s+to\s+|\s+for\s+|\s+in\s+|\s*$)", text, flags=re.IGNORECASE)
        if origin_match:
            origin = _clean_place_fragment(origin_match.group(1))

    total_budget_patterns = [
        r"\btotal budget(?:\s+is|\s+of|:)?\s*(?:lkr|rs\.?|rupees?)?\s*([\d,]+(?:\.\d+)?)",
        r"\boverall budget(?:\s+is|\s+of|:)?\s*(?:lkr|rs\.?|rupees?)?\s*([\d,]+(?:\.\d+)?)",
    ]
    for pattern in total_budget_patterns:
        total_budget_match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if total_budget_match:
            total_budget_lkr = _normalize_budget_value(total_budget_match.group(1))
            if total_budget_lkr is not None:
                break

    budget_patterns = [
        r"\bbudget(?:\s+is|\s+of|:)?\s*(?:lkr|rs\.?|rupees?)?\s*([\d,]+(?:\.\d+)?)",
        r"\b(?:lkr|rs\.?|rupees?)\s*([\d,]+(?:\.\d+)?)\b",
    ]
    if total_budget_lkr is None:
        for pattern in budget_patterns:
            budget_match = re.search(pattern, lowered, flags=re.IGNORECASE)
            if budget_match:
                total_budget_lkr = _normalize_budget_value(budget_match.group(1))
                if total_budget_lkr is not None:
                    break

    accommodation_budget_patterns = [
        r"\baccommodation budget(?:\s+is|\s+of|:)?\s*(?:lkr|rs\.?|rupees?)?\s*([\d,]+(?:\.\d+)?)",
        r"\bstay budget(?:\s+is|\s+of|:)?\s*(?:lkr|rs\.?|rupees?)?\s*([\d,]+(?:\.\d+)?)",
        r"\bhotel budget(?:\s+is|\s+of|:)?\s*(?:lkr|rs\.?|rupees?)?\s*([\d,]+(?:\.\d+)?)",
    ]
    for pattern in accommodation_budget_patterns:
        accommodation_match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if accommodation_match:
            accommodation_budget_lkr = _normalize_budget_value(accommodation_match.group(1))
            if accommodation_budget_lkr is not None:
                break

    flight_origin_match = re.search(r"\bfly(?:ing)?\s+from\s+([A-Za-z]{3})\b", text, flags=re.IGNORECASE)
    if flight_origin_match:
        flight_origin_input = flight_origin_match.group(1).upper()
        flight_origin = flight_origin_match.group(1).upper()
        needs_flights = True

    airport_origin_match = re.search(r"\bflight origin(?:\s+is|:)?\s*([A-Za-z]{3})\b", text, flags=re.IGNORECASE)
    if airport_origin_match:
        flight_origin_input = airport_origin_match.group(1).upper()
        flight_origin = airport_origin_match.group(1).upper()
        needs_flights = True

    city_origin_match = re.search(
        rf"\b(?:flying|fly|flights?|need flights?)\s+from\s+(.+?){FLIGHT_DETAIL_BOUNDARY}",
        text,
        flags=re.IGNORECASE,
    )
    if city_origin_match and not flight_origin:
        parsed_flight_origin_input = _clean_place_fragment(city_origin_match.group(1))
        parsed_flight_origin = _normalize_airport_code(parsed_flight_origin_input)
        if parsed_flight_origin:
            flight_origin_input = parsed_flight_origin_input
            flight_origin = parsed_flight_origin
            needs_flights = True

    short_origin_match = re.search(
        rf"^\s*from\s+(.+?){FLIGHT_DETAIL_BOUNDARY}",
        text,
        flags=re.IGNORECASE,
    )
    if short_origin_match and not flight_origin and (_looks_like_flight_detail_message(text) or contextual_flight_collection):
        parsed_flight_origin_input = _clean_place_fragment(short_origin_match.group(1))
        parsed_flight_origin = _normalize_airport_code(parsed_flight_origin_input)
        if parsed_flight_origin:
            flight_origin_input = parsed_flight_origin_input
            flight_origin = parsed_flight_origin
            needs_flights = True

    plain_origin_match = re.search(
        rf"\bflight origin(?:\s+is|:)?\s*(.+?){FLIGHT_DETAIL_BOUNDARY}",
        text,
        flags=re.IGNORECASE,
    )
    if plain_origin_match and not flight_origin:
        parsed_flight_origin_input = _clean_place_fragment(plain_origin_match.group(1))
        parsed_flight_origin = _normalize_airport_code(parsed_flight_origin_input)
        if parsed_flight_origin:
            flight_origin_input = parsed_flight_origin_input
            flight_origin = parsed_flight_origin
            needs_flights = True

    departure_date_match = re.search(
        r"\b(?:flight date|departure date|flight departure date)(?:\s+is|:)?\s*([A-Za-z0-9,\-/ ]+)",
        text,
        flags=re.IGNORECASE,
    )
    if departure_date_match:
        parsed_date = _normalize_date_value(departure_date_match.group(1))
        if parsed_date:
            flight_departure_date = parsed_date
            needs_flights = True
    elif needs_flights is True:
        departure_date_match = re.search(r"\bon\s+([A-Za-z0-9,\-/ ]+?)(?:\s+for\s+\d+\s+passengers?|\s*,|\s+(?:economy|premium economy|business|first)(?:\s+class)?|\s*$)", text, flags=re.IGNORECASE)
        if departure_date_match:
            parsed_date = _normalize_date_value(departure_date_match.group(1))
            if parsed_date:
                flight_departure_date = parsed_date
        if not flight_departure_date:
            standalone_date_match = re.search(
                r"\b(\d{4}-\d{2}-\d{2}|\d{4}\s+[A-Za-z]+\s+\d{1,2}|\d{1,2}\s+[A-Za-z]+\s+\d{4}|[A-Za-z]+\s+\d{1,2}\s+\d{4})\b",
                text,
                flags=re.IGNORECASE,
            )
            if standalone_date_match:
                parsed_date = _normalize_date_value(standalone_date_match.group(1))
                if parsed_date:
                    flight_departure_date = parsed_date

    parsed_passengers = _parse_passenger_value(text)
    if parsed_passengers is not None and (
        next_required_field == "flight_passengers"
        or passenger_keywords_present
    ):
        flight_passengers = parsed_passengers
        needs_flights = True

    parsed_cabin_class = _parse_cabin_class(text)
    if parsed_cabin_class:
        flight_cabin_class = parsed_cabin_class
        needs_flights = True

    if ("flight_origin" in missing_fields or contextual_flight_collection) and not flight_origin:
        contextual_flight_origin = _normalize_airport_code(text)
        if contextual_flight_origin:
            flight_origin = contextual_flight_origin
            flight_origin_input = _clean_place_fragment(text)
            needs_flights = True

    if ("flight_departure_date" in missing_fields or contextual_flight_collection) and not flight_departure_date:
        contextual_date = _normalize_date_value(text)
        if contextual_date:
            flight_departure_date = contextual_date
            needs_flights = True
        else:
            standalone_contextual_date_match = re.search(
                r"\b(\d{4}-\d{2}-\d{2}|\d{4}\s+[A-Za-z]+\s+\d{1,2}|\d{1,2}\s+[A-Za-z]+\s+\d{4}|[A-Za-z]+\s+\d{1,2}\s+\d{4})\b",
                text,
                flags=re.IGNORECASE,
            )
            if standalone_contextual_date_match:
                parsed_date = _normalize_date_value(standalone_contextual_date_match.group(1))
                if parsed_date:
                    flight_departure_date = parsed_date
                    needs_flights = True

    if ("flight_passengers" in missing_fields or contextual_flight_collection) and flight_passengers is None:
        contextual_passengers = _parse_passenger_value(text)
        if contextual_passengers is not None:
            flight_passengers = contextual_passengers
            needs_flights = True

    if ("flight_cabin_class" in missing_fields or contextual_flight_collection) and not flight_cabin_class:
        contextual_cabin_class = _parse_cabin_class(text)
        if contextual_cabin_class:
            flight_cabin_class = contextual_cabin_class
            needs_flights = True

    if next_required_field == "total_budget_lkr" and total_budget_lkr is None:
        contextual_budget = _normalize_budget_value(text)
        if contextual_budget is not None:
            total_budget_lkr = contextual_budget

    if next_required_field == "destination" and not destination:
        if (
            text
            and " " not in text.strip()
            and text.strip().lower() not in YES_HINTS
            and text.strip().lower() not in NO_HINTS
            and _normalize_date_value(text) is None
            and _parse_passenger_value(text) is None
        ):
            destination = _clean_place_fragment(text)

    if next_required_field == "origin" and not origin and not _looks_like_flight_detail_message(text):
        if (
            text
            and " " not in text.strip()
            and text.strip().lower() not in YES_HINTS
            and text.strip().lower() not in NO_HINTS
            and _normalize_date_value(text) is None
            and _parse_passenger_value(text) is None
            and _normalize_requirement_value(current_details.destination) != _clean_place_fragment(text)
        ):
            origin = _clean_place_fragment(text)

    return TripRequirements(
        needs_flights=needs_flights,
        origin=origin,
        destination=destination,
        duration=duration,
        accommodation_budget_lkr=accommodation_budget_lkr,
        total_budget_lkr=total_budget_lkr,
        flight_origin_input=flight_origin_input,
        flight_origin=flight_origin,
        flight_departure_date=flight_departure_date,
        flight_search_mode=None,
        flight_passengers=flight_passengers,
        flight_cabin_class=flight_cabin_class,
    )


def _format_greeting_reply() -> str:
    return "Hey, happy to help with this trip. Which city are you flying from?"


def _format_place_name(value: str | None) -> str | None:
    normalized = _normalize_requirement_value(value)
    if not normalized:
        return None
    return " ".join(part.capitalize() for part in normalized.split())


def _format_flight_origin_label(details: TripRequirements) -> str:
    raw_input = _format_place_name(details.flight_origin_input)
    if raw_input:
        return raw_input
    airport_code = _normalize_airport_code(details.flight_origin)
    if airport_code:
        return airport_code
    return "your departure city"


def _format_completion_reply(details: TripRequirements) -> str:
    origin = _format_place_name(details.origin) or "your starting point"
    destination = _format_place_name(details.destination) or "your destination"
    duration = _normalize_requirement_value(details.duration) or "your preferred duration"
    total_budget = _normalize_budget_value(details.total_budget_lkr)
    budget = _normalize_budget_value(details.accommodation_budget_lkr)
    if _normalize_needs_flights(details.needs_flights):
        reply = (
            f"Perfect, I’ve got the full picture now. You’re travelling from {origin} to "
            f"{destination} for {duration}, and I’ll also look for flights from "
            f"{_format_flight_origin_label(details)} on {details.flight_departure_date} for "
            f"{details.flight_passengers} passenger(s) in {details.flight_cabin_class} class."
        )
    else:
        reply = (
            f"Perfect, I’ve got the full picture now. You’re travelling from {origin} to "
            f"{destination} for {duration}. I’ll skip flights and use the budget on stays."
        )
    if total_budget is not None:
        reply += f" I’ll treat LKR {total_budget:,.0f} as the total trip budget."
    if budget is not None:
        reply += f" I’ll also use an accommodation budget of LKR {budget:,.0f} when ranking stays."
    return reply


def _format_missing_reply(details: TripRequirements, missing_fields: list[str]) -> str:
    next_field = _next_required_field(missing_fields)
    prompts = {
        "flight_origin": "Which city are you flying from?",
        "flight_departure_date": "What departure date should I check for the flight?",
        "flight_passengers": "How many travellers should I search for?",
        "flight_cabin_class": "Which cabin class do you want, like economy or business?",
        "total_budget_lkr": "What total budget should I plan around, in LKR?",
        "origin": "Where should the trip start in Sri Lanka?",
        "destination": "Where in Sri Lanka do you want to go?",
        "duration": "How many days should the trip be?",
    }
    if next_field:
        return prompts[next_field]
    return "Tell me the next trip detail."


def _build_extraction_chain(
    model: str,
    api_key: str,
    temperature: float,
    *,
    system_prompt: str,
    output_schema: type[FlightIntakeOutput] | type[TripIntakeOutput],
) -> StructuredExtractionChain:
    llm = ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
        temperature=temperature,
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            (
                "human",
                "Current known structured state:\n{current_state}\n\n"
                "Active intake phase:\n{active_phase}\n\n"
                "Backend-detected missing fields:\n{current_missing_fields}\n\n"
                "Missing fields for the active phase only:\n{active_phase_missing_fields}\n\n"
                "Conversation history:\n{history}\n\n"
                "Latest user message:\n{user_message}",
            ),
        ]
    )
    return prompt | llm.with_structured_output(output_schema)


class IntakeBot:
    phase: IntakePhase

    def __init__(
        self,
        *,
        chain: StructuredExtractionChain | None,
        executor: ThreadPoolExecutor | None,
        timeout_seconds: float,
    ) -> None:
        self._chain = chain
        self._executor = executor
        self._timeout_seconds = timeout_seconds

    def _invoke_chain(self, payload: dict[str, str]) -> object:
        if self._chain is None:
            return None
        try:
            if self._executor is None:
                return self._chain.invoke(payload)
            future = self._executor.submit(self._chain.invoke, payload)
            return future.result(timeout=self._timeout_seconds)
        except (FutureTimeoutError, Exception):
            return None

    def _build_chain_payload(
        self,
        *,
        details: TripRequirements,
        history: list[ConversationTurn],
        user_message: str,
    ) -> dict[str, str]:
        missing_fields = _find_missing_fields(details)
        phase_missing_fields = (
            _find_flight_missing_fields(details)
            if self.phase == "flight"
            else _find_trip_missing_fields(details)
            if self.phase == "trip"
            else []
        )
        return {
            "current_state": details.model_dump_json(indent=2),
            "active_phase": self.phase,
            "current_missing_fields": _format_missing_fields_text(missing_fields),
            "active_phase_missing_fields": _format_missing_fields_text(phase_missing_fields),
            "history": _history_to_text(history),
            "user_message": user_message,
        }


class FlightIntakeBot(IntakeBot):
    phase: IntakePhase = "flight"

    def extract_local(
        self,
        *,
        user_message: str,
        details: TripRequirements,
    ) -> TripRequirements:
        return _flight_output_to_requirements(
            _heuristic_trip_requirements(
                user_message,
                current_details=details,
                current_missing_fields=_find_missing_fields(details),
            )
        )

    def extract(
        self,
        *,
        user_message: str,
        details: TripRequirements,
        history: list[ConversationTurn],
    ) -> tuple[TripRequirements, object | None]:
        payload = self._build_chain_payload(
            details=details,
            history=history,
            user_message=user_message,
        )
        llm_output = self._invoke_chain(payload)
        heuristic_requirements = self.extract_local(user_message=user_message, details=details)
        
        if llm_output:
            llm_requirements = _flight_output_to_requirements(llm_output)
            merged = _merge_trip_requirements(llm_requirements, heuristic_requirements)
            return merged, llm_output
            
        return heuristic_requirements, None


class TripIntakeBot(IntakeBot):
    phase: IntakePhase = "trip"

    def extract_local(
        self,
        *,
        user_message: str,
        details: TripRequirements,
    ) -> TripRequirements:
        return _trip_output_to_requirements(
            _heuristic_trip_requirements(
                user_message,
                current_details=details,
                current_missing_fields=_find_missing_fields(details),
            )
        )

    def extract(
        self,
        *,
        user_message: str,
        details: TripRequirements,
        history: list[ConversationTurn],
    ) -> tuple[TripRequirements, object | None]:
        payload = self._build_chain_payload(
            details=details,
            history=history,
            user_message=user_message,
        )
        llm_output = self._invoke_chain(payload)
        heuristic_requirements = self.extract_local(user_message=user_message, details=details)
        
        if llm_output:
            llm_requirements = _trip_output_to_requirements(llm_output)
            merged = _merge_trip_requirements(llm_requirements, heuristic_requirements)
            return merged, llm_output
            
        return heuristic_requirements, None


class TravelIntakeService:
    def __init__(
        self,
        *,
        model: str = "gemini-2.5-flash-lite",
        google_api_key: str | None = None,
        temperature: float = 0,
        chain: StructuredExtractionChain | None = None,
        flight_chain: StructuredExtractionChain | None = None,
        trip_chain: StructuredExtractionChain | None = None,
        use_llm: bool = True,
    ) -> None:
        api_key = google_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self._flight_chain = flight_chain or chain
        self._trip_chain = trip_chain or chain
        self._llm_timeout_seconds = float(os.getenv("CHAT_LLM_TIMEOUT_SECONDS", "6"))
        self._executor = ThreadPoolExecutor(max_workers=2) if use_llm else None
        if use_llm and api_key:
            if self._flight_chain is None:
                self._flight_chain = _build_extraction_chain(
                    model=model,
                    api_key=api_key,
                    temperature=temperature,
                    system_prompt=FLIGHT_EXTRACTION_SYSTEM_PROMPT,
                    output_schema=FlightIntakeOutput,
                )
            if self._trip_chain is None:
                self._trip_chain = _build_extraction_chain(
                    model=model,
                    api_key=api_key,
                    temperature=temperature,
                    system_prompt=TRIP_EXTRACTION_SYSTEM_PROMPT,
                    output_schema=TripIntakeOutput,
                )
        self._flight_bot = FlightIntakeBot(
            chain=self._flight_chain,
            executor=self._executor,
            timeout_seconds=self._llm_timeout_seconds,
        )
        self._trip_bot = TripIntakeBot(
            chain=self._trip_chain,
            executor=self._executor,
            timeout_seconds=self._llm_timeout_seconds,
        )

    def process_turn(
        self,
        user_message: str,
        session: ChatSessionState | None = None,
    ) -> ChatResponse:
        incoming_session = session or ChatSessionState()
        required_flight_details = _require_flights(incoming_session.trip_requirements)
        active_session = ChatSessionState(
            trip_requirements=required_flight_details,
            history=incoming_session.history,
            active_phase=_current_intake_stage(required_flight_details),
        )
        current_missing_fields = _find_missing_fields(active_session.trip_requirements)
        current_phase = _current_intake_stage(active_session.trip_requirements)

        merged_requirements = active_session.trip_requirements
        started_phase = current_phase

        if _find_flight_missing_fields(merged_requirements):
            flight_requirements, flight_llm_out = self._flight_bot.extract(
                user_message=user_message,
                details=merged_requirements,
                history=active_session.history,
            )
            if flight_llm_out and not getattr(flight_llm_out, "is_valid_input", True):
                assistant_reply = getattr(flight_llm_out, "conversational_reply", "I need a bit more info!") or "I need a bit more info!"
                return ChatResponse(
                    session=ChatSessionState(
                        trip_requirements=active_session.trip_requirements,
                        history=[
                            *active_session.history,
                            ConversationTurn(role="user", content=user_message),
                            ConversationTurn(role="assistant", content=assistant_reply),
                        ],
                        active_phase=current_phase,
                    ),
                    turn=ChatTurnResult(
                        assistant_reply=assistant_reply,
                        extracted_trip_requirements=active_session.trip_requirements,
                        active_phase=current_phase,
                        missing_fields=current_missing_fields,
                        is_complete=not current_missing_fields,
                    )
                )
            merged_requirements = _merge_trip_requirements(merged_requirements, flight_requirements)

        # Check trip info if flight is complete or bypassed
        if not _find_flight_missing_fields(merged_requirements) and _find_trip_missing_fields(merged_requirements):
            trip_requirements, trip_llm_out = self._trip_bot.extract(
                user_message=user_message,
                details=merged_requirements,
                history=active_session.history,
            )
            if trip_llm_out and not getattr(trip_llm_out, "is_valid_input", True):
                assistant_reply = getattr(trip_llm_out, "conversational_reply", "I need a bit more info!") or "I need a bit more info!"
                return ChatResponse(
                    session=ChatSessionState(
                        trip_requirements=active_session.trip_requirements,
                        history=[
                            *active_session.history,
                            ConversationTurn(role="user", content=user_message),
                            ConversationTurn(role="assistant", content=assistant_reply),
                        ],
                        active_phase=current_phase,
                    ),
                    turn=ChatTurnResult(
                        assistant_reply=assistant_reply,
                        extracted_trip_requirements=active_session.trip_requirements,
                        active_phase=current_phase,
                        missing_fields=current_missing_fields,
                        is_complete=not current_missing_fields,
                    )
                )
            merged_requirements = _merge_trip_requirements(merged_requirements, trip_requirements)

        merged_requirements = _require_flights(merged_requirements)
        missing_fields = _find_missing_fields(merged_requirements)
        active_phase = _current_intake_stage(merged_requirements)
        active_phase_missing_fields = _find_active_phase_missing_fields(merged_requirements)
        if missing_fields:
            assistant_reply = _format_missing_reply(merged_requirements, active_phase_missing_fields or missing_fields)
        else:
            assistant_reply = _format_completion_reply(merged_requirements)

        turn = ChatTurnResult(
            assistant_reply=assistant_reply,
            extracted_trip_requirements=merged_requirements,
            active_phase=active_phase,
            missing_fields=missing_fields,
            is_complete=not missing_fields,
        )
        updated_session = ChatSessionState(
            trip_requirements=merged_requirements,
            history=[
                *active_session.history,
                ConversationTurn(role="user", content=user_message),
                ConversationTurn(role="assistant", content=assistant_reply),
            ],
            active_phase=active_phase,
        )
        return ChatResponse(session=updated_session, turn=turn)
