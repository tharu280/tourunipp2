import asyncio
from intake.service import TravelIntakeService
from intake.schemas import ChatSessionState
import os

def main():
    print(f"GOOGLE_API_KEY is set: {'GOOGLE_API_KEY' in os.environ}")
    service = TravelIntakeService(use_llm=True)
    session = ChatSessionState()
    
    print("\n--- Test 1: User says 'hey' ---")
    user_msg = "hey"
    # To debug, let's manually invoke the _flight_bot extract
    bot = service._flight_bot
    history = session.history
    details = session.trip_requirements
    
    payload = bot._build_chain_payload(details=details, history=history, user_message=user_msg)
    print("Invoking LLM chain...")
    try:
        llm_out = bot._invoke_chain(payload)
        print("LLM Output:", llm_out)
    except Exception as e:
        print("LLM Error:", e)

    response = service.process_turn(user_msg, session)
    print(f"Final Bot Reply: {response.turn.assistant_reply}")

if __name__ == "__main__":
    main()
