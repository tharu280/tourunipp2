from __future__ import annotations

import argparse
import json
from typing import Iterable

from clean_run.intake.schemas import ChatSessionState, ConversationTurn
from clean_run.intake.service import TravelIntakeService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interactive isolated CLI for the clean_run intake chatbot."
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable Gemini and use heuristic extraction only.",
    )
    parser.add_argument(
        "--show-state",
        action="store_true",
        help="Print collected slot values after every turn.",
    )
    parser.add_argument(
        "--show-history",
        action="store_true",
        help="Print transcript history after every turn.",
    )
    parser.add_argument(
        "--session-json",
        default=None,
        help="Optional prior ChatSessionState JSON to preload.",
    )
    return parser.parse_args()


def _format_state(session: ChatSessionState) -> str:
    requirements = session.trip_requirements.model_dump()
    ordered_keys = [
        "flight_origin_input",
        "flight_origin",
        "flight_departure_date",
        "flight_passengers",
        "flight_cabin_class",
        "total_budget_lkr",
        "accommodation_budget_lkr",
        "origin",
        "destination",
        "duration",
    ]
    lines = ["Current state:"]
    for key in ordered_keys:
        lines.append(f"  - {key}: {requirements.get(key)}")
    return "\n".join(lines)


def _format_history(history: Iterable[ConversationTurn]) -> str:
    turns = list(history)
    if not turns:
        return "Transcript: <empty>"
    lines = ["Transcript:"]
    for turn in turns:
        speaker = "You" if turn.role == "user" else "Bot"
        lines.append(f"  {speaker}: {turn.content}")
    return "\n".join(lines)


def _print_session_debug(
    session: ChatSessionState,
    *,
    show_state: bool,
    show_history: bool,
) -> None:
    if show_state:
        print(_format_state(session))
    if show_history:
        print(_format_history(session.history))


def _load_session(session_json: str | None) -> ChatSessionState | None:
    if not session_json:
        return None
    return ChatSessionState.model_validate_json(session_json)


def main() -> None:
    args = parse_args()
    service = TravelIntakeService(use_llm=not args.no_llm)
    session = _load_session(args.session_json)

    print("Isolated intake bot ready.")
    print("Commands: /state, /history, /reset, /json, /exit")

    while True:
        try:
            message = input("you> ").strip()
        except EOFError:
            print("\nbye")
            break
        except KeyboardInterrupt:
            print("\nbye")
            break

        if not message:
            continue

        if message in {"/exit", "/quit"}:
            print("bye")
            break
        if message == "/reset":
            session = None
            print("bot> session reset")
            continue
        if message == "/state":
            if session is None:
                print("Current state: <empty>")
            else:
                print(_format_state(session))
            continue
        if message == "/history":
            if session is None:
                print("Transcript: <empty>")
            else:
                print(_format_history(session.history))
            continue
        if message == "/json":
            payload = session.model_dump() if session else {}
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            continue

        response = service.process_turn(message, session)
        session = response.session

        print(f"bot> {response.turn.assistant_reply}")
        print(f"missing> {', '.join(response.turn.missing_fields) or 'none'}")
        print(f"complete> {response.turn.is_complete}")
        _print_session_debug(
            session,
            show_state=args.show_state,
            show_history=args.show_history,
        )


if __name__ == "__main__":
    main()
