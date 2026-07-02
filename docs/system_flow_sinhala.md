# Tour Intelligence System Flow - Sinhala Explanation

Project එකේ main folder එක:

```text
/Users/dilshantharushika/Desktop/routemvp/tourunipp2
```

## 1. System එකේ high-level idea එක

මෙම system එක route-first tourism planning system එකක්. පරණ approach එක වගේ LLM එකෙන් attractions හෝ route stops invent කරවන්නේ නැහැ. පළමුව user ගේ trip requirement තුන ගන්නවා. ඉන්පසු Google Routes API එකෙන් real road route alternatives ගන්නවා. ඒ route alternatives මත curated attraction dataset එක, accommodation dataset එක, RoadLK incidents, weather forecast, traffic signal, crowd pressure signal, travel window heatmap, සහ NSGA-II style route ranking එක apply කරනවා.

High-level flow එක මෙහෙමයි:

```text
User chat input
-> Gemini intake chatbot
-> origin / destination / duration extraction
-> Streamlit planner controls
-> planner_pipeline.py
-> LangGraph flow
-> place resolution
-> Google route alternatives
-> day segmentation
-> attractions + accommodation enrichment
-> RoadLK enrichment
-> weather enrichment
-> crowd pressure enrichment
-> selected-route live traffic enrichment
-> travel window pressure heatmap
-> itinerary generation
-> final plan object
-> Streamlit dashboard + saved JSON/text outputs
```

## 2. Frontend entry point: Streamlit UI

Frontend එක තියෙන්නේ:

```text
streamlit_app.py
```

මෙය Streamlit based dashboard එකයි. User මුලින්ම app එක open කරනකොට ඔහුට Trip Intake Chat section එකක් පේනවා. ඒ chat section එකෙන් user natural language වලින් trip එක කියනවා.

උදාහරණ:

```text
I want to go from Kandy to Badulla for 4 days
```

Streamlit UI එකේ main responsibilities:

- User chat message collect කිරීම
- Gemini chatbot එක call කිරීම
- Extract කරගත් origin, destination, duration display කිරීම
- Trip start date සහ departure time ලබාගැනීම
- Weather, crowd, Gemini refinement, RoadLK toggles ලබාගැනීම
- Planner build button එකෙන් backend pipeline එක run කිරීම
- Final plan එක dashboard එකේ render කිරීම
- Route map, journey-by-day, pressure/weather, itinerary, advisor chat display කිරීම
- Plan එක JSON සහ text file විදිහට save කිරීම

Streamlit app එක backend plan එක build කරන්නේ:

```text
planner_pipeline.py
```

අදාල function එක:

```python
build_trip_plan(...)
```

## 3. Gemini intake chatbot

Trip input ගන්න chatbot එක තියෙන්නේ:

```text
chat/bot.py
chat/schemas.py
```

මෙතන `TravelIntakeChatbot` class එක තියෙනවා. මේ chatbot එක Gemini model එක භාවිතා කරලා user message එකෙන් trip requirement තුන extract කරනවා.

Input fields තුන:

- Origin: ගමන පටන් ගන්න තැන
- Destination: ගමන අවසන් කරන තැන
- Duration: ගමනේ දින ගණන

උදාහරණයක්:

```text
User: i wanna go from galle to kandy in 3 days
```

Chatbot output structure එක:

```text
origin = Galle
destination = Kandy
duration = 3 days
```

මෙම structured data එක `ChatSessionState` තුළ save වෙනවා. UI එකේ Build Dashboard button එක enable වෙන්නේ මේ fields තුනම complete වුණාමයි.

### Gemini + deterministic fallback

`chat/bot.py` තුළ Gemini structured output එකට අමතරව heuristic parser එකක් තියෙනවා:

```python
_heuristic_trip_requirements(...)
```

මේකෙන් common phrases වගේ:

```text
from Galle to Kandy in 3 days
go to Kandy from Galle for 3 days
```

