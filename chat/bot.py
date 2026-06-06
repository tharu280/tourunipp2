from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable, Optional

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from chat.schemas import (
    ChatResponse,
    ChatSessionState,
    ChatTurnResult,
    ConversationTurn,
    TripRequirements,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "google_routes" / ".env")

SYSTEM_PROMPT = """
You are a friendly travel intake chatbot.

Your only job is to help the user provide these three trip details:
1. starting location
2. destination
3. duration

Behavior rules:
- Reply naturally, warmly, and conversationally.
- Sound helpful and upbeat, but keep replies concise.
- If the user is just greeting you or making small talk, respond like a friendly human first, then gently guide them into the trip planning conversation.
- If the user gives one or two of the required trip details, acknowledge them and ask only for the missing ones.
- If the user gives all three details, confirm them clearly with a friendly wrap-up and do not ask unnecessary follow-up questions.
- If the user says something related to the trip but incomplete, keep the conversation focused on collecting the missing trip details.
- If the user goes slightly off track, gently steer them back to the three required details.
- Do not invent missing details.
- Prefer short, clear follow-up questions.
- Avoid sounding robotic or repetitive.
- Avoid asking all three questions in the exact same way every time.
- Prefer one gentle invitation over an interrogation-style list.
- Treat "start location" and "origin" as the same thing.
- Treat "how long", "duration", "days", and "trip length" as the same concept.
- When all three details are available, end with an inviting line similar to:
  "Awesome, let me take care of your travel plan from {origin} to {destination} for you."

Known trip details so far:
- Origin: {origin}
- Destination: {destination}
- Duration: {duration}

Conversation so far:
{history}
"""


def _history_to_text(history: Iterable[ConversationTurn]) -> str:
    items = list(history)
    if not items:
        return "No previous conversation."
    return "\n".join(f"{turn.role.title()}: {turn.content}" for turn in items)


def _merge_trip_requirements(
    current: TripRequirements,
    incoming: TripRequirements,
) -> TripRequirements:
    return TripRequirements(
        origin=incoming.origin or current.origin,
        destination=incoming.destination or current.destination,
        duration=incoming.duration or current.duration,
    )


def _find_missing_fields(details: TripRequirements) -> list[str]:
    missing = []
    if not details.origin:
        missing.append("origin")
    if not details.destination:
        missing.append("destination")
    if not details.duration:
        missing.append("duration")
    return missing


