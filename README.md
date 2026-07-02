---
title: Route MVP
emoji: 🌴
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
---

# Route MVP

This repo now includes a small Google Routes fetcher for collecting the default
route plus available alternatives and saving them as JSON for later scoring.

It also now includes a small Gemini-powered trip intake chatbot under
`chat/` for collecting:
- origin
- destination
- duration

It also includes:
- `roadlk/` for route-side incident enrichment
- `weather/` for route-segment weather enrichment
- `crowd/` for holiday/weather/road-pressure trip scoring
- `nsgaii/` for Pareto-style route ranking across enriched route profiles
- `trip_graph/` for the LangGraph route-first backend flow
- `api.py` for a FastAPI backend
- `streamlit_app.py` for a chat-first route intelligence dashboard

## Hugging Face Spaces

This repo is now prepared for a **Hugging Face Docker Space** that runs the
Streamlit app directly.

Before you push it to HF:

1. Create a new **Docker Space**.
2. Push this repository to the Space.
3. Add these Space secrets:

```env
GOOGLE_MAPS_API_KEY=your_google_maps_key
GEMINI_API_KEY=your_gemini_key
```

Notes:
- The app entrypoint is `streamlit_app.py`.
- The Docker image launches Streamlit on the HF-provided `PORT`.
- The `outputs/` directory is created in the container at runtime.
- HF Space disk is ephemeral by default, so saved itinerary files in `outputs/`
  can disappear after restarts unless you attach persistent storage.

## Local Setup

1. Create a `.env` file in the project root. You can start from `.env.example`:

```env
GOOGLE_MAPS_API_KEY=your_demo_or_regular_maps_key_here
GEMINI_API_KEY=your_gemini_key_here
```

2. Install the Python dependencies:

```bash
python3 -m pip install -r requirements.txt
```

## Run the FastAPI backend

```bash
python3 -m uvicorn api:app --host 0.0.0.0 --port 7860
```

API endpoints:
- `GET /health`
- `POST /chat`
- `POST /plan`

## Run the intake chatbot

```bash
python3 -m chat.cli
```

The chatbot reads `GEMINI_API_KEY` from the project root `.env` or
`google_routes/.env`.

## Run the Streamlit dashboard

```bash
python3 -m streamlit run streamlit_app.py
```

The dashboard uses:
- chat intake for origin, destination, and duration
- Google route alternatives
- curated attraction enrichment
- lodging enrichment
- optional Gemini refinement
- optional RoadLK, weather, and crowd scoring
- NSGA-II style route recommendation
- a LangGraph backend flow under `trip_graph/`
- a Streamlit-first route intelligence interface with map, pressure, route, stay, and itinerary views

## Run NSGA-II style route selection

```bash
python3 -m nsgaii.select_routes \
  --input outputs/enriched-routes-20260605-024754.json
```

The selector automatically uses whatever objectives are available across all
routes in the input file, such as distance, duration, attraction value,
lodging quality, RoadLK risk, weather risk, and crowd pressure.

## Fetch and save route alternatives

```bash
python3 -m google_routes.fetch_routes \
  --origin-lat 6.9271 \
  --origin-lng 79.8612 \
  --destination-lat 7.2906 \
  --destination-lng 80.6337
```

By default this writes a JSON file under `outputs/`.

## Saved route shape

Each saved file contains:

- origin and destination coordinates
- route count
- one object per returned route
- route labels
- distance
- duration
- encoded polyline
- raw route payload for later enrichment
