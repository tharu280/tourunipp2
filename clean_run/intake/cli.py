from __future__ import annotations

import argparse
import json

from .schemas import ChatSessionState
from .service import TravelIntakeService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run clean_run intake chatbot step.")
    parser.add_argument("--message", required=True, help="User message to process.")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable Gemini and use heuristic extraction only.",
    )
    parser.add_argument(
        "--session-json",
        default=None,
        help="Optional prior ChatSessionState JSON.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    session = None
    if args.session_json:
        session = ChatSessionState.model_validate_json(args.session_json)
    response = TravelIntakeService(use_llm=not args.no_llm).process_turn(args.message, session)
    print(
        json.dumps(
            {
                "session": response.session.model_dump(),
                "turn": response.turn.model_dump(),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