වගේ inputs deterministic විදිහට parse කරනවා. මෙය chatbot එක replace කිරීමක් නෙවෙයි. Gemini reply එක natural conversation එක සඳහා භාවිතා කරන අතර, important fields miss නොවෙන්න safety layer එකක් විදිහට deterministic parser එක තියෙනවා.

මෙය අවශ්‍ය හේතුව:

- Gemini response text එක හරි වුණත් structured field එකක් miss වෙන්න පුළුවන්
- UI button enable/disable logic එක structured state මත depend වෙනවා
- ඒ නිසා production-style system එකකට LLM + deterministic safety net approach එක වඩා reliable

## 4. Planner pipeline bridge

Streamlit UI එකෙන් backend flow එක call කරන bridge file එක:

```text
planner_pipeline.py
```

මෙහි `TripPlanOptions` dataclass එකෙන් planner toggles represent කරනවා:

```python
include_gemini
include_roadlk
include_weather
include_crowd
place_strategy
```

ප්‍රධාන function එක:

```python
build_trip_plan(...)
```

මෙය internally LangGraph flow එක call කරනවා:

```python
invoke_trip_graph(...)
```

LangGraph async flow එක Streamlit වගේ sync environment එකක run කරන්න `_run_async(...)` helper එක තියෙනවා.

## 5. LangGraph flow

LangGraph orchestration එක තියෙන්නේ:

```text
trip_graph/graph.py
trip_graph/nodes.py
trip_graph/state.py
```

Graph එක define කරන file එක:

```text
trip_graph/graph.py
```

Graph nodes order එක:

```text
resolve_trip
-> route_generation
-> roadlk_enrichment
-> weather_enrichment
-> crowd_enrichment
-> traffic_enrichment
-> travel_windows_enrichment
-> itinerary_generation
-> assemble_plan
-> END
```

මෙහි advantage එක:

- pipeline එක clear node-by-node structure එකකට break වෙනවා
- එක් එක් enrichment layer එක independent node එකක්
- RoadLK/weather/crowd/traffic වගේ future modules add කරන්න ලේසියි
- route profile එක gradually enrich වෙනවා
- frontend එකට final structured plan object එකක් ලැබෙනවා

## 6. Node 1: resolve_trip

Node එක:

```text
trip_graph/nodes.py -> resolve_trip_node
```

මෙහි වැඩ:

1. Duration text එක trip days count එකකට convert කරනවා.
2. Trip dates list එක හදනවා.
3. Origin text එක coordinates වලට resolve කරනවා.
4. Destination text එක coordinates වලට resolve කරනවා.

Duration parsing function:

```python
parse_trip_days(...)
```

Examples:

```text
"4 days" -> 4
"1 week" -> 7
"3" -> 3
```

Place resolution එක කරන්නේ:

```text
google_places/client.py -> resolve_place_query
```

මෙහි පළමුව Google Geocoding API භාවිතා වෙනවා. එය fail වුණොත් Google Places Text Search fallback එකක් තියෙනවා.

Sri Lanka constraint එක:

```text
components=country:LK
```

ඒ නිසා Kandy, Badulla, Galle වගේ place names Sri Lanka context එකෙන් resolve වෙනවා.

Output:

```text
trip_days
trip_dates
origin_resolved
destination_resolved
```

## 7. Node 2: route_generation

Node එක:

```text
trip_graph/nodes.py -> route_generation_node
```

මෙම node එකේ main responsibilities:

1. Google Routes API call කිරීම
2. Multiple route alternatives ලබාගැනීම
3. Route profiles build කිරීම
4. Attractions සහ accommodation enrich කිරීම
5. Initial NSGA-II ranking කිරීම
6. Optional Gemini refinement selected route එකට apply කිරීම

Google route call එක:

```text
traffic/google_routes/client.py
```

Google routes call එක multiple alternatives request කරනවා:

```python
compute_alternative_routes=True
```

මෙයින් route alternatives ලැබෙනවා. උදාහරණයක් ලෙස:

```text
route_1
route_2
route_3
```

Route profile එකට include වෙන fields:

- route id
- distance
- duration
- encoded polyline
- decoded geometry summary
- day segments
- attractions
- lodging

