from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class TripRequirements(BaseModel):
    origin: Optional[str] = Field(
        default=None,
        description="The journey starting location provided by the user.",
    )
    destination: Optional[str] = Field(
        default=None,
        description="The trip destination provided by the user.",
    )
    duration: Optional[str] = Field(
        default=None,
        description="The trip duration provided by the user, such as 2 days or 1 week.",
    )


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatTurnResult(BaseModel):
    assistant_reply: str = Field(
        description="Natural assistant reply for the user."
    )
    extracted_trip_requirements: TripRequirements = Field(
        description="Best-effort structured extraction from the current turn."
    )
    missing_fields: List[Literal["origin", "destination", "duration"]] = Field(
        default_factory=list,
        description="Trip fields that are still missing after this turn.",
    )
    is_complete: bool = Field(
        description="True only when origin, destination, and duration are all known."
    )


class ChatSessionState(BaseModel):
    trip_requirements: TripRequirements = Field(default_factory=TripRequirements)
    history: List[ConversationTurn] = Field(default_factory=list)


class ChatResponse(BaseModel):
    session: ChatSessionState
    turn: ChatTurnResult
