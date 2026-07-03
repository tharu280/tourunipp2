from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

IntakePhase = Literal["flight", "trip", "complete"]


class TripRequirements(BaseModel):
    needs_flights: bool | None = Field(default=None)
    origin: str | None = Field(default=None)
    destination: str | None = Field(default=None)
    duration: str | None = Field(default=None)
    accommodation_budget_lkr: float | None = Field(default=None)
    total_budget_lkr: float | None = Field(default=None)
    flight_origin_input: str | None = Field(default=None)
    flight_origin: str | None = Field(default=None)
    flight_departure_date: str | None = Field(default=None)
    flight_search_mode: str | None = Field(default=None)
    flight_passengers: int | None = Field(default=None)
    flight_cabin_class: str | None = Field(default=None)


class FlightIntakeOutput(BaseModel):
    is_valid_input: bool = Field(
        default=True,
        description="True if the user provided travel details or answered a question. False if the user just said a greeting (like 'hi', 'hey') or made a vague statement.",
    )
    conversational_reply: str | None = Field(
        default=None,
        description="If is_valid_input is False, write a polite conversational response asking for the missing information.",
    )
    flight_origin_input: str | None = Field(
        default=None,
        description="The city or airport the user will fly from, e.g. Dubai or DXB.",
    )
    flight_origin: str | None = Field(
        default=None,
        description="Likely IATA airport code for the flight origin when obvious, e.g. DXB.",
    )
    flight_departure_date: str | None = Field(
        default=None,
        description="Flight departure date. Prefer ISO format YYYY-MM-DD when the user gives a full date.",
    )
    flight_passengers: int | None = Field(default=None, description="Number of flight passengers.")
    flight_cabin_class: str | None = Field(
        default=None,
        description="Cabin class such as economy, premium_economy, business, or first.",
    )
    total_budget_lkr: float | None = Field(
        default=None,
        description="Total trip budget in LKR, before flight cost is deducted.",
    )
    missing_info: str | None = Field(default=None, description="Flight-phase field that is still missing.")


class TripIntakeOutput(BaseModel):
    is_valid_input: bool = Field(
        default=True,
        description="True if the user provided travel details or answered a question. False if the user just said a greeting (like 'hi', 'hey') or made a vague statement.",
    )
    conversational_reply: str | None = Field(
        default=None,
        description="If is_valid_input is False, write a polite conversational response asking for the missing information.",
    )
    origin: str | None = Field(default=None, description="Sri Lanka trip start location.")
    destination: str | None = Field(default=None, description="Sri Lanka trip destination.")
    duration: str | None = Field(default=None, description="Trip duration, e.g. 4 days.")
    missing_info: str | None = Field(default=None, description="Trip-phase field that is still missing.")


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatTurnResult(BaseModel):
    assistant_reply: str
    extracted_trip_requirements: TripRequirements
    active_phase: IntakePhase = "flight"
    missing_fields: list[
        Literal[
            "needs_flights",
            "origin",
            "destination",
            "duration",
            "total_budget_lkr",
            "flight_origin",
            "flight_departure_date",
            "flight_passengers",
            "flight_cabin_class",
        ]
    ] = Field(default_factory=list)
    is_complete: bool


class ChatSessionState(BaseModel):
    trip_requirements: TripRequirements = Field(default_factory=TripRequirements)
    history: list[ConversationTurn] = Field(default_factory=list)
    active_phase: IntakePhase = "flight"


class ChatResponse(BaseModel):
    session: ChatSessionState
    turn: ChatTurnResult