## 8. Day segmentation

Day segmentation logic එක තියෙන්නේ:

```text
traffic/google_routes/segments.py
```

Function:

```python
build_day_segments(...)
```

දැනට route එක trip days ගණනට equal-distance split කරනවා.

උදාහරණ:

```text
Total route distance = 330 km
Trip days = 3
Day 1 = 110 km
Day 2 = 110 km
Day 3 = 110 km
```

ඒ නිසා UI එකේ හැම day card එකකම same distance පේන්න පුළුවන්. මෙය current limitation එකක්. Tourism itinerary logic එකක් සඳහා future improvement එකක් වන්නේ attraction clusters, overnight bases, සහ actual travel pacing අනුව uneven day segmentation කිරීමයි.

දැනට each segment එකේ:

- start point
- mid point
- end point
- segment path points
- segment distance
- segment duration
- overnight stop status

save වෙනවා.

## 9. Attractions dataset enrichment

Attraction enrichment logic එක තියෙන්නේ:

```text
google_places/enrich_routes.py
```

Dataset එක:

```text
data/sri_lanka_attractions.json
```

මෙහි curated Sri Lanka attractions තියෙනවා. මෙය raw Google POI dump එකක් නෙවෙයි. District, province, categories, coordinates, tier, importance score, summary, source URLs වගේ fields තියෙන curated dataset එකක්.

Attraction selection flow:

```text
Full route geometry
-> route-near districts identify කිරීම
-> those districts වල attractions route pool එකට ගන්නවා
-> full route distance cutoff apply කරනවා
-> attraction එක closest day segment එකට assign කරනවා
-> each day segment එකට local route corridor filtering apply කරනවා
-> importance/tier/distance අනුව light ranking
-> Gemini refinement optional
```

Important functions:

```python
build_route_attraction_pool(...)
assign_attractions_to_segments(...)
fetch_curated_attractions_for_segment(...)
rank_places_for_segment(...)
```

මෙහි advantage එක:

- National leakage අඩු වෙනවා
- Kandy to Badulla route එකට Galle Fort වගේ irrelevant attraction randomly නොඑනවා
- Dataset එක district-aware සහ route-aware දෙකම වෙනවා
- Gemini ට send වෙන්නේ already geographically relevant candidates

## 10. Accommodation dataset enrichment

Accommodation dataset එක:

```text
data/sri_lanka_accommodations.json
```

Accommodation enrichment logic එකත් තියෙන්නේ:

```text
google_places/enrich_routes.py
```

Accommodation flow:

```text
Day segment end point
-> overnight stop ද කියලා බලනවා
-> curated accommodation dataset එකෙන් nearby stays ගන්නවා
-> Google Places lodging fallback එක try කරනවා
-> distance/rating/price/rating_band වගේ signals අනුව rank කරනවා
```

Important functions:

```python
load_curated_accommodations(...)
normalize_curated_accommodation(...)
fetch_curated_lodging_for_segment(...)
```

Accommodation only needed වෙන්නේ overnight stop days වලටයි. Final day එක journey end එක නම් overnight stay අවශ්‍ය නැති නිසා no overnight base ලෙස show වෙන්න පුළුවන්.

## 11. Gemini route/day refinement

Gemini refinement module එක:

```text
gemini_refine/refine_routes.py
gemini_refine/client.py
```

මෙය attraction discovery engine එකක් නෙවෙයි. Attraction discovery කරන්නේ curated dataset + route filtering. Gemini refinement එකෙන් කරන්නේ:

- already selected route/day candidates බලනවා
- day එකට best attractions choose/refine කරනවා
- repetitive choices අඩු කරන්න උදව් වෙනවා
- final recommendation quality improve කරනවා

Performance හේතුවෙන් Gemini refinement currently selected/recommended route එකට පමණක් apply වෙනවා. සියලු route alternatives වලට Gemini call කිරීම slow නිසා එය avoid කරලා තියෙනවා.

## 12. NSGA-II style route ranking

NSGA-II ranking logic එක තියෙන්නේ:

