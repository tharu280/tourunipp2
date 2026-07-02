from __future__ import annotations

import unittest

from clean_run.intake.schemas import (
    ChatSessionState,
    ConversationTurn,
    FlightIntakeOutput,
    TripIntakeOutput,
    TripRequirements,
)
from clean_run.intake.service import TravelIntakeService


class FakeChain:
    def __init__(self, result: TripRequirements) -> None:
        self._result = result
        self.payloads: list[dict[str, str]] = []

    def invoke(self, payload: dict[str, str]) -> TripRequirements:
        self.payloads.append(payload)
        return self._result


def _empty_llm_result() -> TripRequirements:
    return TripRequirements()


class TravelIntakeServiceTests(unittest.TestCase):
    def test_greeting_starts_with_flight_details_not_yes_no_gate(self) -> None:
        service = TravelIntakeService(chain=None, use_llm=False)
        response = service.process_turn("hey")

        self.assertTrue(response.session.trip_requirements.needs_flights)
        self.assertNotIn("needs_flights", response.turn.missing_fields)
        self.assertIn("flight_origin", response.turn.missing_fields)
        self.assertIn("flight_departure_date", response.turn.missing_fields)
        self.assertIn("flight_passengers", response.turn.missing_fields)
        self.assertIn("flight_cabin_class", response.turn.missing_fields)
        self.assertIn("which city are you flying from", response.turn.assistant_reply.lower())
        self.assertNotIn("departure date", response.turn.assistant_reply.lower())
        self.assertNotIn("do you want", response.turn.assistant_reply.lower())
        self.assertNotIn("yes or no", response.turn.assistant_reply.lower())

    def test_first_greeting_is_deterministic_even_when_llm_is_available(self) -> None:
        chain = FakeChain(
            TripRequirements(flight_origin="CMB")
        )
        service = TravelIntakeService(chain=chain)
        response = service.process_turn("hey")

        self.assertEqual(chain.payloads, [])
        self.assertEqual(response.turn.assistant_reply, "Hey, happy to help with this trip. Which city are you flying from?")
        self.assertIn("flight_origin", response.turn.missing_fields)

    def test_nope_does_not_skip_flight_collection_anymore(self) -> None:
        service = TravelIntakeService(chain=None, use_llm=False)
        response = service.process_turn("nope")

        self.assertTrue(response.session.trip_requirements.needs_flights)
        self.assertIn("flight_origin", response.turn.missing_fields)
        self.assertIn("flight_departure_date", response.turn.missing_fields)
        self.assertIn("flight_passengers", response.turn.missing_fields)
        self.assertIn("flight_cabin_class", response.turn.missing_fields)
        self.assertEqual(response.turn.assistant_reply, "Which city are you flying from?")

    def test_flight_details_are_collected_before_route(self) -> None:
        service = TravelIntakeService(chain=None, use_llm=False)
        first = service.process_turn("hey")
        second = service.process_turn("from Dubai, 2026 July 20, 2 passengers, economy", first.session)

        self.assertEqual(second.session.trip_requirements.flight_origin, "DXB")
        self.assertEqual(second.session.trip_requirements.flight_origin_input, "Dubai")
        self.assertEqual(second.session.trip_requirements.flight_departure_date, "2026-07-20")
        self.assertEqual(second.session.trip_requirements.flight_passengers, 2)
        self.assertEqual(second.session.trip_requirements.flight_cabin_class, "economy")
        self.assertNotIn("flight_origin", second.turn.missing_fields)
        self.assertNotIn("flight_departure_date", second.turn.missing_fields)
        self.assertNotIn("flight_passengers", second.turn.missing_fields)
        self.assertNotIn("flight_cabin_class", second.turn.missing_fields)
        self.assertIn("total_budget_lkr", second.turn.missing_fields)
        self.assertIn("origin", second.turn.missing_fields)
        self.assertIn("destination", second.turn.missing_fields)
        self.assertIn("duration", second.turn.missing_fields)
        self.assertEqual(second.turn.assistant_reply, "What total budget should I plan around, in LKR?")

    def test_full_natural_message_completes_all_required_fields(self) -> None:
        service = TravelIntakeService(chain=None, use_llm=False)
        response = service.process_turn(
            "I am flying from Dubai on 2026 July 20, 2 passengers, economy. "
            "Trip from Kandy to Galle for 4 days. Budget 400000 LKR."
        )

        self.assertTrue(response.turn.is_complete)
        self.assertTrue(response.session.trip_requirements.needs_flights)
        self.assertEqual(response.session.trip_requirements.flight_origin, "DXB")
        self.assertEqual(response.session.trip_requirements.flight_departure_date, "2026-07-20")
        self.assertEqual(response.session.trip_requirements.flight_passengers, 2)
        self.assertEqual(response.session.trip_requirements.flight_cabin_class, "economy")
        self.assertEqual(response.session.trip_requirements.origin, "Kandy")
        self.assertEqual(response.session.trip_requirements.destination, "Galle")
        self.assertEqual(response.session.trip_requirements.duration, "4 days")
        self.assertEqual(response.session.trip_requirements.total_budget_lkr, 400000.0)
        self.assertIn("from Kandy to Galle", response.turn.assistant_reply)
        self.assertIn("flights from Dubai", response.turn.assistant_reply)

    def test_phase_llm_outputs_are_accepted_without_regex_support(self) -> None:
        flight_chain = FakeChain(
            FlightIntakeOutput(
                flight_origin_input="Tokyo",
                flight_origin="HND",
                flight_departure_date="2026-08-15",
                flight_passengers=3,
                flight_cabin_class="business",
                total_budget_lkr=900000,
            )
        )
        trip_chain = FakeChain(
            TripIntakeOutput(
                origin="Negombo",
                destination="Ella",
                duration="5 days",
            )
        )
        service = TravelIntakeService(flight_chain=flight_chain, trip_chain=trip_chain)

        first = service.process_turn("please arrange that plan")
        response = service.process_turn("continue with the route", first.session)

        self.assertTrue(response.turn.is_complete)
        self.assertEqual(response.turn.active_phase, "complete")
        self.assertEqual(response.session.trip_requirements.flight_origin_input, "Tokyo")
        self.assertEqual(response.session.trip_requirements.flight_origin, "HND")
        self.assertEqual(response.session.trip_requirements.flight_departure_date, "2026-08-15")
        self.assertEqual(response.session.trip_requirements.flight_passengers, 3)
        self.assertEqual(response.session.trip_requirements.flight_cabin_class, "business")
        self.assertEqual(response.session.trip_requirements.total_budget_lkr, 900000.0)
        self.assertEqual(response.session.trip_requirements.origin, "Negombo")
        self.assertEqual(response.session.trip_requirements.destination, "Ella")
        self.assertEqual(response.session.trip_requirements.duration, "5 days")

    def test_trip_bot_does_not_run_before_flight_phase_is_complete(self) -> None:
        flight_chain = FakeChain(FlightIntakeOutput())
        trip_chain = FakeChain(
            TripIntakeOutput(
                origin="Negombo",
                destination="Ella",
                duration="5 days",
            )
        )
        service = TravelIntakeService(flight_chain=flight_chain, trip_chain=trip_chain)

        response = service.process_turn("from colombo to badulla for 4 days")

        self.assertEqual(len(flight_chain.payloads), 1)
        self.assertEqual(flight_chain.payloads[0]["active_phase"], "flight")
        self.assertEqual(trip_chain.payloads, [])
        self.assertEqual(response.session.trip_requirements.origin, "colombo")
        self.assertEqual(response.session.trip_requirements.destination, "badulla")
        self.assertEqual(response.session.trip_requirements.duration, "4 days")
        self.assertEqual(response.turn.active_phase, "flight")
        self.assertEqual(response.turn.assistant_reply, "Which city are you flying from?")

    def test_strict_multi_turn_flow_keeps_asking_until_every_variable_exists(self) -> None:
        service = TravelIntakeService(chain=None, use_llm=False)

        first = service.process_turn("hey")
        self.assertFalse(first.turn.is_complete)
        self.assertEqual(first.turn.active_phase, "flight")
        self.assertIn("flight_origin", first.turn.missing_fields)

        second = service.process_turn("from dubai, 2026 july 20, 2 passengers, economy", first.session)
        self.assertFalse(second.turn.is_complete)
        self.assertEqual(second.turn.active_phase, "flight")
        self.assertEqual(second.turn.missing_fields, ["total_budget_lkr", "origin", "destination", "duration"])
        self.assertEqual(second.turn.assistant_reply, "What total budget should I plan around, in LKR?")

        third = service.process_turn("from colombo to badulla", second.session)
        self.assertFalse(third.turn.is_complete)
        self.assertEqual(third.turn.active_phase, "flight")
        self.assertEqual(third.session.trip_requirements.origin, "colombo")
        self.assertEqual(third.session.trip_requirements.destination, "badulla")
        self.assertEqual(third.turn.missing_fields, ["total_budget_lkr", "duration"])
        self.assertEqual(third.turn.assistant_reply, "What total budget should I plan around, in LKR?")

        fourth = service.process_turn("400000 lkr", third.session)
        self.assertFalse(fourth.turn.is_complete)
        self.assertEqual(fourth.turn.active_phase, "trip")
        self.assertEqual(fourth.session.trip_requirements.total_budget_lkr, 400000.0)
        self.assertEqual(fourth.turn.missing_fields, ["duration"])
        self.assertEqual(fourth.turn.assistant_reply, "How many days should the trip be?")

        fifth = service.process_turn("4 days", fourth.session)
        self.assertTrue(fifth.turn.is_complete)
        self.assertEqual(fifth.turn.active_phase, "complete")
        self.assertEqual(fifth.session.trip_requirements.duration, "4 days")

    def test_user_transcript_collects_budget_before_route_and_parses_casual_route(self) -> None:
        service = TravelIntakeService(chain=None, use_llm=False)

        first = service.process_turn("yes")
        self.assertIn("which city are you flying from", first.turn.assistant_reply.lower())
        self.assertNotIn("departure date", first.turn.assistant_reply.lower())

        second = service.process_turn("dubai", first.session)
        self.assertEqual(second.session.trip_requirements.flight_origin, "DXB")
        self.assertEqual(second.turn.assistant_reply, "What departure date should I check for the flight?")

        third = service.process_turn("2026 june 20, 1 passanger, economy", second.session)
        self.assertEqual(third.session.trip_requirements.flight_departure_date, "2026-06-20")
        self.assertEqual(third.session.trip_requirements.flight_passengers, 1)
        self.assertEqual(third.session.trip_requirements.flight_cabin_class, "economy")
        self.assertEqual(third.turn.assistant_reply, "What total budget should I plan around, in LKR?")

        fourth = service.process_turn("400000 lkr", third.session)
        self.assertEqual(fourth.session.trip_requirements.total_budget_lkr, 400000.0)
        self.assertEqual(fourth.turn.assistant_reply, "Where should the trip start in Sri Lanka?")

        fifth = service.process_turn("colombo to badulla 3 days", fourth.session)
        self.assertEqual(fifth.session.trip_requirements.origin, "colombo")
        self.assertEqual(fifth.session.trip_requirements.destination, "badulla")
        self.assertEqual(fifth.session.trip_requirements.duration, "3 days")
        self.assertTrue(fifth.turn.is_complete)

    def test_compact_route_with_for_duration_does_not_pollute_destination(self) -> None:
        service = TravelIntakeService(chain=None, use_llm=False)
        session = ChatSessionState(
            trip_requirements=TripRequirements(
                needs_flights=True,
                flight_origin="DXB",
                flight_origin_input="Dubai",
                flight_departure_date="2026-07-20",
                flight_passengers=2,
                flight_cabin_class="economy",
                total_budget_lkr=400000,
            )
        )

        response = service.process_turn("from colombo to badulla for 4 days", session)

        self.assertEqual(response.session.trip_requirements.origin, "colombo")
        self.assertEqual(response.session.trip_requirements.destination, "badulla")
        self.assertEqual(response.session.trip_requirements.duration, "4 days")
        self.assertTrue(response.turn.is_complete)

    def test_plain_numeric_budget_is_accepted_when_budget_is_next_required_field(self) -> None:
        service = TravelIntakeService(chain=None, use_llm=False)
        session = ChatSessionState(
            trip_requirements=TripRequirements(
                needs_flights=True,
                flight_origin="DXB",
                flight_origin_input="Dubai",
                flight_departure_date="2026-07-20",
                flight_passengers=2,
                flight_cabin_class="economy",
            )
        )

        response = service.process_turn("500000", session)

        self.assertEqual(response.session.trip_requirements.total_budget_lkr, 500000.0)
        self.assertEqual(response.turn.assistant_reply, "Where should the trip start in Sri Lanka?")
        self.assertEqual(response.turn.missing_fields, ["origin", "destination", "duration"])

    def test_llm_cannot_skip_budget_to_ask_route_after_flights(self) -> None:
        chain = FakeChain(TripRequirements())
        service = TravelIntakeService(chain=chain)
        session = ChatSessionState(
            trip_requirements=TripRequirements(
                needs_flights=True,
                flight_origin="DXB",
                flight_origin_input="dubai",
                flight_departure_date="2026-06-20",
                flight_passengers=1,
                flight_cabin_class="economy",
            )
        )

        response = service.process_turn("ok", session)

        self.assertIn("total_budget_lkr", response.turn.missing_fields)
        self.assertEqual(response.turn.assistant_reply, "What total budget should I plan around, in LKR?")

    def test_contextual_short_replies_use_current_missing_flight_field(self) -> None:
        service = TravelIntakeService(chain=None, use_llm=False)
        session = ChatSessionState(
            trip_requirements=TripRequirements(
                needs_flights=True,
                flight_origin="DXB",
                flight_origin_input="Dubai",
                flight_departure_date="2026-07-20",
                flight_cabin_class="economy",
            )
        )

        response = service.process_turn("two", session)
        self.assertEqual(response.session.trip_requirements.flight_passengers, 2)
        self.assertNotIn("flight_passengers", response.turn.missing_fields)

    def test_cabin_class_reply_does_not_pollute_destination(self) -> None:
        service = TravelIntakeService(chain=None, use_llm=False)
        session = ChatSessionState(
            trip_requirements=TripRequirements(
                needs_flights=True,
                flight_origin="DXB",
                flight_origin_input="Dubai",
                flight_departure_date="2026-07-20",
                flight_passengers=2,
            )
        )

        response = service.process_turn("economy", session)

        self.assertEqual(response.session.trip_requirements.flight_cabin_class, "economy")
        self.assertIsNone(response.session.trip_requirements.destination)
        self.assertEqual(response.turn.assistant_reply, "What total budget should I plan around, in LKR?")

    def test_traveller_phrase_is_accepted_for_passenger_count(self) -> None:
        service = TravelIntakeService(chain=None, use_llm=False)
        session = ChatSessionState(
            trip_requirements=TripRequirements(
                needs_flights=True,
                flight_origin="DXB",
                flight_origin_input="Dubai",
                flight_departure_date="2026-07-20",
            )
        )

        response = service.process_turn("1 traveller", session)

        self.assertEqual(response.session.trip_requirements.flight_passengers, 1)
        self.assertEqual(response.turn.assistant_reply, "Which cabin class do you want, like economy or business?")

    def test_natural_cabin_reply_is_accepted(self) -> None:
        service = TravelIntakeService(chain=None, use_llm=False)
        session = ChatSessionState(
            trip_requirements=TripRequirements(
                needs_flights=True,
                flight_origin="DXB",
                flight_origin_input="Dubai",
                flight_departure_date="2026-07-20",
                flight_passengers=1,
            )
        )

        response = service.process_turn("economy is fine", session)

        self.assertEqual(response.session.trip_requirements.flight_cabin_class, "economy")
        self.assertEqual(response.turn.assistant_reply, "What total budget should I plan around, in LKR?")

    def test_origin_answer_after_budget_moves_to_destination(self) -> None:
        service = TravelIntakeService(chain=None, use_llm=False)
        session = ChatSessionState(
            trip_requirements=TripRequirements(
                needs_flights=True,
                flight_origin="DXB",
                flight_origin_input="Dubai",
                flight_departure_date="2026-07-20",
                flight_passengers=2,
                flight_cabin_class="economy",
                total_budget_lkr=500000.0,
            )
        )

        response = service.process_turn("colombo", session)

        self.assertEqual(response.session.trip_requirements.origin, "colombo")
        self.assertIsNone(response.session.trip_requirements.destination)
        self.assertEqual(response.turn.assistant_reply, "Where in Sri Lanka do you want to go?")
        self.assertEqual(response.turn.missing_fields, ["destination", "duration"])

    def test_bare_number_answer_is_accepted_when_duration_is_next(self) -> None:
        service = TravelIntakeService(chain=None, use_llm=False)
        session = ChatSessionState(
            trip_requirements=TripRequirements(
                needs_flights=True,
                flight_origin="DXB",
                flight_origin_input="Dubai",
                flight_departure_date="2026-07-20",
                flight_passengers=1,
                flight_cabin_class="economy",
                total_budget_lkr=500000.0,
                origin="colombo",
                destination="badulla",
            )
        )

        response = service.process_turn("4", session)

        self.assertTrue(response.turn.is_complete)
        self.assertEqual(response.session.trip_requirements.duration, "4 days")
        self.assertEqual(response.turn.missing_fields, [])

    def test_chat_history_is_sent_to_gemini_chain(self) -> None:
        chain = FakeChain(_empty_llm_result())
        service = TravelIntakeService(chain=chain)

        session = ChatSessionState(
            trip_requirements=TripRequirements(
                needs_flights=True,
                flight_origin="DXB",
                flight_origin_input="Dubai",
                flight_departure_date="2026-07-20",
                flight_passengers=2,
                flight_cabin_class="economy",
                total_budget_lkr=400000,
            ),
            history=[
                ConversationTurn(role="user", content="I want a quiet hill country trip."),
                ConversationTurn(role="assistant", content="Where should the trip start in Sri Lanka?"),
            ],
        )
        service.process_turn("the same place we discussed", session)

        self.assertGreaterEqual(len(chain.payloads), 1)
        second_payload = chain.payloads[-1]
        self.assertIn("User: I want a quiet hill country trip.", second_payload["history"])
        self.assertIn("Assistant:", second_payload["history"])
        self.assertIn("current_state", second_payload)
        self.assertIn("current_missing_fields", second_payload)

    def test_extraction_chain_receives_updated_missing_fields_after_budget(self) -> None:
        chain = FakeChain(_empty_llm_result())
        service = TravelIntakeService(chain=chain)

        first = service.process_turn("from Dubai, 2026 July 20, 2 passengers, economy")
        second = service.process_turn("400000 lkr", first.session)
        service.process_turn("the place we talked about", second.session)

        self.assertGreaterEqual(len(chain.payloads), 1)
        trip_payloads_after_budget = [
            payload
            for payload in chain.payloads
            if payload["active_phase"] == "trip"
            and payload["current_missing_fields"] == "origin, destination, duration"
        ]
        self.assertTrue(trip_payloads_after_budget)
        self.assertEqual(trip_payloads_after_budget[-1]["active_phase_missing_fields"], "origin, destination, duration")

    def test_llm_cannot_mark_complete_without_backend_required_fields(self) -> None:
        chain = FakeChain(
            TripRequirements(
                needs_flights=True,
                origin="Colombo",
                destination="Badulla",
                duration="4 days",
                total_budget_lkr=400000,
            )
        )
        service = TravelIntakeService(chain=chain)
        response = service.process_turn("from colombo to badulla for 4 days with 400000 lkr")

        self.assertFalse(response.turn.is_complete)
        self.assertIn("flight_origin", response.turn.missing_fields)
        self.assertIn("flight_departure_date", response.turn.missing_fields)
        self.assertIn("flight_passengers", response.turn.missing_fields)
        self.assertIn("flight_cabin_class", response.turn.missing_fields)
        self.assertEqual(response.turn.assistant_reply, "Which city are you flying from?")

    def test_full_brief_with_flights_from_phrase_no_longer_pollutes_trip_origin(self) -> None:
        service = TravelIntakeService(chain=None, use_llm=False)

        response = service.process_turn(
            "I need flights from Dubai on 2026-07-20 for 1 passenger in economy. "
            "My total budget is 500000 LKR. I want to travel from Colombo to Badulla for 4 days."
        )

        self.assertTrue(response.turn.is_complete)
        self.assertEqual(response.session.trip_requirements.flight_origin, "DXB")
        self.assertEqual(response.session.trip_requirements.origin, "Colombo")
        self.assertEqual(response.session.trip_requirements.destination, "Badulla")
        self.assertEqual(response.session.trip_requirements.duration, "4 days")

    def test_full_brief_plain_route_without_from_completes(self) -> None:
        service = TravelIntakeService(chain=None, use_llm=False)

        response = service.process_turn(
            "i need flights from dubai on 2026 july 20 for 1 traveller economy. "
            "budget 500000 lkr. colombo to badulla for 4 days."
        )

        self.assertTrue(response.turn.is_complete)
        self.assertEqual(response.turn.active_phase, "complete")
        self.assertEqual(response.session.active_phase, "complete")
        self.assertEqual(response.session.trip_requirements.flight_origin, "DXB")
        self.assertEqual(response.session.trip_requirements.flight_departure_date, "2026-07-20")
        self.assertEqual(response.session.trip_requirements.flight_passengers, 1)
        self.assertEqual(response.session.trip_requirements.flight_cabin_class, "economy")
        self.assertEqual(response.session.trip_requirements.total_budget_lkr, 500000.0)
        self.assertEqual(response.session.trip_requirements.origin, "colombo")
        self.assertEqual(response.session.trip_requirements.destination, "badulla")
        self.assertEqual(response.session.trip_requirements.duration, "4 days")
        self.assertIn("from Colombo to Badulla", response.turn.assistant_reply)

    def test_full_brief_plain_android_text_input_completes(self) -> None:
        service = TravelIntakeService(chain=None, use_llm=False)

        response = service.process_turn(
            "I need flights from Dubai on 2026 July 20 for 1 traveller economy "
            "budget 500000 lkr from Colombo to Badulla for 4 days"
        )

        self.assertTrue(response.turn.is_complete)
        self.assertEqual(response.session.trip_requirements.flight_origin, "DXB")
        self.assertEqual(response.session.trip_requirements.flight_departure_date, "2026-07-20")
        self.assertEqual(response.session.trip_requirements.flight_passengers, 1)
        self.assertEqual(response.session.trip_requirements.flight_cabin_class, "economy")
        self.assertEqual(response.session.trip_requirements.total_budget_lkr, 500000.0)
        self.assertEqual(response.session.trip_requirements.origin, "Colombo")
        self.assertEqual(response.session.trip_requirements.destination, "Badulla")
        self.assertEqual(response.session.trip_requirements.duration, "4 days")


if __name__ == "__main__":
    unittest.main()
