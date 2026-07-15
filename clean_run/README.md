# clean_run

This is the clean backend package for TourUni / RouteMVP.

Use this as the backend source for hosting. The important detail is that the
deployment root should contain the `clean_run/` package folder, then run:

```bash
uvicorn clean_run.api:app --host 0.0.0.0 --port 7860
```

Do not flatten the contents of `clean_run/` into the hosting root unless you
also rewrite imports. The package imports are intentionally `clean_run.*`.

Backend-only install:

```bash
python3 -m pip install -r clean_run/requirements.txt
```

Required environment variables are loaded from deployment secrets, `.env`, or
`clean_run/atlas-credentials.env`:

- `GOOGLE_MAPS_API_KEY`
- `GEMINI_API_KEY`
- `WEATHER_API_KEY`
- `FLIGHT_API_TOKEN`
- `MONGODB_URI`
- `MONGODB_DATABASE`
- `MONGODB_COLLECTION`
- `JWT_SECRET` (at least 32 random characters)

Authentication settings:

- `JWT_ISSUER=touruni-api`
- `JWT_AUDIENCE=touruni-pwa`
- `ACCESS_TOKEN_MINUTES=15`
- `REFRESH_TOKEN_DAYS=30`
- `REFRESH_COOKIE_NAME=touruni_refresh_token`
- `COOKIE_SECURE=true` in hosted HTTPS environments

Generate a production JWT secret with:

```bash
openssl rand -hex 32
```

The same MongoDB database is used for `users`, `refresh_tokens`, and the configured
trip-session collection. Passwords are Argon2 hashes. Access tokens are short-lived
JWTs kept in frontend memory, while rotating refresh tokens are stored only in a
secure HTTP-only browser cookie and as SHA-256 hashes in MongoDB.

Main API entrypoint:

- `GET /health`
- `POST /chat`
- `POST /auth/signup`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /auth/me`
- `POST /plan`
- `GET /sessions/{session_id}`
- `GET /sessions/{session_id}/dashboard`
- `GET /sessions/{session_id}/chatbot-context`
- `POST /sessions/{session_id}/refresh-intelligence`
- `POST /sessions/{session_id}/contextual-alternatives`
- `POST /sessions/{session_id}/emotion-checkins`

When `/plan` receives a valid bearer access token, the saved trip session is tagged
with the authenticated `user_id`. Existing anonymous planner calls remain compatible
during this first authentication phase.

Contextual alternatives are generated on demand for planned attractions affected
by crowd or weather risk. They are ranked using weather suitability, crowd-relief
potential, distance, user interests, and OpenStreetMap metadata quality. Results
are temporary recommendations and do not modify the session or itinerary.

Emotion check-ins are opt-in and privacy-safe by contract. The mobile app should
run the CNN locally and send only `emotion_label`, confidence, top predictions,
attraction metadata, and timestamp. Raw images are not accepted or stored by the
backend.

Goal:

- rebuild the backend in smaller verified steps
- keep each step isolated and testable
- avoid dragging old frontend or Streamlit assumptions into the new backend

Migration order:

1. intake chatbot
2. trip resolution
3. route generation
4. road enrichment
5. weather enrichment
6. crowd enrichment
7. traffic enrichment
8. travel windows
9. itinerary assembly
10. API wrapper
11. flight intake and cached fare lookup
12. mongodb session persistence

Current status:

- `step_01_intake`: implemented and tested
- `step_02_resolve_trip`: implemented and tested
- `step_03_route_generation`: implemented and tested
- `step_04_place_enrichment`: implemented and tested
- `step_05_road_enrichment`: implemented and tested
- `step_06_weather_enrichment`: implemented and tested
- `step_07_crowd_enrichment`: implemented and tested
- `step_08_traffic_enrichment`: implemented and tested
- `step_09_travel_windows`: implemented and tested
- `step_10_itinerary_and_assembly`: implemented and tested
- `step_11_flight_search`: implemented and tested
- `step_12_session_persistence`: implemented and tested

Useful commands:

```bash
python3 -m clean_run.intake.cli --no-llm --message "Plan a trip from Colombo to Kandy for 2 days."
python3 -m clean_run.trip.cli --origin Colombo --destination Kandy --duration "2 days"
python3 -m clean_run.routes.cli --origin Colombo --destination Kandy --duration "2 days"
python3 -m clean_run.flights.cli --origin DXB --departure-date 2026-07-01 --search-mode single_day --cabin-class economy --total-budget-lkr 300000
python3 -m clean_run.pipeline.cli --origin Colombo --destination Kandy --duration "1 day" --start-date 2026-06-12 --stop-after final
python3 -m clean_run.pipeline.cli --origin Colombo --destination Kandy --duration "3 days" --start-date 2026-06-20 --total-budget-lkr 300000 --flight-origin DXB --flight-departure-date 2026-07-05 --flight-usd-to-lkr-rate 300
python3 -m unittest clean_run.tests.test_intake_service
python3 -m unittest clean_run.tests.test_trip_resolution
python3 -m unittest clean_run.tests.test_route_generation
python3 -m unittest clean_run.tests.test_flights_service
python3 -m unittest clean_run.tests.test_session_repository
python3 -m unittest clean_run.tests.test_clean_pipeline
```
