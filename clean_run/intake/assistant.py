import json
from typing import Any

from clean_run.integrations.gemini_client import generate_chat_response

SYSTEM_PROMPT = """You are the TourUni Trip Assistant, a helpful AI travel guide for Sri Lanka.
Your job is to answer the user's questions about their current trip plan using ONLY the provided trip context.

CRITICAL RULES:
1. Answer ONLY from the supplied trip context below.
2. NEVER invent live weather, crowd, traffic, hotel, flight, or price data. If it is not in the context, clearly say the information is missing, unavailable, or estimated.
3. Distinguish itinerary decisions from temporary recommendations.
4. Never silently modify the package. If the user asks for an itinerary change, explain the recommendation but require explicit confirmation before changing anything (the system currently does not auto-modify, so just advise them).
5. Prefer concise, useful mobile answers.
6. Mention the relevant day, attraction, or accommodation when answering.
7. Explain why a recommendation was made based on the context (e.g. weather, crowd, roads, budget, mood).

TRIP CONTEXT:
{context_json}
"""

def handle_assistant_chat(message: str, history: list[dict[str, Any]], context_payload: dict[str, Any]) -> str:
    system_text = SYSTEM_PROMPT.format(
        context_json=json.dumps(context_payload, ensure_ascii=True, separators=(",", ":")),
    )

    messages: list[dict[str, str]] = []
    for item in history[-20:]:
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        messages.append({"role": role, "content": content[:4_000]})

    messages.append({"role": "user", "content": message.strip()[:4_000]})
    return generate_chat_response(
        messages=messages,
        system_instruction=system_text,
    )
