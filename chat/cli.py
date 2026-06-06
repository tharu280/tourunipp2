from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chat.bot import TravelIntakeChatbot
from chat.schemas import ChatSessionState


def main() -> None:
    bot = TravelIntakeChatbot()
    session = ChatSessionState()

    print("Travel intake chatbot")
    print("Type 'exit' to stop.\n")

    while True:
        user_message = input("You: ").strip()
        if not user_message:
            continue
        if user_message.lower() in {"exit", "quit"}:
            print("Chat ended.")
            break

        response = bot.process_turn(user_message, session)
        turn = response.turn
        session = response.session

        print(f"Bot: {turn.assistant_reply}")
        print(
            "Collected:",
            {
                "origin": turn.extracted_trip_requirements.origin,
                "destination": turn.extracted_trip_requirements.destination,
                "duration": turn.extracted_trip_requirements.duration,
            },
        )
        print(f"Missing: {turn.missing_fields}\n")

        if turn.is_complete:
            print("Trip intake complete.")
            break


if __name__ == "__main__":
    main()