```text
trip_graph/nsgaii/select_routes.py
```

මෙය full genetic search population එකක් generate කරන system එකක් නොවෙයි. Google Routes API එකෙන් ලැබෙන route alternatives කිහිපය multi-objective optimization style එකෙන් compare කරන layer එකක්.

Objectives:

```text
Minimize:
- distance_meters
- duration_seconds
- road_risk_score
- weather_risk_score
- crowd_pressure_score

Maximize:
- attraction_value_score
- lodging_value_score
```

Core functions:

```python
build_candidate(...)
infer_active_objectives(...)
nondominated_sort(...)
assign_crowding_distance(...)
assign_compromise_scores(...)
build_summary(...)
```

Route ranking output:

- Pareto rank
- crowding distance
- compromise score
- recommended route id
- active objectives

LangGraph flow එකේ enrichment node එකක් පසු route data වෙනස් වුණාම `_payload_with_selection(...)` function එකෙන් නැවත route ranking update කරනවා.

## 13. RoadLK enrichment

RoadLK route incident logic:

```text
roadlk/client.py
roadlk/enrich_routes.py
```

LangGraph node:

```text
roadlk_node
```

මෙහි වැඩ:

```text
Each route alternative
-> route geometry bbox එක build කිරීම
-> RoadLK incident data fetch කිරීම
-> bbox filter
-> route corridor distance filter
-> duplicates remove කිරීම
-> risk score / risk level generate කිරීම
```

RoadLK output fields:

- risk_level
- critical_count
- incidents
- critical_incidents
- by_status
- by_damage_type
- distance_to_route_meters

මෙය NSGA-II route comparison එකට road risk objective එකක් ලෙස යනවා. UI එකේ road warnings සහ pressure model එකටත් යනවා.

## 14. Weather enrichment

Weather logic:

```text
weather/client.py
weather/enrich_routes.py
```

LangGraph node:

```text
weather_node
```

Weather data source එක Open-Meteo style API එකක්. API key එකක් අවශ්‍ය නොවන setup එකක් ලෙස use කරනවා.

Weather flow:

```text
Each route
-> each day segment midpoint
-> forecast fetch
-> daily weather summary
-> weather risk score
-> route-level weather summary
```

Weather risk factors:

- rain probability
- rainfall
- wind speed
- max temperature

Output:

- per-segment forecast
- per-segment weather risk
- route weather summary
- average_weather_risk_score
- max_weather_risk_score
- risk_level

## 15. Crowd / travel pressure enrichment

Crowd pressure logic:

```text
crowd/client.py
crowd/enrich_routes.py
```

LangGraph node:

```text
crowd_node
```

මෙය true live tourist density sensor එකක් නොවෙයි. මෙය crowd/travel pressure estimation module එකක්. It estimates likely pressure using available proxy signals.

Current signals:

- Sri Lanka public holidays
- weekend demand
- weather pressure
- RoadLK road friction
- attraction/corridor sensitivity
- live traffic pressure, after traffic enrichment

Crowd module output:

- risk_level
- signal_score
- helper_summary
- recommendations
- component breakdown
- zone_pressure
- attraction_pressure
- forecast_windows
- redistribution_suggestions

Zone pressure includes:

- day-level pressure
- district-level pressure
- corridor-level pressure

Attraction pressure gives each attraction:

- pressure score
- pressure level
- preferred visit window

Redistribution suggestions:

- high pressure day එකකට earlier visit suggestion
- crowded attraction එකකට alternative attraction
- overnight pattern guidance
- route flexibility advice

## 16. Selected-route live traffic enrichment

Traffic logic:

```text
traffic/client.py
```

LangGraph node:

```text
traffic_node
```

මෙම node එක සියලු routes වලට traffic call කරන්නේ නැහැ. Google demo/free API limit avoid කරන්න selected/recommended route එකට පමණක් traffic enrichment කරනවා.

Flow:

```text
Recommended route
-> Google Routes traffic-aware request
-> duration + staticDuration compare
-> speedReadingIntervals summarize
-> congestion score calculate
-> traffic risk level create
-> crowd pressure recompute with traffic
```

