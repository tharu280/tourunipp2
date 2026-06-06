from __future__ import annotations

from datetime import date
from typing import Any

from langgraph.graph import END, StateGraph

from trip_graph.nodes import (
    assemble_plan_node,
    crowd_node,
    itinerary_node,
    resolve_trip_node,
    roadlk_node,
    route_generation_node,
    traffic_node,
    travel_windows_node,
    weather_node,
)
from trip_graph.state import TripGraphState


workflow = StateGraph(TripGraphState)
workflow.add_node("resolve_trip", resolve_trip_node)
workflow.add_node("route_generation", route_generation_node)
workflow.add_node("roadlk_enrichment", roadlk_node)
workflow.add_node("weather_enrichment", weather_node)
workflow.add_node("crowd_enrichment", crowd_node)
workflow.add_node("traffic_enrichment", traffic_node)
workflow.add_node("travel_windows_enrichment", travel_windows_node)
workflow.add_node("itinerary_generation", itinerary_node)
workflow.add_node("assemble_plan", assemble_plan_node)

workflow.set_entry_point("resolve_trip")
workflow.add_edge("resolve_trip", "route_generation")
workflow.add_edge("route_generation", "roadlk_enrichment")
workflow.add_edge("roadlk_enrichment", "weather_enrichment")
workflow.add_edge("weather_enrichment", "crowd_enrichment")
workflow.add_edge("crowd_enrichment", "traffic_enrichment")
workflow.add_edge("traffic_enrichment", "travel_windows_enrichment")
workflow.add_edge("travel_windows_enrichment", "itinerary_generation")
workflow.add_edge("itinerary_generation", "assemble_plan")
workflow.add_edge("assemble_plan", END)

trip_planner_graph = workflow.compile()


async def invoke_trip_graph(
    *,
    origin_text: str,
    destination_text: str,
    duration_text: str,
    start_date: date,
    departure_time: str = "08:00",
    options: Any = None,
):
    graph_state = await trip_planner_graph.ainvoke(
        {
            "origin_text": origin_text,
            "destination_text": destination_text,
            "duration_text": duration_text,
            "start_date": start_date.isoformat(),
            "departure_time": departure_time,
            "options": {
                "include_gemini": (options.include_gemini if options else True),
                "include_roadlk": (options.include_roadlk if options else True),
                "include_weather": (options.include_weather if options else True),
                "include_crowd": (options.include_crowd if options else True),
                "place_strategy": (options.place_strategy if options else "nearby"),
            },
        }
    )
    return graph_state["final_plan"]