def _clean_place_fragment(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip(" ,.-")
    return cleaned or None


def _heuristic_trip_requirements(message: str) -> TripRequirements:
    text = " ".join(message.strip().split())
    lowered = text.lower()

    origin = None
    destination = None
    duration = None

    duration_match = re.search(r"\b(\d+)\s*(day|days|week|weeks)\b", lowered)
    if duration_match:
        amount = duration_match.group(1)
        unit = duration_match.group(2)
        duration = f"{amount} {unit}"

    pattern_pairs = [
        r"\bfrom\s+(?P<origin>.+?)\s+to\s+(?P<destination>.+?)(?:\s+for\s+|\s+in\s+|\s*$)",
        r"\bgo(?:ing)?\s+to\s+(?P<destination>.+?)\s+from\s+(?P<origin>.+?)(?:\s+for\s+|\s+in\s+|\s*$)",
        r"\btravel(?:ling)?\s+from\s+(?P<origin>.+?)\s+to\s+(?P<destination>.+?)(?:\s+for\s+|\s+in\s+|\s*$)",
    ]
    for pattern in pattern_pairs:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            origin = _clean_place_fragment(match.group("origin"))
            destination = _clean_place_fragment(match.group("destination"))
            break

    if not destination:
        dest_match = re.search(r"\bto\s+(.+?)(?:\s+for\s+|\s+in\s+|\s*$)", text, flags=re.IGNORECASE)
        if dest_match:
            destination = _clean_place_fragment(dest_match.group(1))

    if not origin:
        origin_match = re.search(r"\bfrom\s+(.+?)(?:\s+to\s+|\s+for\s+|\s+in\s+|\s*$)", text, flags=re.IGNORECASE)
        if origin_match:
            origin = _clean_place_fragment(origin_match.group(1))

    return TripRequirements(origin=origin, destination=destination, duration=duration)


def _looks_like_greeting(message: str) -> bool:
    normalized = " ".join(message.lower().strip().split())
    greetings = {
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
    return normalized in greetings


def _format_greeting_reply() -> str:
    return (
        "Hey! I'd love to help with your trip. Tell me where you'd like to go, "
        "and we can figure out the starting point and trip length together."
    )


def _format_completion_reply(details: TripRequirements) -> str:
    origin = details.origin or "your starting point"
    destination = details.destination or "your destination"
    duration = details.duration or "your preferred duration"
    return (
        f"Perfect, I’ve got everything I need: starting from {origin}, heading to "
        f"{destination}, for {duration}. Let me take care of your travel plan from "
        f"{origin} to {destination} for you."
    )


class TravelIntakeChatbot:
    def __init__(
        self,
        model: str = "gemini-2.5-flash-lite",
        google_api_key: Optional[str] = None,
        temperature: float = 0,
    ) -> None:
        api_key = google_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY or GOOGLE_API_KEY is required to run the travel chatbot."
            )

        llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            temperature=temperature,
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                ("human", "Latest user message: {user_message}"),
            ]
        )

        self._chain = prompt | llm.with_structured_output(ChatTurnResult)

    def process_turn(
        self,
        user_message: str,
        session: Optional[ChatSessionState] = None,
    ) -> ChatResponse:
        active_session = session or ChatSessionState()
        current_missing_fields = _find_missing_fields(active_session.trip_requirements)

        if _looks_like_greeting(user_message) and len(active_session.history) == 0:
            assistant_reply = _format_greeting_reply()
            turn = ChatTurnResult(
                assistant_reply=assistant_reply,
                extracted_trip_requirements=active_session.trip_requirements.model_dump(),
                missing_fields=current_missing_fields,
                is_complete=not current_missing_fields,
            )
            updated_session = ChatSessionState(
                trip_requirements=active_session.trip_requirements,
                history=[
                    *active_session.history,
                    ConversationTurn(role="user", content=user_message),
                    ConversationTurn(role="assistant", content=assistant_reply),
                ],
            )
            return ChatResponse(session=updated_session, turn=turn)

        raw_result = self._chain.invoke(
            {
                "origin": active_session.trip_requirements.origin or "unknown",
                "destination": active_session.trip_requirements.destination or "unknown",
                "duration": active_session.trip_requirements.duration or "unknown",
                "history": _history_to_text(active_session.history),
                "user_message": user_message,
            }
        )

        merged_requirements = _merge_trip_requirements(
            active_session.trip_requirements,
            raw_result.extracted_trip_requirements,
        )
        heuristic_requirements = _heuristic_trip_requirements(user_message)
        merged_requirements = _merge_trip_requirements(
            merged_requirements,
            heuristic_requirements,
        )
        missing_fields = _find_missing_fields(merged_requirements)
        assistant_reply = raw_result.assistant_reply.strip()
        if not missing_fields:
            assistant_reply = _format_completion_reply(merged_requirements)

        turn = ChatTurnResult(
            assistant_reply=assistant_reply,
            extracted_trip_requirements=merged_requirements.model_dump(),
            missing_fields=missing_fields,
            is_complete=not missing_fields,
        )
        updated_session = ChatSessionState(
            trip_requirements=merged_requirements,
            history=[
                *active_session.history,
                ConversationTurn(role="user", content=user_message),
                ConversationTurn(role="assistant", content=turn.assistant_reply),
            ],
        )

        return ChatResponse(session=updated_session, turn=turn)

    def reply(
        self,
        user_message: str,
        session: Optional[ChatSessionState] = None,
    ) -> ChatSessionState:
        return self.process_turn(user_message, session).session

    def respond(
        self,
        user_message: str,
        session: Optional[ChatSessionState] = None,
    ) -> ChatTurnResult:
        return self.process_turn(user_message, session).turn
