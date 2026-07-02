# Isolated Bot

This folder is a tiny CLI sandbox for the `clean_run` intake chatbot.

Use it when you want to test only the conversation flow and slot collection,
without the React UI, planner pipeline, route engine, or Mongo session layer.

## Run

From `/Users/dilshantharushika/Desktop/routemvp/tourunipp2`:

```bash
python3 -m clean_run.isolated_bot.cli --no-llm --show-state
```

Or with Gemini enabled:

```bash
python3 -m clean_run.isolated_bot.cli --show-state
```

## Commands

- `/state` shows the current collected trip fields
- `/history` shows the chat transcript
- `/reset` clears the session and starts fresh
- `/exit` or `/quit` closes the bot

## Suggested test flow

```text
hey
dubai
2026 july 20
1 traveller
economy is fine
500000
colombo
badulla
4 days
```