Traffic output:

- live_duration_seconds
- static_duration_seconds
- delay_minutes
- normal_ratio
- slow_ratio
- jam_ratio
- congestion_score
- risk_level
- summary

Traffic data pressure model එකට fourth component එකක් ලෙස යනවා:

```text
holiday demand + weather stress + RoadLK road friction + live traffic
```

## 17. Travel windows / pressure heatmap

Travel window heatmap logic:

```text
travel_windows/client.py
```

LangGraph node:

```text
travel_windows_node
```

මෙහි system එක trip dates සහ daily time slots analyze කරනවා.

Time slots:

- Early Morning
- Morning Rush
- Late Morning
- Midday
- School Pickup
- Evening Rush
- Evening

Each slot pressure score එක build වෙන්නේ:

- baseline traffic time-band score
- calendar/holiday/weekend score
- weather score
- RoadLK score
- live traffic score
- long route exposure bonus

Output:

- heatmap chart rows
- best window
- worst window
- selected departure match
- per-day slots
- pressure level for each travel window

UI එකේ Pressure & Weather tab එකේ heatmap එකෙන් මේ values show කරනවා.

## 18. Itinerary generation

Itinerary generation node එක:

```text
trip_graph/nodes.py -> itinerary_node
```

Itinerary builder file එක:

```text
travel_windows/itinerary/generator.py
```

මෙහි plan context එකට route, attractions, lodging, RoadLK, weather, traffic, crowd signals, travel windows යන සියල්ල pass වෙනවා.

Gemini enabled නම්:

- final itinerary story Gemini generate කරනවා
- route/weather/crowd/road/redistribution guidance narrative එකට include වෙනවා

Gemini fail වුණොත්:

- deterministic fallback itinerary එකක් generate වෙනවා
- app එක crash නොවෙයි

Output:

- itinerary_guidance
- itinerary_markdown
- itinerary_source

## 19. Final plan assembly

Final assembly node:

```text
trip_graph/nodes.py -> assemble_plan_node
```

මෙහි සියලු intermediate outputs එක final plan dictionary එකකට එකතු වෙනවා.

Final plan includes:

- routes
- recommended_route
- route_data
- nsgaii_summary
- road_alerts
- weather_data
- traffic_data
- crowd_signals
- travel_windows
- itinerary_guidance
- itinerary_markdown
- origin_resolved
- destination_resolved
- trip_days
- trip_dates
- warnings

මෙම final plan object එක Streamlit UI එකට return වෙනවා.

## 20. Output saving

Plan save logic එක:

```text
planner_pipeline.py
```

Functions:

```python
save_plan_snapshot(...)
save_plan_text_export(...)
```

Dashboard build වුණාම system එක files දෙකක් save කරනවා.

JSON snapshot:

```text
outputs/streamlit-trip-plan-YYYYMMDD-HHMMSS.json
```

Human-readable text export:

```text
outputs/streamlit-trip-plan-YYYYMMDD-HHMMSS.txt
```

Latest stable text file:

```text
outputs/latest-trip-plan.txt
```

මෙම text file එක post-plan advisor/chatbot එකට context එකක් ලෙස use කරන්න පුළුවන්. ඒ නිසා itinerary build වුණාට පස්සේ user ට “Day 2 එක risky ද?”, “Rain වැඩි වුණොත් මොකක් skip කරන්නද?”, “Best leaving time මොකක්ද?” වගේ follow-up questions අහන්න පුළුවන්.

## 21. Pressure & Weather Advisor

Advisor UI එක තියෙන්නේ:

```text
streamlit_app.py
```

Advisor context එක build වෙන data:

- current plan summary
- saved JSON snapshot
- latest text export
- weather/crowd/road/traffic/travel window data

Advisor Gemini-based conversational layer එකක්. It does not rebuild the route. It explains and guides based on already-built plan intelligence.

Typical questions:

```text
Which day feels riskiest?
Best time to leave on Day 2?
What should I skip if delayed?
Which attraction may be crowded?
```

## 22. Streamlit dashboard sections

Dashboard tabs:

```text
Journey By Day
Map & Routes
Pressure & Weather
Itinerary
```

### Journey By Day

මෙය main travel planning view එකයි.

Shows:

- day distance
- drive time
- pressure level
- anchor attraction
- accommodation
- best timing
- attractions for the day
- stay/route comfort
- weather snapshot
- flexibility advice

### Map & Routes

Shows:

- selected route
- alternative routes
- route map
- segment anchors
- attractions
- accommodations
- RoadLK warnings
- NSGA-II route ranking
- selected route spotlight

### Pressure & Weather

Shows:

- weather forecast
- pressure heatmap
- pressure drivers
- RoadLK road friction
- district/corridor pressure
- redistribution suggestions
- advisor chatbot

### Itinerary

Shows:

- final itinerary markdown
- planner summary
- route id, distance, duration, pressure, road/weather risk

## 23. API layer

FastAPI wrapper එක:

```text
api.py
```

මෙය optional backend API එකක් ලෙස තියෙනවා. React/frontend separation එකකට හෝ remote API call එකකට use කරන්න පුළුවන්.

Main endpoints:

- `GET /health`
- `POST /chat`
- `POST /plan`

නමුත් current main frontend එක Streamlit. Streamlit app එක direct `planner_pipeline.py` හරහා LangGraph flow එක call කරනවා.

## 24. Deployment

HF Spaces deployment සඳහා Docker setup එක තියෙන්නේ:

```text
Dockerfile
README.md
```

Required secrets:

```text
GOOGLE_MAPS_API_KEY
GEMINI_API_KEY
```

Important:

- `.env` files commit කරන්න හොඳ නැහැ
- HF Space secrets ලෙස keys add කරන්න
- `outputs/` ephemeral වෙන්න පුළුවන් unless persistent storage attach කරනවා

## 25. Current limitations

### Equal day segmentation

දැනට day segments route distance එක trip days ගණනට සමාන ලෙස බෙදනවා. ඒ නිසා හැම දවසකටම equal distance/duration පේන්න පුළුවන්.

Future improvement:

- attraction clusters අනුව day split කිරීම
- overnight base location අනුව day split කිරීම
- scenic/tourism corridor pacing අනුව segment boundaries move කිරීම

### Crowd pressure is estimated, not true live density

Crowd module එක true live tourist density monitoring system එකක් නොවෙයි. It is a pressure estimation model using proxy signals.

Proxy signals:

- holiday/weekend
- weather
- RoadLK
- live traffic
- route length
- attraction/corridor sensitivity

Future improvement:

- historical tourist arrivals
- attraction footfall
- hotel occupancy
- mobile mobility signals
- actual crowd count sensors

### Accommodation data quality

Accommodation dataset එක useful base එකක් වුණත් hotel-level coordinates, exact prices, and current availability වගේ things live booking systems තරම් accurate නොවිය හැක.

## 26. Why this architecture is strong

මෙම architecture එකේ strength එක වන්නේ LLM එක සියල්ල invent කරන system එකක් නොවීමයි.

Instead:

- Google Routes gives real route alternatives
- curated dataset gives controlled tourism knowledge
- RoadLK gives road incident context
- weather layer gives environmental risk
- traffic gives selected-route live movement friction
- crowd module combines pressure signals
- NSGA-II compares routes with multiple objectives
- Gemini only refines and explains, not blindly controls geography

ඒ නිසා system එක:

- route-aware
- data-driven
- explainable
- modular
- expandable
- Sri Lanka-focused

## 27. One-sentence summary

මෙම project එක user ගේ origin, destination, duration chatbot එකකින් ලබාගෙන, LangGraph route-first pipeline එකක් හරහා multiple Google route alternatives enrich කරලා, attractions, accommodations, RoadLK, weather, traffic, crowd pressure, travel windows, NSGA-II ranking සහ Gemini itinerary narrative එකක් combine කරමින් day-by-day intelligent tour package එකක් generate කරන system එකකි.
