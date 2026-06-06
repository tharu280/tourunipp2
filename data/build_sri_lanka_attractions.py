#!/usr/bin/env python3
"""Build and validate an expanded curated Sri Lanka attractions dataset."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


DATA_DIR = Path(__file__).parent
OUTPUT_PATH = DATA_DIR / "sri_lanka_attractions.json"
SUMMARY_PATH = DATA_DIR / "dataset_summary.md"

SLTDA_ATTRACTIONS = "https://www.sltda.gov.lk/en/tourist-attractions"
SLTDA_REGIONAL = "https://www.sltda.gov.lk/en/regional-tourism"
SL_TRAVEL_ZOO = "https://www.srilanka.travel/zoological-gardens"
DWC_PROTECTED = "https://www.dwc.gov.lk/?page_id=72"
DWC_WILPATTU = "https://www.dwc.gov.lk/wnp/about/"
DWC_MARINE = "https://www.dwc.gov.lk/?page_id=817"
BOTANIC_HOME = "https://en.botanicgardens.gov.lk/"
BOTANIC_HENARATHGODA = "https://en.botanicgardens.gov.lk/service/botanic-gardens-henarathgoda/"
BOTANIC_HAKGALA = "https://en.botanicgardens.gov.lk/service/botanic-gardens-hakgala/"
BOTANIC_PERADENIYA = "https://botanicgardens.gov.lk/service/royal-botanic-gardens-peradeniya/"
BOTANIC_MIRIJJAWILA = "https://en.botanicgardens.gov.lk/service/dry-zone-botanic-gardens-mirijjawila/"
BOTANIC_SEETHAWAKA = "https://en.botanicgardens.gov.lk/service/wet-zone-botanic-gardens-awissawella/"
MUSEUM_HOME = "https://www.museum.gov.lk/v1/home"
MUSEUM_LIST = "https://www.museum.gov.lk/v1/museums"
GANGARAMAYA_HOME = "https://gangaramaya.com/"
ENV_ZOO = "https://www.env.gov.lk/web/index.php/en/department-of-national-zoological-gardens"

UNESCO_ANURADHAPURA = "https://whc.unesco.org/en/list/200"
UNESCO_POLONNARUWA = "https://whc.unesco.org/en/list/201"
UNESCO_SIGIRIYA = "https://whc.unesco.org/en/list/202"
UNESCO_DAMBULLA = "https://whc.unesco.org/en/list/561"
UNESCO_KANDY = "https://whc.unesco.org/en/list/450"
UNESCO_GALLE = "https://whc.unesco.org/en/list/451"
UNESCO_SINHARAJA = "https://whc.unesco.org/en/list/405"
UNESCO_CENTRAL_HIGHLANDS = "https://whc.unesco.org/en/list/1203"


def wiki(title: str) -> str:
    return f"https://en.wikipedia.org/wiki/{title}"


DISTRICTS = [
    ("Ampara", "Eastern"),
    ("Anuradhapura", "North Central"),
    ("Badulla", "Uva"),
    ("Batticaloa", "Eastern"),
    ("Colombo", "Western"),
    ("Galle", "Southern"),
    ("Gampaha", "Western"),
    ("Hambantota", "Southern"),
    ("Jaffna", "Northern"),
    ("Kalutara", "Western"),
    ("Kandy", "Central"),
    ("Kegalle", "Sabaragamuwa"),
    ("Kilinochchi", "Northern"),
    ("Kurunegala", "North Western"),
    ("Mannar", "Northern"),
    ("Matale", "Central"),
    ("Matara", "Southern"),
    ("Monaragala", "Uva"),
    ("Mullaitivu", "Northern"),
    ("Nuwara Eliya", "Central"),
    ("Polonnaruwa", "North Central"),
    ("Puttalam", "North Western"),
    ("Ratnapura", "Sabaragamuwa"),
    ("Trincomalee", "Eastern"),
    ("Vavuniya", "Northern"),
]

PROVINCE_BY_DISTRICT = dict(DISTRICTS)
TIER_ORDER = {"tier_1": 1, "tier_2": 2, "tier_3": 3}
CATEGORY_SET = {
    "adventure",
    "beach",
    "cultural",
    "family",
    "historic",
    "museum",
    "nature",
    "religious",
    "scenic",
    "waterfall",
    "wildlife",
}
TAG_SET = {
    "budget_friendly",
    "couples",
    "day_trip",
    "family_friendly",
    "hidden_gem",
    "iconic",
    "must_see",
    "photography",
    "unesco",
}
SPARSE_DISTRICT_NOTES = {
    "Kilinochchi": "Kept intentionally sparse because the district has limited widely visited leisure attractions beyond a few meaningful war-history and landscape stops.",
    "Mullaitivu": "Kept intentionally sparse because tourism infrastructure remains light and adding more entries would quickly drift into low-signal filler.",
    "Vavuniya": "Kept intentionally sparse because it functions more as a transit gateway than a dense attraction district for most leisure itineraries.",
}
FOCUS_DISTRICTS = ["Colombo", "Galle", "Gampaha", "Kandy", "Matale", "Nuwara Eliya"]
BASELINE_DISTRICT_COUNTS = {
    "Ampara": 9,
    "Anuradhapura": 18,
    "Badulla": 22,
    "Batticaloa": 9,
    "Colombo": 22,
    "Galle": 24,
    "Gampaha": 13,
    "Hambantota": 16,
    "Jaffna": 16,
    "Kalutara": 13,
    "Kandy": 23,
    "Kegalle": 8,
    "Kilinochchi": 2,
    "Kurunegala": 11,
    "Mannar": 9,
    "Matale": 22,
    "Matara": 15,
    "Monaragala": 8,
    "Mullaitivu": 2,
    "Nuwara Eliya": 27,
    "Polonnaruwa": 14,
    "Puttalam": 12,
    "Ratnapura": 15,
    "Trincomalee": 18,
    "Vavuniya": 2,
}
CORRIDORS = {
    "Colombo -> Galle -> Matara -> Hambantota": ["Colombo", "Galle", "Matara", "Hambantota"],
    "Kandy -> Nuwara Eliya -> Ella -> Badulla": ["Kandy", "Nuwara Eliya", "Badulla"],
    "Kandy -> Matale -> Dambulla -> Sigiriya": ["Kandy", "Matale"],
    "Dambulla -> Polonnaruwa -> Anuradhapura": ["Matale", "Polonnaruwa", "Anuradhapura"],
    "Colombo -> Kalutara -> Bentota/Beruwala side": ["Colombo", "Kalutara"],
    "Trincomalee -> Batticaloa -> Ampara": ["Trincomalee", "Batticaloa", "Ampara"],
    "Jaffna -> Mannar": ["Jaffna", "Mannar"],
    "Ratnapura -> Belihuloya / southern hill-country edge": ["Ratnapura", "Monaragala"],
}
SLTDA_CROSS_REFERENCE_MAP = {
    "Arugam Bay": "Arugambay",
    "Sacred City of Anuradhapura": "Anuradhapura",
    "Nine Arch Bridge": "Ella",
    "Pasikuda Beach": "Pasikudah",
    "Kalkudah Beach": "Kalkudah",
    "Galle Fort": "Galle",
    "Hikkaduwa Beach and Marine Park": "Hikkaduwa",
    "Negombo Beach": "Negombo",
    "Yala National Park": "Yala National Park",
    "Bundala National Park": "Bundala Nation Park",
    "Nallur Kandaswamy Kovil": "Jaffna",
    "Bentota Beach": "Benthota",
    "Beruwala Beach": "Beruwala",
    "Temple of the Sacred Tooth Relic": "Kandy",
    "Pinnawala Elephant Orphanage": "Pinnawela",
    "Mannar Island": "Mannar",
    "Sigiriya Rock Fortress": "Sigiriya",
    "Dambulla Cave Temple": "Dambulla",
    "Mirissa Beach": "Matara",
    "Weligama Bay": "Weligama",
    "Horton Plains National Park": "Horton Plains",
    "Gregory Lake": "Nuwara Eliy",
    "Ancient City of Polonnaruwa": "Polonnaruwa",
    "Minneriya National Park": "Minneriya",
    "Kalpitiya": "Kalpitiya",
    "Wilpattu National Park": "Wilpattu National Park",
    "Adam's Peak (Sri Pada)": "Adams Peak",
    "Sinharaja Forest Reserve": "Sinharaja",
    "Koneswaram Temple": "Trincomalee",
    "Nilaveli Beach": "Nilaveli",
    "Kitulgala": "Kithulgala",
}


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def a(
    name: str,
    district: str,
    latitude: float,
    longitude: float,
    importance_score: int,
    estimated_visit_hours: float,
    tier: str,
    categories: list[str],
    tags: list[str],
    summary: str,
    source_urls: list[str],
) -> dict:
    return {
        "name": name,
        "district": district,
        "province": PROVINCE_BY_DISTRICT[district],
        "categories": categories,
        "latitude": latitude,
        "longitude": longitude,
        "importance_score": importance_score,
        "estimated_visit_hours": estimated_visit_hours,
        "tier": tier,
        "tags": tags,
        "summary": summary,
        "source_urls": source_urls,
    }


ATTRACTIONS = [
    # Ampara
    a("Arugam Bay", "Ampara", 6.8404, 81.8368, 9, 6.0, "tier_1", ["beach", "adventure", "scenic"], ["must_see", "iconic", "couples", "budget_friendly", "photography"], "Sri Lanka's best-known surf beach and the anchor attraction for east-coast stays in Ampara.", [SLTDA_ATTRACTIONS, wiki("Arugam_Bay")]),
    a("Kumana National Park", "Ampara", 6.5811, 81.6695, 8, 5.0, "tier_2", ["wildlife", "nature", "adventure"], ["must_see", "day_trip", "photography"], "A respected safari alternative with wetlands, birdlife, and lower-density wildlife experiences.", [DWC_PROTECTED, wiki("Kumana_National_Park")]),
    a("Muhudu Maha Viharaya", "Ampara", 6.5829, 81.8727, 7, 1.5, "tier_2", ["religious", "historic", "scenic"], ["iconic", "day_trip", "photography"], "A coastal Buddhist temple near Pottuvil that combines pilgrimage importance with strong seafront atmosphere.", [SLTDA_REGIONAL, wiki("Muhudu_Maha_Viharaya")]),
    a("Magul Maha Viharaya", "Ampara", 6.6207, 81.7813, 6, 1.5, "tier_3", ["religious", "historic", "cultural"], ["hidden_gem", "day_trip", "photography"], "An ancient forest-edge temple site valued for archaeology and a quieter historical setting.", [SLTDA_REGIONAL, wiki("Magul_Maha_Viharaya")]),
    a("Lahugala Kitulana National Park", "Ampara", 6.8594, 81.6933, 6, 3.0, "tier_3", ["wildlife", "nature"], ["hidden_gem", "day_trip", "photography"], "A smaller protected area worth considering for travelers interested in elephants and quieter dry-zone habitats.", [DWC_PROTECTED, wiki("Lahugala_Kitulana_National_Park")]),

    # Anuradhapura
    a("Sacred City of Anuradhapura", "Anuradhapura", 8.3500, 80.3964, 10, 6.0, "tier_1", ["historic", "cultural", "religious"], ["unesco", "must_see", "iconic", "day_trip", "photography"], "Sri Lanka's first ancient capital and one of the country's most important archaeological and pilgrimage landscapes.", [UNESCO_ANURADHAPURA, wiki("Anuradhapura")]),
    a("Mihintale", "Anuradhapura", 8.3546, 80.5034, 8, 3.0, "tier_2", ["historic", "religious", "scenic"], ["must_see", "day_trip", "photography"], "A major Buddhist pilgrimage hill linked to the introduction of Buddhism to Sri Lanka.", [SLTDA_REGIONAL, wiki("Mihintale")]),
    a("Jaya Sri Maha Bodhi", "Anuradhapura", 8.3446, 80.3959, 9, 1.5, "tier_1", ["religious", "historic", "cultural"], ["iconic", "must_see", "photography"], "The revered sacred fig shrine is one of the country's highest-value pilgrimage stops inside Anuradhapura.", [UNESCO_ANURADHAPURA, wiki("Jaya_Sri_Maha_Bodhi")]),
    a("Ruwanwelisaya", "Anuradhapura", 8.3503, 80.3968, 9, 1.5, "tier_1", ["religious", "historic", "cultural"], ["iconic", "must_see", "photography"], "One of Sri Lanka's most celebrated stupas and a core stop in any Anuradhapura day plan.", [UNESCO_ANURADHAPURA, wiki("Ruwanwelisaya")]),
    a("Jetavanaramaya", "Anuradhapura", 8.3517, 80.4009, 8, 1.5, "tier_2", ["historic", "religious", "cultural"], ["iconic", "day_trip", "photography"], "A monumental stupa complex that adds scale and archaeological depth to Anuradhapura itineraries.", [UNESCO_ANURADHAPURA, wiki("Jetavanaramaya")]),
    a("Isurumuniya", "Anuradhapura", 8.3350, 80.3881, 7, 1.0, "tier_2", ["historic", "religious", "cultural"], ["day_trip", "photography", "budget_friendly"], "A compact but rewarding temple stop known for its rock setting and famous stone carvings.", [UNESCO_ANURADHAPURA, wiki("Isurumuniya")]),

    # Badulla
    a("Nine Arch Bridge", "Badulla", 6.8747, 81.0608, 9, 2.0, "tier_1", ["scenic", "historic", "family"], ["must_see", "iconic", "day_trip", "photography"], "The signature Ella viewpoint for train photography and one of Sri Lanka's most recognizable rail landmarks.", [SLTDA_REGIONAL, wiki("Nine_Arch_Bridge")]),
    a("Little Adam's Peak", "Badulla", 6.8666, 81.0467, 8, 2.5, "tier_2", ["nature", "scenic", "adventure"], ["must_see", "family_friendly", "couples", "photography"], "An easy hike with sweeping views that fits cleanly into most Ella-based itineraries.", [SLTDA_REGIONAL, wiki("Little_Adam%27s_Peak")]),
    a("Ella Rock", "Badulla", 6.8662, 81.0542, 8, 4.0, "tier_2", ["nature", "scenic", "adventure"], ["must_see", "photography", "day_trip"], "A longer and more adventurous Ella-area hike with big ridge and valley views.", [SLTDA_REGIONAL, wiki("Ella_Rock")]),
    a("Ravana Falls", "Badulla", 6.8400, 81.0595, 7, 1.0, "tier_2", ["waterfall", "nature", "scenic"], ["day_trip", "photography", "budget_friendly"], "A highly accessible roadside waterfall that works well as a short stop near Ella.", [SLTDA_REGIONAL, wiki("Ravana_Falls")]),
    a("Diyaluma Falls", "Badulla", 6.7386, 81.0295, 8, 3.5, "tier_2", ["waterfall", "nature", "adventure", "scenic"], ["must_see", "photography", "day_trip"], "One of Sri Lanka's tallest waterfalls, popular for its views and upper natural pools.", [SLTDA_REGIONAL, wiki("Diyaluma_Falls")]),
    a("Lipton's Seat", "Badulla", 6.8096, 80.9383, 7, 2.0, "tier_2", ["scenic", "nature", "cultural"], ["couples", "photography", "day_trip"], "A classic tea-country viewpoint tied to colonial plantation history and broad hill panoramas.", [SLTDA_REGIONAL, wiki("Lipton%27s_Seat")]),
    a("Demodara Loop", "Badulla", 6.9001, 81.0555, 6, 1.0, "tier_3", ["scenic", "historic"], ["photography", "day_trip", "budget_friendly"], "A clever hill-country railway engineering stop that complements Ella train-focused itineraries.", [SLTDA_REGIONAL, wiki("Demodara_Loop")]),
    a("Adisham Bungalow", "Badulla", 6.7786, 80.9757, 6, 1.5, "tier_3", ["historic", "cultural", "scenic"], ["hidden_gem", "couples", "photography"], "A high-country manor and monastery site suited to slower Haputale-area sightseeing days.", [SLTDA_REGIONAL, wiki("Adisham_Hall")]),

    # Batticaloa
    a("Pasikuda Beach", "Batticaloa", 7.9291, 81.5612, 8, 5.0, "tier_2", ["beach", "family", "scenic"], ["must_see", "family_friendly", "couples", "photography"], "The district's main resort beach with calm, shallow water and easy family appeal.", [SLTDA_ATTRACTIONS, wiki("Pasikuda")]),
    a("Kalkudah Beach", "Batticaloa", 7.9308, 81.5697, 7, 3.0, "tier_2", ["beach", "scenic"], ["couples", "photography", "day_trip"], "A quieter neighboring stretch of coast often paired with Pasikuda.", [SLTDA_ATTRACTIONS, wiki("Kalkudah")]),
    a("Batticaloa Fort", "Batticaloa", 7.7102, 81.7005, 6, 1.5, "tier_2", ["historic", "cultural", "family"], ["day_trip", "photography", "budget_friendly"], "A compact colonial fort that gives Batticaloa's lagoonfront a strong heritage anchor.", [SLTDA_ATTRACTIONS, wiki("Batticaloa_Fort")]),
    a("Batticaloa Lagoon", "Batticaloa", 7.7248, 81.7000, 6, 1.5, "tier_3", ["scenic", "nature", "family"], ["couples", "photography", "day_trip"], "A scenic lagoon experience that adds sunset and boat-ride value to east-coast itineraries.", [SLTDA_REGIONAL, wiki("Batticaloa_Lagoon")]),
    a("Kallady Beach", "Batticaloa", 7.7109, 81.7114, 5, 2.0, "tier_3", ["beach", "scenic"], ["budget_friendly", "photography", "day_trip"], "A local-facing beach stop useful for travelers staying in Batticaloa town.", [SLTDA_REGIONAL, wiki("Kallady")]),

    # Colombo
    a("Colombo National Museum", "Colombo", 6.9101, 79.8612, 8, 2.5, "tier_2", ["museum", "historic", "cultural", "family"], ["family_friendly", "budget_friendly", "day_trip"], "Sri Lanka's flagship museum for archaeology, royal regalia, and national history.", [MUSEUM_HOME, wiki("Colombo_National_Museum")]),
    a("Gangaramaya Temple", "Colombo", 6.9167, 79.8563, 8, 1.5, "tier_2", ["religious", "cultural", "historic"], ["iconic", "family_friendly", "photography", "day_trip"], "One of Colombo's best-known temples and an easy cultural stop in the city center.", [GANGARAMAYA_HOME, wiki("Gangaramaya_Temple")]),
    a("Galle Face Green", "Colombo", 6.9271, 79.8447, 7, 1.5, "tier_2", ["scenic", "family", "cultural"], ["budget_friendly", "family_friendly", "couples", "photography"], "Colombo's signature waterfront promenade and a strong sunset/social stop.", [SLTDA_REGIONAL, wiki("Galle_Face_Green")]),
    a("Independence Memorial Hall", "Colombo", 6.9032, 79.8670, 7, 1.0, "tier_2", ["historic", "cultural", "family"], ["day_trip", "budget_friendly", "photography"], "A polished civic landmark that fits well into compact city loops.", [MUSEUM_LIST, wiki("Independence_Memorial_Hall")]),
    a("Dutch Museum", "Colombo", 6.9397, 79.8510, 6, 1.0, "tier_3", ["museum", "historic", "cultural"], ["day_trip", "budget_friendly"], "A smaller but worthwhile colonial-history museum in the old Pettah area.", [MUSEUM_LIST, wiki("Dutch_Museum,_Colombo")]),
    a("Jami Ul-Alfar Mosque", "Colombo", 6.9389, 79.8500, 7, 0.75, "tier_2", ["religious", "historic", "cultural"], ["iconic", "photography", "day_trip"], "The red-and-white mosque is one of Colombo's most distinctive urban landmarks.", [SLTDA_REGIONAL, wiki("Jami_Ul-Alfar_Mosque")]),
    a("Mount Lavinia Beach", "Colombo", 6.8389, 79.8637, 7, 3.0, "tier_2", ["beach", "scenic", "family"], ["couples", "family_friendly", "photography"], "The metro area's best-known leisure beach and a practical evening or half-day stop.", [SLTDA_REGIONAL, wiki("Mount_Lavinia_Beach")]),
    a("National Zoological Gardens of Sri Lanka", "Colombo", 6.8569, 79.8737, 6, 3.0, "tier_3", ["family", "wildlife"], ["family_friendly", "day_trip"], "A long-standing Colombo attraction that remains useful for family-focused itineraries.", [SL_TRAVEL_ZOO, ENV_ZOO, wiki("National_Zoological_Gardens_of_Sri_Lanka")]),
    a("National Museum of Natural History", "Colombo", 6.9105, 79.8615, 6, 1.0, "tier_3", ["museum", "family"], ["family_friendly", "day_trip", "budget_friendly"], "A practical companion stop to the main museum for wildlife and natural-history themed city itineraries.", [MUSEUM_LIST, wiki("National_Museum_of_Natural_History,_Sri_Lanka")]),
    a("Viharamahadevi Park", "Colombo", 6.9147, 79.8612, 6, 1.0, "tier_3", ["family", "scenic", "nature"], ["family_friendly", "budget_friendly", "day_trip"], "Colombo's best-known formal city park and a useful green-space stop between museum and civic landmarks.", [SLTDA_REGIONAL, wiki("Viharamahadevi_Park")]),
    a("Colombo Lighthouse", "Colombo", 6.9344, 79.8428, 6, 0.75, "tier_3", ["historic", "scenic"], ["photography", "day_trip"], "A recognizable harbour-front landmark that adds maritime context to central Colombo sightseeing.", [SLTDA_REGIONAL, wiki("Colombo_Lighthouse")]),
    a("Old Parliament Building", "Colombo", 6.9354, 79.8448, 6, 0.75, "tier_3", ["historic", "cultural"], ["photography", "day_trip"], "A notable neoclassical landmark on the seafront that helps strengthen walkable heritage coverage in central Colombo.", [SLTDA_REGIONAL, wiki("Old_Parliament_Building,_Colombo")]),
    a("Wolvendaal Church", "Colombo", 6.9422, 79.8573, 6, 1.0, "tier_3", ["historic", "religious", "cultural"], ["day_trip", "photography"], "One of Colombo's oldest surviving churches and a meaningful heritage stop beyond the main civic core.", [SLTDA_REGIONAL, wiki("Wolvendaal_Church")]),

    # Galle
    a("Galle Fort", "Galle", 6.0260, 80.2166, 10, 4.0, "tier_1", ["historic", "cultural", "scenic"], ["unesco", "must_see", "iconic", "couples", "photography"], "Sri Lanka's most atmospheric colonial fort city and a top-tier walking destination.", [UNESCO_GALLE, wiki("Galle_Fort")]),
    a("Unawatuna Beach", "Galle", 6.0100, 80.2496, 8, 4.0, "tier_2", ["beach", "scenic", "family"], ["must_see", "couples", "family_friendly", "photography"], "A classic south-coast beach that pairs easily with Galle Fort.", [SLTDA_ATTRACTIONS, wiki("Unawatuna")]),
    a("Hikkaduwa Beach and Marine Park", "Galle", 6.1407, 80.1006, 8, 4.0, "tier_2", ["beach", "nature", "adventure", "family"], ["family_friendly", "couples", "photography", "day_trip"], "A popular beach town known for snorkeling, surf culture, and easy tourist services.", [SLTDA_ATTRACTIONS, DWC_MARINE, wiki("Hikkaduwa")]),
    a("Japanese Peace Pagoda, Rumassala", "Galle", 6.0103, 80.2390, 6, 1.0, "tier_3", ["religious", "scenic", "cultural"], ["couples", "photography", "day_trip"], "A clifftop pagoda stop with good views over the bay and fort side of Galle.", [SLTDA_REGIONAL, wiki("Japanese_Peace_Pagoda,_Unawatuna")]),
    a("Jungle Beach", "Galle", 6.0076, 80.2457, 6, 2.0, "tier_3", ["beach", "scenic", "nature"], ["hidden_gem", "couples", "photography"], "A smaller sheltered beach often used as a quieter alternative to Unawatuna.", [SLTDA_REGIONAL, wiki("Jungle_Beach,_Sri_Lanka")]),
    a("Martin Wickramasinghe Folk Museum", "Galle", 5.9924, 80.3330, 6, 1.5, "tier_3", ["museum", "cultural", "historic"], ["day_trip", "family_friendly"], "A strong literary and ethnographic stop in the Koggala area for culture-oriented routes.", [MUSEUM_LIST, wiki("Martin_Wickramasinghe_Folk_Museum_Complex")]),
    a("Sea Turtle Hatchery, Habaraduwa", "Galle", 5.9878, 80.3093, 5, 1.0, "tier_3", ["family", "nature"], ["family_friendly", "day_trip"], "A common short stop for travelers interested in hatchery-based turtle education on the south coast.", [SLTDA_REGIONAL, wiki("Sea_Turtle_Conservation_Museum")]),
    a("Kanneliya Forest Reserve", "Galle", 6.2570, 80.3630, 6, 3.0, "tier_3", ["nature", "adventure", "wildlife"], ["hidden_gem", "photography", "day_trip"], "A rainforest hiking option inland from the coast for travelers wanting more nature variety.", [SLTDA_REGIONAL, wiki("Kanneliya-Dediyagala-Nakiyadeniya")]),
    a("Galle Lighthouse", "Galle", 6.0245, 80.2210, 7, 0.75, "tier_2", ["historic", "scenic"], ["iconic", "photography", "day_trip"], "The fort's photogenic lighthouse is one of the district's most recognizable supporting landmarks.", [UNESCO_GALLE, wiki("Galle_Lighthouse")]),
    a("Maritime Museum, Galle", "Galle", 6.0261, 80.2177, 6, 1.0, "tier_3", ["museum", "historic", "cultural"], ["day_trip", "family_friendly"], "A focused fort museum that adds maritime and tsunami-related interpretation to Galle visits.", [MUSEUM_LIST, wiki("National_Maritime_Museum,_Galle")]),
    a("National Museum of Galle", "Galle", 6.0251, 80.2162, 6, 1.0, "tier_3", ["museum", "historic", "cultural"], ["day_trip", "budget_friendly"], "A useful fort museum stop for travelers who want more regional historical context.", [MUSEUM_LIST, wiki("National_Museum_of_Galle")]),
    a("Flag Rock Bastion", "Galle", 6.0238, 80.2188, 6, 0.5, "tier_3", ["scenic", "historic"], ["photography", "couples", "day_trip"], "One of the best quick sunset and sea-view points on the fort ramparts.", [UNESCO_GALLE, wiki("Flag_Rock_Bastion")]),
    a("Groote Kerk, Galle", "Galle", 6.0271, 80.2168, 6, 0.75, "tier_3", ["historic", "religious", "cultural"], ["day_trip", "photography"], "The Dutch Reformed church is a worthwhile small-scale heritage stop inside the fort.", [UNESCO_GALLE, wiki("Dutch_Reformed_Church,_Galle")]),

    # Gampaha
    a("Negombo Beach", "Gampaha", 7.2304, 79.8407, 7, 3.0, "tier_2", ["beach", "family", "scenic"], ["family_friendly", "couples", "day_trip", "photography"], "A practical west-coast beach base near the airport and a common arrival/departure stop.", [SLTDA_ATTRACTIONS, wiki("Negombo")]),
    a("Muthurajawela Marsh", "Gampaha", 7.0917, 79.8447, 6, 2.5, "tier_3", ["nature", "wildlife", "family"], ["family_friendly", "day_trip", "photography"], "A wetland boat-ride option close to Negombo with accessible birding value.", [SLTDA_REGIONAL, wiki("Muthurajawela")]),
    a("Negombo Lagoon", "Gampaha", 7.1931, 79.8278, 6, 2.0, "tier_3", ["nature", "scenic", "family"], ["couples", "photography", "day_trip"], "A lagoon excursion area that adds sunrise, fishing, and boat-tour options to Negombo stays.", [SLTDA_REGIONAL, wiki("Negombo_Lagoon")]),
    a("Negombo Dutch Fort", "Gampaha", 7.2137, 79.8397, 5, 0.75, "tier_3", ["historic", "cultural"], ["budget_friendly", "day_trip"], "A smaller colonial remnant that works as a quick add-on near the fish market zone.", [SLTDA_REGIONAL, wiki("Negombo_Fort")]),
    a("Angurukaramulla Temple", "Gampaha", 7.2166, 79.8479, 6, 1.0, "tier_3", ["religious", "cultural"], ["day_trip", "photography"], "A colorful temple stop in Negombo that adds religious architecture and local character.", [SLTDA_REGIONAL, wiki("Angurukaramulla_Temple")]),
    a("Kelaniya Raja Maha Vihara", "Gampaha", 6.9553, 79.9210, 7, 1.5, "tier_2", ["religious", "historic", "cultural"], ["iconic", "day_trip", "photography"], "One of the island's important Buddhist temples and a solid cultural stop near Colombo.", [SLTDA_REGIONAL, wiki("Kelaniya_Raja_Maha_Vihara")]),
    a("Henarathgoda Botanical Garden", "Gampaha", 7.0913, 79.9972, 7, 2.0, "tier_2", ["nature", "family", "scenic"], ["family_friendly", "day_trip", "photography"], "A historic botanic garden in Gampaha that broadens the district beyond Negombo-focused coastal stops.", [BOTANIC_HENARATHGODA, BOTANIC_HOME, wiki("Henarathgoda_Botanical_Garden")]),
    a("Hamilton Canal", "Gampaha", 7.2087, 79.8387, 5, 1.0, "tier_3", ["historic", "scenic"], ["day_trip", "budget_friendly", "photography"], "A colonial-era canal corridor that adds local waterway character to Negombo urban itineraries.", [SLTDA_REGIONAL, wiki("Hamilton_Canal_(Sri_Lanka)")]),
    a("St. Mary's Church, Negombo", "Gampaha", 7.2090, 79.8395, 6, 0.75, "tier_3", ["religious", "historic", "cultural"], ["day_trip", "photography"], "A major Catholic landmark in Negombo that is genuinely useful on heritage-oriented walking routes.", [SLTDA_REGIONAL, wiki("St._Mary%27s_Church,_Negombo")]),
    a("Negombo Fish Market", "Gampaha", 7.2174, 79.8388, 6, 1.0, "tier_3", ["cultural", "family"], ["day_trip", "photography", "budget_friendly"], "A lively local market stop that adds working-harbour atmosphere and everyday coastal character.", [SLTDA_REGIONAL, wiki("Negombo_Fish_Market")]),

    # Hambantota
    a("Yala National Park", "Hambantota", 6.3725, 81.5185, 10, 5.0, "tier_1", ["wildlife", "nature", "adventure"], ["must_see", "iconic", "photography", "day_trip"], "Sri Lanka's best-known safari destination and a major itinerary anchor in the deep south.", [DWC_PROTECTED, SLTDA_ATTRACTIONS, wiki("Yala_National_Park")]),
    a("Bundala National Park", "Hambantota", 6.1969, 81.2102, 8, 4.0, "tier_2", ["wildlife", "nature", "scenic"], ["unesco", "must_see", "photography", "day_trip"], "A leading wetland and birdwatching park that complements Yala well.", [DWC_PROTECTED, SLTDA_ATTRACTIONS, wiki("Bundala_National_Park")]),
    a("Tangalle Beach", "Hambantota", 6.0242, 80.7950, 8, 4.0, "tier_2", ["beach", "scenic", "family"], ["must_see", "couples", "photography"], "A broad and attractive southern beach base with stronger scenery than urban beach towns.", [SLTDA_REGIONAL, wiki("Tangalle")]),
    a("Hummanaya Blow Hole", "Hambantota", 6.0722, 80.8209, 6, 1.0, "tier_3", ["scenic", "nature"], ["day_trip", "photography"], "A dramatic coastal geological stop best used as a short scenic detour near Tangalle.", [SLTDA_REGIONAL, wiki("Hummanaya")]),
    a("Mulkirigala Raja Maha Vihara", "Hambantota", 6.2430, 80.7218, 7, 1.5, "tier_2", ["religious", "historic", "scenic"], ["hidden_gem", "photography", "day_trip"], "A rock monastery complex that gives Hambantota itineraries a strong inland heritage option.", [SLTDA_REGIONAL, wiki("Mulkirigala_Raja_Maha_Vihara")]),
    a("Rekawa Beach", "Hambantota", 6.0427, 80.8293, 6, 2.0, "tier_3", ["beach", "nature", "scenic"], ["photography", "day_trip"], "A quieter coastal stretch associated with turtle-watching and lower-key beach time.", [DWC_MARINE, wiki("Rekawa")]),
    a("Dry Zone Botanic Gardens, Mirijjawila", "Hambantota", 6.2540, 81.1390, 6, 2.0, "tier_3", ["nature", "family", "scenic"], ["family_friendly", "day_trip"], "A substantial botanic garden that broadens Hambantota beyond beaches and wildlife.", [BOTANIC_MIRIJJAWILA, BOTANIC_HOME, wiki("Dry_Zone_Botanic_Gardens,_Hambantota")]),
    a("Ridiyagama Safari Park", "Hambantota", 6.3988, 81.1654, 6, 3.0, "tier_3", ["family", "wildlife"], ["family_friendly", "day_trip"], "A family-focused safari park option that can support mixed-age travel plans in the district.", [ENV_ZOO, wiki("Ridiyagama_Safari_Park")]),

    # Jaffna
    a("Nallur Kandaswamy Kovil", "Jaffna", 9.6758, 80.0303, 8, 1.5, "tier_2", ["religious", "cultural", "historic"], ["iconic", "photography", "day_trip"], "The defining Hindu temple landmark of Jaffna and a core cultural stop in the north.", [SLTDA_ATTRACTIONS, wiki("Nallur_Kandaswamy_temple")]),
    a("Jaffna Fort", "Jaffna", 9.6615, 80.0073, 7, 1.5, "tier_2", ["historic", "cultural", "scenic"], ["day_trip", "photography", "budget_friendly"], "A major colonial fortification with open views and strong historical context.", [SLTDA_ATTRACTIONS, wiki("Jaffna_Fort")]),
    a("Delft Island", "Jaffna", 9.4833, 79.7167, 7, 6.0, "tier_2", ["scenic", "historic", "adventure"], ["hidden_gem", "photography", "day_trip"], "A full-day island excursion known for open landscapes, ruins, and wild horses.", [SLTDA_REGIONAL, wiki("Delft_Island")]),
    a("Casuarina Beach", "Jaffna", 9.8176, 79.9716, 6, 3.0, "tier_3", ["beach", "scenic", "family"], ["family_friendly", "couples", "photography"], "One of the better-known leisure beaches within easy reach of Jaffna town.", [SLTDA_REGIONAL, wiki("Casuarina_Beach")]),
    a("Nagadeepa Purana Vihara", "Jaffna", 9.6036, 79.7736, 7, 2.5, "tier_2", ["religious", "cultural", "historic"], ["iconic", "day_trip"], "An island pilgrimage temple commonly visited on northern cultural circuits.", [SLTDA_REGIONAL, wiki("Nagadeepa_Purana_Vihara")]),
    a("Keerimalai Naguleswaram Temple", "Jaffna", 9.8212, 79.9670, 7, 1.5, "tier_2", ["religious", "historic", "scenic"], ["photography", "day_trip"], "A coastal temple site that combines religious significance with nearby springs and sea views.", [SLTDA_REGIONAL, wiki("Naguleswaram_temple")]),
    a("Dambakola Patuna", "Jaffna", 9.7448, 80.0197, 6, 1.5, "tier_3", ["religious", "historic", "scenic"], ["hidden_gem", "day_trip", "photography"], "A quieter northern pilgrimage and historical site with shoreline character.", [SLTDA_REGIONAL, wiki("Dambakola_Patuna")]),
    a("Jaffna Public Library", "Jaffna", 9.6674, 80.0110, 6, 0.75, "tier_3", ["cultural", "historic"], ["iconic", "day_trip", "budget_friendly"], "An important civic and cultural landmark with deep symbolic value in the north.", [SLTDA_REGIONAL, wiki("Jaffna_Public_Library")]),

    # Kalutara
    a("Bentota Beach", "Kalutara", 6.4218, 79.9957, 8, 4.0, "tier_2", ["beach", "family", "adventure"], ["must_see", "family_friendly", "couples", "photography"], "A long-established west-coast beach resort area with broad mainstream appeal.", [SLTDA_ATTRACTIONS, wiki("Bentota")]),
    a("Brief Garden", "Kalutara", 6.4618, 80.0321, 6, 1.5, "tier_3", ["cultural", "scenic", "family"], ["couples", "photography", "hidden_gem", "day_trip"], "A design-forward landscape garden that adds an elegant inland stop to Bentota itineraries.", [SLTDA_REGIONAL, wiki("Brief_Garden,_Sri_Lanka")]),
    a("Kalutara Bodhiya", "Kalutara", 6.5853, 79.9607, 7, 1.0, "tier_2", ["religious", "cultural"], ["iconic", "day_trip", "photography"], "A major roadside Buddhist landmark that is highly recognizable to domestic travelers.", [SLTDA_REGIONAL, wiki("Kalutara_Chaitya")]),
    a("Richmond Castle", "Kalutara", 6.5910, 80.1526, 6, 1.5, "tier_3", ["historic", "cultural", "family"], ["day_trip", "photography"], "A photogenic Edwardian mansion and estate that supports slower day-trip itineraries.", [SLTDA_REGIONAL, wiki("Richmond_Castle,_Kalutara")]),
    a("Beruwala Beach", "Kalutara", 6.4788, 79.9821, 7, 3.0, "tier_2", ["beach", "scenic", "family"], ["couples", "family_friendly", "photography"], "A popular west-coast beach area with easy resort access and coastal day-use value.", [SLTDA_ATTRACTIONS, wiki("Beruwala")]),
    a("Fa Hien Caves", "Kalutara", 6.3729, 80.1363, 6, 2.0, "tier_3", ["historic", "nature", "cultural"], ["hidden_gem", "day_trip"], "An important prehistoric cave site best suited to travelers seeking archaeology beyond the coast.", [SLTDA_REGIONAL, wiki("Fa_Hien_Cave")]),

    # Kandy
    a("Temple of the Sacred Tooth Relic", "Kandy", 7.2936, 80.6413, 10, 2.5, "tier_1", ["religious", "historic", "cultural"], ["unesco", "must_see", "iconic", "photography"], "Sri Lanka's most important Buddhist shrine and the central cultural draw in Kandy.", [UNESCO_KANDY, wiki("Temple_of_the_Tooth")]),
    a("Royal Botanic Gardens, Peradeniya", "Kandy", 7.2682, 80.5950, 8, 3.0, "tier_2", ["nature", "family", "scenic"], ["family_friendly", "couples", "photography", "day_trip"], "The island's most important botanic garden and a dependable half-day Kandy outing.", [BOTANIC_PERADENIYA, wiki("Royal_Botanic_Gardens,_Peradeniya")]),
    a("Kandy Lake", "Kandy", 7.2913, 80.6413, 7, 1.0, "tier_2", ["scenic", "historic", "family"], ["couples", "photography", "budget_friendly"], "A central scenic element that improves walkable Kandy itineraries and evening pacing.", [UNESCO_KANDY, wiki("Kandy_Lake")]),
    a("Bahirawakanda Vihara Buddha Statue", "Kandy", 7.2881, 80.6294, 6, 1.0, "tier_3", ["religious", "scenic"], ["photography", "day_trip"], "A city-overlook viewpoint best used as a short scenic add-on in Kandy.", [SLTDA_REGIONAL, wiki("Bahirawakanda_Vihara_Buddha_Statue")]),
    a("Udawattakele Forest Reserve", "Kandy", 7.3008, 80.6444, 7, 2.0, "tier_2", ["nature", "wildlife", "scenic"], ["day_trip", "photography"], "A close-to-town forest reserve that gives Kandy itineraries a useful urban-nature option.", [SLTDA_REGIONAL, wiki("Udawattakele_Forest_Reserve")]),
    a("Ceylon Tea Museum", "Kandy", 7.2695, 80.6338, 7, 1.5, "tier_2", ["museum", "cultural", "historic"], ["day_trip", "family_friendly"], "A strong interpretive stop for travelers interested in the tea industry's heritage.", [MUSEUM_LIST, wiki("Ceylon_Tea_Museum")]),
    a("Embekka Devalaya", "Kandy", 7.2148, 80.5713, 7, 1.0, "tier_2", ["historic", "religious", "cultural"], ["day_trip", "photography"], "An important temple complex renowned for fine wood carving.", [SLTDA_REGIONAL, wiki("Embekka_Devalaya")]),
    a("Lankatilaka Vihara", "Kandy", 7.2408, 80.5751, 7, 1.0, "tier_2", ["religious", "historic", "cultural"], ["day_trip", "photography"], "A high-set medieval temple that fits naturally into the Gampola-side heritage circuit.", [SLTDA_REGIONAL, wiki("Lankatilaka_Vihara")]),
    a("National Museum of Kandy", "Kandy", 7.2929, 80.6410, 7, 1.0, "tier_2", ["museum", "historic", "cultural"], ["day_trip", "family_friendly"], "An easy add-on near the Temple of the Tooth that improves Kandy's core heritage coverage.", [MUSEUM_LIST, wiki("National_Museum,_Kandy")]),
    a("Royal Palace of Kandy", "Kandy", 7.2934, 80.6416, 7, 1.0, "tier_2", ["historic", "cultural"], ["day_trip", "photography"], "The former royal palace complex adds political and courtly context to the sacred city visit.", [UNESCO_KANDY, wiki("Royal_Palace_of_Kandy")]),
    a("Gadaladeniya Temple", "Kandy", 7.2249, 80.6012, 7, 1.0, "tier_2", ["religious", "historic", "cultural"], ["day_trip", "photography"], "A strong supporting temple stop that complements Embekka and Lankatilaka in the same heritage corridor.", [SLTDA_REGIONAL, wiki("Gadaladeniya_Temple")]),
    a("Degaldoruwa Raja Maha Vihara", "Kandy", 7.2761, 80.7014, 7, 1.0, "tier_2", ["religious", "historic", "cultural"], ["day_trip", "photography"], "Known for murals and cave-temple character, it adds more depth to Kandy's temple inventory.", [SLTDA_REGIONAL, wiki("Degaldoruwa_Raja_Maha_Vihara")]),
    a("Kandy View Point", "Kandy", 7.2842, 80.6464, 6, 0.75, "tier_3", ["scenic", "family"], ["photography", "couples", "day_trip"], "A practical overlook for travelers who want an easy city panorama without a longer excursion.", [SLTDA_REGIONAL, wiki("Kandy_View_Point")]),

    # Kegalle
    a("Pinnawala Elephant Orphanage", "Kegalle", 7.3018, 80.3882, 7, 2.5, "tier_2", ["family", "wildlife", "cultural"], ["iconic", "family_friendly", "day_trip"], "One of Sri Lanka's most famous family stops, centered on elephant viewing and care routines.", [SLTDA_ATTRACTIONS, wiki("Pinnawala_Elephant_Orphanage")]),
    a("Belilena Cave", "Kegalle", 7.0047, 80.3327, 5, 2.5, "tier_3", ["historic", "nature", "adventure"], ["hidden_gem", "photography", "day_trip"], "A prehistoric cave site with archaeological significance and a forested approach.", [SLTDA_REGIONAL, wiki("Belilena")]),
    a("Pinnawala Open Zoo", "Kegalle", 7.3245, 80.3881, 5, 2.0, "tier_3", ["family", "wildlife"], ["family_friendly", "day_trip"], "An optional family stop in the Pinnawala cluster for travelers already focusing on that corridor.", [ENV_ZOO, wiki("Pinnawala_Open_Zoo")]),
    a("Alagalla Mountain Range", "Kegalle", 7.1127, 80.4461, 6, 4.0, "tier_3", ["nature", "scenic", "adventure"], ["hidden_gem", "photography", "day_trip"], "A rewarding hike for more outdoors-oriented travelers moving between Kandy and Colombo side routes.", [SLTDA_REGIONAL, wiki("Alagalla_Mountain_Range")]),
    a("Kitulgala", "Kegalle", 6.9892, 80.4178, 7, 4.0, "tier_2", ["adventure", "nature", "scenic"], ["must_see", "photography", "day_trip"], "An SLTDA-listed wet-zone adventure base best known for white-water rafting, rainforest scenery, and active day trips.", [SLTDA_ATTRACTIONS, wiki("Kitulgala")]),

    # Kilinochchi
    a("Elephant Pass", "Kilinochchi", 9.5035, 80.4081, 5, 1.0, "tier_3", ["historic", "scenic", "cultural"], ["day_trip", "photography"], "A historically important isthmus and war-history stop on the northbound corridor.", [SLTDA_REGIONAL, wiki("Elephant_Pass")]),
    a("Iranamadu Tank", "Kilinochchi", 9.1041, 80.5186, 5, 1.0, "tier_3", ["scenic", "nature"], ["day_trip", "photography"], "A large reservoir stop mainly useful for route context, open landscapes, and local sightseeing.", [SLTDA_REGIONAL, wiki("Iranamadu_Tank")]),

    # Kurunegala
    a("Yapahuwa Rock Fortress", "Kurunegala", 7.8229, 80.3028, 7, 2.5, "tier_2", ["historic", "cultural", "scenic"], ["must_see", "photography", "day_trip"], "A dramatic medieval capital site with a memorable stone stairway and hilltop remains.", [SLTDA_REGIONAL, wiki("Yapahuwa")]),
    a("Ridi Viharaya", "Kurunegala", 7.6501, 80.1939, 6, 1.5, "tier_3", ["religious", "historic", "cultural"], ["day_trip", "photography", "budget_friendly"], "A long-standing temple complex with murals, caves, and historical associations.", [SLTDA_REGIONAL, wiki("Ridi_Viharaya")]),
    a("Panduwasnuwara", "Kurunegala", 7.4893, 80.1905, 6, 1.5, "tier_3", ["historic", "cultural"], ["hidden_gem", "day_trip"], "A worthwhile ancient kingdom site for travelers interested in Sri Lanka's lesser-visited capitals.", [SLTDA_REGIONAL, wiki("Panduwasnuwara")]),
    a("Athugala Rock", "Kurunegala", 7.4868, 80.3647, 6, 1.0, "tier_3", ["scenic", "family"], ["photography", "day_trip", "budget_friendly"], "The defining lookout above Kurunegala town and a practical short stop on transit days.", [SLTDA_REGIONAL, wiki("Athugala")]),
    a("Dambadeniya Kingdom", "Kurunegala", 7.3704, 80.1701, 6, 1.5, "tier_3", ["historic", "cultural"], ["day_trip", "hidden_gem"], "Another historic capital site that adds depth for culture-focused inland itineraries.", [SLTDA_REGIONAL, wiki("Dambadeniya")]),

    # Mannar
    a("Mannar Island", "Mannar", 8.9819, 79.9047, 6, 4.0, "tier_3", ["scenic", "historic", "beach"], ["hidden_gem", "photography", "day_trip"], "A remote-feeling island district stop with coastal landscapes and birding context.", [SLTDA_ATTRACTIONS, wiki("Mannar_Island")]),
    a("Shrine of Our Lady of Madhu", "Mannar", 8.8655, 80.1415, 7, 1.5, "tier_2", ["religious", "cultural", "historic"], ["iconic", "day_trip"], "One of Sri Lanka's most important Catholic pilgrimage sites.", [SLTDA_REGIONAL, wiki("Shrine_of_Our_Lady_of_Madhu")]),
    a("Mannar Fort", "Mannar", 8.9776, 79.9093, 6, 1.0, "tier_3", ["historic", "cultural"], ["photography", "day_trip"], "A colonial-era fortification that supports short heritage loops on the island.", [SLTDA_REGIONAL, wiki("Mannar_Fort")]),
    a("Baobab Tree, Mannar", "Mannar", 8.9797, 79.9054, 5, 0.5, "tier_3", ["historic", "family"], ["budget_friendly", "day_trip"], "A quick but distinctive landmark reflecting Mannar's Indian Ocean trading history.", [SLTDA_REGIONAL, wiki("Baobab_Tree,_Mannar")]),
    a("Thiruketheeswaram Temple", "Mannar", 8.9367, 79.9123, 7, 1.5, "tier_2", ["religious", "historic", "cultural"], ["iconic", "day_trip", "photography"], "A major Hindu temple with strong religious importance and long historical roots.", [SLTDA_REGIONAL, wiki("Thiruketheeswaram")]),

    # Matale
    a("Sigiriya Rock Fortress", "Matale", 7.9570, 80.7603, 10, 4.0, "tier_1", ["historic", "cultural", "scenic"], ["unesco", "must_see", "iconic", "photography"], "Sri Lanka's most iconic archaeological landmark and one of the country's highest-value attractions.", [UNESCO_SIGIRIYA, wiki("Sigiriya")]),
    a("Dambulla Cave Temple", "Matale", 7.8567, 80.6492, 9, 2.5, "tier_1", ["religious", "historic", "cultural"], ["unesco", "must_see", "iconic", "photography"], "A world-famous cave temple complex with major artistic and religious importance.", [UNESCO_DAMBULLA, wiki("Dambulla_cave_temple")]),
    a("Pidurangala Rock", "Matale", 7.9667, 80.7600, 8, 3.0, "tier_2", ["nature", "scenic", "adventure"], ["must_see", "couples", "photography"], "The best supporting hike to Sigiriya, prized for summit views back toward Lion Rock.", [SLTDA_REGIONAL, wiki("Pidurangala")]),
    a("Nalanda Gedige", "Matale", 7.6731, 80.7281, 7, 1.0, "tier_2", ["historic", "cultural", "religious"], ["day_trip", "photography"], "A distinctive stone temple known for its hybrid South Asian architectural character.", [SLTDA_REGIONAL, wiki("Nalanda_Gedige")]),
    a("Aluvihare Rock Temple", "Matale", 7.4969, 80.6246, 7, 1.5, "tier_2", ["religious", "historic", "cultural"], ["day_trip", "photography"], "An important Buddhist monastic and scriptural site just south of Matale town.", [SLTDA_REGIONAL, wiki("Aluvihare_Rock_Temple")]),
    a("Riverston", "Matale", 7.5720, 80.7543, 7, 3.0, "tier_2", ["nature", "scenic", "adventure"], ["hidden_gem", "photography", "day_trip"], "A cool-climate highland area valued for viewpoint drives and hiking.", [SLTDA_REGIONAL, wiki("Riverston")]),
    a("Sembuwatta Lake", "Matale", 7.3547, 80.7088, 6, 2.0, "tier_3", ["scenic", "nature", "family"], ["couples", "photography", "day_trip"], "A scenic upland leisure stop suitable for lighter day plans between Kandy and Matale.", [SLTDA_REGIONAL, wiki("Sembuwatta_Lake")]),
    a("Ibbankatuwa Megalithic Tombs", "Matale", 7.8720, 80.6547, 6, 1.0, "tier_3", ["historic", "cultural"], ["day_trip", "hidden_gem"], "A useful archaeological add-on for culture-heavy routes around Dambulla.", [SLTDA_REGIONAL, wiki("Ibbankatuwa_Megalithic_Tombs")]),
    a("Knuckles Mountain Range", "Matale", 7.4536, 80.7796, 8, 5.0, "tier_2", ["nature", "adventure", "scenic", "wildlife"], ["must_see", "photography", "day_trip"], "A major trekking and landscape area that meaningfully broadens Matale beyond the cultural triangle core.", [UNESCO_CENTRAL_HIGHLANDS, wiki("Knuckles_Mountain_Range")]),
    a("Pitawala Pathana", "Matale", 7.5661, 80.7640, 7, 2.0, "tier_2", ["nature", "scenic", "adventure"], ["hidden_gem", "photography", "day_trip"], "One of the best-accessible Knuckles-area outings, useful for half-day highland nature planning.", [SLTDA_REGIONAL, wiki("Pitawala_Pathana")]),
    a("Wasgamuwa National Park", "Matale", 7.7485, 80.9438, 7, 4.5, "tier_2", ["wildlife", "nature", "adventure"], ["day_trip", "photography"], "A substantial inland safari option that adds wildlife variety to Matale-centered itineraries.", [DWC_PROTECTED, wiki("Wasgamuwa_National_Park")]),
    a("Sera Ella Falls", "Matale", 7.6043, 80.8345, 6, 1.5, "tier_3", ["waterfall", "nature", "scenic"], ["hidden_gem", "photography", "day_trip"], "A rewarding waterfall stop in the Riverston side of the district, especially useful for scenic day loops.", [SLTDA_REGIONAL, wiki("Sera_Ella")]),
    a("Sri Muthumariamman Temple, Matale", "Matale", 7.4670, 80.6232, 6, 0.75, "tier_3", ["religious", "cultural"], ["photography", "day_trip"], "A colorful and highly visible town temple that adds South Indian-influenced religious architecture to Matale itineraries.", [SLTDA_REGIONAL, wiki("Sri_Muthumariamman_Thevasthanam")]),

    # Matara
    a("Mirissa Beach", "Matara", 5.9483, 80.4716, 8, 4.0, "tier_2", ["beach", "scenic", "family"], ["must_see", "couples", "photography", "family_friendly"], "A marquee south-coast beach destination known for leisure stays and whale-watching access.", [SLTDA_REGIONAL, DWC_MARINE, wiki("Mirissa")]),
    a("Weligama Bay", "Matara", 5.9730, 80.4297, 7, 4.0, "tier_2", ["beach", "adventure", "family"], ["family_friendly", "couples", "budget_friendly", "photography"], "A broad bay popular for beginner surfing and relaxed beach time.", [SLTDA_ATTRACTIONS, wiki("Weligama")]),
    a("Polhena Beach", "Matara", 5.9545, 80.5235, 6, 2.0, "tier_3", ["beach", "family", "scenic"], ["family_friendly", "day_trip"], "A calm urban-adjacent beach that adds easy family leisure time near Matara.", [SLTDA_REGIONAL, wiki("Polhena")]),
    a("Matara Star Fort", "Matara", 5.9486, 80.5472, 6, 1.0, "tier_3", ["historic", "cultural"], ["day_trip", "budget_friendly"], "A compact Dutch fortification that works as a short heritage stop in town.", [MUSEUM_LIST, wiki("Star_fort,_Matara")]),
    a("Weherahena Temple", "Matara", 5.9936, 80.5756, 6, 1.5, "tier_3", ["religious", "cultural"], ["photography", "day_trip"], "A colorful Buddhist temple complex and a dependable cultural diversion inland from the beaches.", [SLTDA_REGIONAL, wiki("Weherahena_Temple")]),
    a("Dondra Head Lighthouse", "Matara", 5.9312, 80.5889, 6, 1.0, "tier_3", ["scenic", "historic"], ["photography", "day_trip"], "The southern headland lighthouse provides strong geographic and visual identity for the district.", [SLTDA_REGIONAL, wiki("Dondra_Head_Lighthouse")]),
    a("Kushtarajagala Statue", "Matara", 5.9747, 80.4291, 5, 0.75, "tier_3", ["historic", "cultural", "religious"], ["day_trip", "budget_friendly"], "A useful short archaeological stop in Weligama for travelers layering history into beach trips.", [SLTDA_REGIONAL, wiki("Kushtarajagala")]),

    # Monaragala
    a("Kataragama Sacred City", "Monaragala", 6.4138, 81.3320, 8, 2.0, "tier_2", ["religious", "cultural", "historic"], ["iconic", "day_trip", "photography"], "A major multi-faith pilgrimage town and a meaningful stop on deep-south and southeast routes.", [SLTDA_REGIONAL, wiki("Kataragama_temple")]),
    a("Buduruwagala Temple", "Monaragala", 6.6861, 81.0710, 6, 1.5, "tier_3", ["historic", "religious", "cultural"], ["day_trip", "photography", "budget_friendly"], "An impressive ancient rock-cut Buddhist site featuring a monumental standing Buddha figure.", [SLTDA_REGIONAL, wiki("Buduruwagala")]),
    a("Nil Diya Pokuna", "Monaragala", 6.8739, 81.0716, 6, 2.5, "tier_3", ["adventure", "nature"], ["hidden_gem", "day_trip"], "A more adventurous cave-pool excursion for travelers staying around Ella or Wellawaya.", [SLTDA_REGIONAL, wiki("Nil_Diya_Pokuna")]),
    a("Yudaganawa Raja Maha Vihara", "Monaragala", 6.7640, 81.0959, 5, 1.0, "tier_3", ["religious", "historic", "cultural"], ["hidden_gem", "day_trip"], "A quieter archaeological and religious site that gives Monaragala extra depth without resorting to filler.", [SLTDA_REGIONAL, wiki("Yudaganawa")]),

    # Mullaitivu
    a("Mullaitivu Beach", "Mullaitivu", 9.2671, 80.8141, 4, 2.0, "tier_3", ["beach", "scenic"], ["hidden_gem", "photography", "day_trip"], "A low-key northern coastal stop included conservatively as one of the district's clearest visitor-facing sites.", [SLTDA_REGIONAL, wiki("Mullaitivu")]),
    a("Kokkilai Sanctuary", "Mullaitivu", 9.3310, 80.8760, 5, 2.5, "tier_3", ["wildlife", "nature", "scenic"], ["hidden_gem", "photography", "day_trip"], "A wetland bird habitat that gives the district one meaningful nature entry without drifting into generic local POIs.", [DWC_PROTECTED, wiki("Kokkilai_Sanctuary")]),

    # Nuwara Eliya
    a("Horton Plains National Park", "Nuwara Eliya", 6.8096, 80.8073, 9, 4.5, "tier_1", ["nature", "wildlife", "scenic", "adventure"], ["unesco", "must_see", "photography", "day_trip"], "A highland plateau park famed for World's End, cloud forest scenery, and cool-climate trekking.", [UNESCO_CENTRAL_HIGHLANDS, DWC_PROTECTED, wiki("Horton_Plains_National_Park")]),
    a("Gregory Lake", "Nuwara Eliya", 6.9497, 80.7891, 6, 1.5, "tier_3", ["scenic", "family", "nature"], ["family_friendly", "couples", "photography", "day_trip"], "A popular Nuwara Eliya stop for easy recreation and lakeside strolling.", [SLTDA_ATTRACTIONS, wiki("Gregory_Lake")]),
    a("Hakgala Botanical Garden", "Nuwara Eliya", 6.9234, 80.8211, 7, 2.0, "tier_2", ["nature", "family", "scenic"], ["family_friendly", "photography", "day_trip"], "A distinctive cool-climate botanic garden that adds floral and landscape variety to hill-country plans.", [BOTANIC_HAKGALA, BOTANIC_HOME, wiki("Hakgala_Botanical_Garden")]),
    a("Victoria Park, Nuwara Eliya", "Nuwara Eliya", 6.9684, 80.7695, 6, 1.0, "tier_3", ["family", "nature", "scenic"], ["family_friendly", "budget_friendly"], "A tidy urban park stop that works well for lighter family pacing in town.", [SLTDA_REGIONAL, wiki("Victoria_Park,_Nuwara_Eliya")]),
    a("Pedro Tea Estate", "Nuwara Eliya", 6.9736, 80.7800, 6, 1.5, "tier_3", ["cultural", "scenic"], ["day_trip", "photography"], "A convenient tea-factory visit for travelers wanting the production side of hill-country landscapes.", [SLTDA_REGIONAL, wiki("Pedro_Tea_Factory")]),
    a("Moon Plains", "Nuwara Eliya", 6.9491, 80.8152, 6, 1.5, "tier_3", ["scenic", "nature"], ["couples", "photography", "day_trip"], "A viewpoint-driven outing with wide highland panoramas on the edge of town.", [SLTDA_REGIONAL, wiki("Moon_Plains")]),
    a("Lover's Leap Waterfall", "Nuwara Eliya", 6.9814, 80.7716, 6, 1.0, "tier_3", ["waterfall", "nature", "scenic"], ["photography", "day_trip"], "A classic Nuwara Eliya waterfall stop that layers well with tea-estate and town routes.", [SLTDA_REGIONAL, wiki("Lover%27s_Leap_Falls")]),
    a("Single Tree Hill", "Nuwara Eliya", 6.9602, 80.7794, 6, 1.5, "tier_3", ["scenic", "adventure", "nature"], ["photography", "day_trip"], "An accessible town-adjacent viewpoint that helps add sunrise or sunset structure to a hill-country stay.", [SLTDA_REGIONAL, wiki("Single_Tree_Hill")]),
    a("Seetha Amman Temple", "Nuwara Eliya", 6.9371, 80.7907, 7, 1.0, "tier_2", ["religious", "cultural", "scenic"], ["iconic", "day_trip", "photography"], "A well-known Ramayana-linked temple that is widely included in mainstream Nuwara Eliya sightseeing.", [SLTDA_REGIONAL, wiki("Seetha_Amman_Temple")]),
    a("Ramboda Falls", "Nuwara Eliya", 7.0562, 80.6993, 7, 1.0, "tier_2", ["waterfall", "nature", "scenic"], ["photography", "day_trip"], "One of the hill country's most popular roadside waterfall stops on the Kandy-Nuwara Eliya route.", [SLTDA_REGIONAL, wiki("Ramboda_Falls")]),
    a("Galway's Land National Park", "Nuwara Eliya", 6.9514, 80.7748, 6, 1.5, "tier_3", ["nature", "wildlife", "family"], ["family_friendly", "day_trip", "photography"], "A compact town-adjacent birding and nature walk option that improves short-stay itinerary flexibility.", [DWC_PROTECTED, wiki("Galway%27s_Land_National_Park")]),
    a("Bomburu Ella", "Nuwara Eliya", 6.8757, 80.8045, 7, 2.5, "tier_2", ["waterfall", "nature", "adventure", "scenic"], ["hidden_gem", "photography", "day_trip"], "A more rewarding waterfall excursion for travelers who want a stronger nature outing beyond town stops.", [SLTDA_REGIONAL, wiki("Bomburu_Ella")]),
    a("Devon Falls", "Nuwara Eliya", 6.8971, 80.6225, 6, 0.75, "tier_3", ["waterfall", "nature", "scenic"], ["photography", "day_trip"], "A classic tea-country viewpoint waterfall that helps enrich the western approach to Nuwara Eliya.", [SLTDA_REGIONAL, wiki("Devon_Falls")]),

    # Polonnaruwa
    a("Ancient City of Polonnaruwa", "Polonnaruwa", 7.9403, 81.0188, 10, 5.0, "tier_1", ["historic", "cultural", "religious"], ["unesco", "must_see", "iconic", "photography"], "A monumental medieval capital best explored as a large archaeological circuit.", [UNESCO_POLONNARUWA, wiki("Polonnaruwa")]),
    a("Minneriya National Park", "Polonnaruwa", 8.0350, 80.8877, 8, 4.0, "tier_2", ["wildlife", "nature", "adventure"], ["must_see", "photography", "day_trip"], "A major safari park, especially noted for seasonal elephant gatherings.", [DWC_PROTECTED, SLTDA_ATTRACTIONS, wiki("Minneriya_National_Park")]),
    a("Gal Vihara", "Polonnaruwa", 7.9667, 81.0096, 8, 1.0, "tier_2", ["historic", "religious", "cultural"], ["must_see", "photography", "day_trip"], "The district's standout sculptural site and one of Sri Lanka's greatest stone-carving ensembles.", [UNESCO_POLONNARUWA, wiki("Gal_Vihara")]),
    a("Parakrama Samudra", "Polonnaruwa", 7.9195, 81.0002, 6, 1.0, "tier_3", ["scenic", "historic"], ["day_trip", "photography"], "A massive ancient reservoir that gives cultural itineraries landscape scale and sunset potential.", [UNESCO_POLONNARUWA, wiki("Parakrama_Samudra")]),
    a("Medirigiriya Vatadage", "Polonnaruwa", 7.8020, 80.9918, 7, 1.0, "tier_2", ["historic", "religious", "cultural"], ["hidden_gem", "day_trip", "photography"], "A fine circular shrine ruin that adds variety beyond the main Polonnaruwa city core.", [SLTDA_REGIONAL, wiki("Medirigiriya_Vatadage")]),
    a("Kaudulla National Park", "Polonnaruwa", 8.1231, 80.8829, 7, 4.0, "tier_2", ["wildlife", "nature", "adventure"], ["day_trip", "photography"], "A strong supporting safari option in the same regional wildlife cluster as Minneriya.", [DWC_PROTECTED, wiki("Kaudulla_National_Park")]),

    # Puttalam
    a("Kalpitiya", "Puttalam", 8.2337, 79.7667, 8, 6.0, "tier_2", ["beach", "adventure", "wildlife", "scenic"], ["must_see", "couples", "photography", "day_trip"], "A leading base for kite surfing, dolphin trips, and lagoon-to-sea coastal experiences.", [SLTDA_ATTRACTIONS, DWC_MARINE, wiki("Kalpitiya")]),
    a("Wilpattu National Park", "Puttalam", 8.4490, 79.9950, 9, 5.0, "tier_1", ["wildlife", "nature", "adventure"], ["must_see", "iconic", "photography", "day_trip"], "Sri Lanka's largest national park, valued for its villu wetlands and lower-density safari feel.", [DWC_WILPATTU, wiki("Wilpattu_National_Park")]),
    a("Munneswaram Temple", "Puttalam", 7.5757, 79.7950, 7, 1.5, "tier_2", ["religious", "historic", "cultural"], ["iconic", "day_trip"], "A major Hindu temple complex that gives Puttalam district a strong heritage stop beyond the coast.", [SLTDA_REGIONAL, wiki("Munneswaram_temple")]),
    a("Anawilundawa Bird Sanctuary", "Puttalam", 7.6939, 79.8075, 6, 2.5, "tier_3", ["wildlife", "nature", "scenic"], ["hidden_gem", "photography", "day_trip"], "A Ramsar wetland and birding area suitable for slower west-coast nature itineraries.", [DWC_PROTECTED, wiki("Anawilundawa_Bird_Sanctuary")]),
    a("Dutch Fort of Kalpitiya", "Puttalam", 8.2325, 79.7662, 6, 0.75, "tier_3", ["historic", "cultural"], ["day_trip", "budget_friendly"], "A short colonial add-on in Kalpitiya town that improves local sightseeing variety.", [SLTDA_REGIONAL, wiki("Kalpitiya_Fort")]),
    a("Bar Reef Marine Sanctuary", "Puttalam", 8.2787, 79.7250, 6, 3.5, "tier_3", ["nature", "adventure", "wildlife", "beach"], ["photography", "day_trip"], "A reef-focused excursion area for snorkeling and marine scenery off the Kalpitiya coast.", [DWC_MARINE, wiki("Bar_Reef")]),

    # Ratnapura
    a("Adam's Peak (Sri Pada)", "Ratnapura", 6.8095, 80.4999, 10, 7.0, "tier_1", ["religious", "nature", "scenic", "adventure"], ["must_see", "iconic", "photography", "day_trip"], "A major pilgrimage mountain and one of Sri Lanka's most memorable summit experiences.", [SLTDA_ATTRACTIONS, wiki("Adam%27s_Peak")]),
    a("Sinharaja Forest Reserve", "Ratnapura", 6.4000, 80.5700, 9, 5.0, "tier_1", ["nature", "wildlife", "adventure"], ["unesco", "must_see", "hidden_gem", "photography"], "Sri Lanka's best-known lowland rainforest for biodiversity-focused trekking and birding.", [UNESCO_SINHARAJA, wiki("Sinharaja_Forest_Reserve")]),
    a("Udawalawe National Park", "Ratnapura", 6.4744, 80.8987, 8, 4.5, "tier_2", ["wildlife", "nature", "adventure"], ["must_see", "photography", "day_trip"], "A premier elephant-focused safari park commonly paired with south and hill-country routes.", [DWC_PROTECTED, wiki("Udawalawe_National_Park")]),
    a("Bopath Ella Falls", "Ratnapura", 6.8002, 80.3662, 6, 1.5, "tier_3", ["waterfall", "nature", "family"], ["family_friendly", "day_trip", "photography"], "A popular local waterfall that adds a softer nature stop to Ratnapura itineraries.", [SLTDA_REGIONAL, wiki("Bopath_Ella_Falls")]),
    a("Ratnapura National Museum", "Ratnapura", 6.6809, 80.4031, 5, 1.0, "tier_3", ["museum", "historic", "cultural"], ["day_trip", "budget_friendly"], "A useful museum stop for travelers wanting gem-country and regional history context.", [MUSEUM_LIST, wiki("National_Museum,_Ratnapura")]),

    # Trincomalee
    a("Koneswaram Temple", "Trincomalee", 8.5711, 81.2335, 8, 1.5, "tier_2", ["religious", "historic", "scenic"], ["iconic", "photography", "day_trip"], "A dramatic clifftop Hindu temple above Trincomalee harbour with strong scenic appeal.", [SLTDA_ATTRACTIONS, wiki("Koneswaram_Temple")]),
    a("Pigeon Island National Park", "Trincomalee", 8.6958, 81.2040, 8, 4.0, "tier_2", ["nature", "beach", "adventure", "wildlife"], ["must_see", "family_friendly", "couples", "photography"], "One of Sri Lanka's signature reef-snorkeling day trips, usually paired with Nilaveli.", [DWC_MARINE, wiki("Pigeon_Island_National_Park")]),
    a("Nilaveli Beach", "Trincomalee", 8.7000, 81.2000, 8, 4.0, "tier_2", ["beach", "family", "scenic"], ["must_see", "couples", "family_friendly", "photography"], "A broad east-coast beach with clear water and strong appeal as a Trincomalee base.", [SLTDA_ATTRACTIONS, wiki("Nilaveli")]),
    a("Fort Frederick", "Trincomalee", 8.5721, 81.2321, 7, 1.0, "tier_2", ["historic", "cultural", "scenic"], ["day_trip", "photography"], "A fort precinct that supports combined visits with Koneswaram and harbour viewpoints.", [SLTDA_REGIONAL, wiki("Fort_Frederick,_Trincomalee")]),
    a("Marble Beach", "Trincomalee", 8.5591, 81.2323, 6, 2.5, "tier_3", ["beach", "scenic"], ["couples", "photography", "day_trip"], "A smaller scenic beach option useful for travelers already exploring the fort peninsula.", [SLTDA_REGIONAL, wiki("Marble_Beach,_Sri_Lanka")]),
    a("Kanniya Hot Springs", "Trincomalee", 8.6062, 81.1752, 6, 0.75, "tier_3", ["historic", "cultural", "family"], ["day_trip", "budget_friendly"], "A quick stop with legend and local interest near Trincomalee town.", [SLTDA_REGIONAL, wiki("Kanniya_hot_springs")]),
    a("Thiriyai Girihandu Seya", "Trincomalee", 8.7891, 81.1896, 6, 1.5, "tier_3", ["religious", "historic", "cultural"], ["hidden_gem", "day_trip"], "A quieter Buddhist heritage site suited to longer east-coast cultural circuits.", [SLTDA_REGIONAL, wiki("Girihandu_Seya")]),

    # Vavuniya
    a("Madukanda Vihara", "Vavuniya", 8.8532, 80.5030, 4, 1.0, "tier_3", ["religious", "historic", "cultural"], ["day_trip", "budget_friendly"], "A modest but historically known temple stop on the north-central route.", [SLTDA_REGIONAL, wiki("Vavuniya")]),
    a("Vavuniya Archaeological Museum", "Vavuniya", 8.7513, 80.4971, 4, 1.0, "tier_3", ["museum", "historic", "cultural"], ["day_trip", "budget_friendly"], "Included conservatively as a useful local history stop for northbound overland travelers.", [MUSEUM_LIST, wiki("Vavuniya")]),
]

EXTRA_ATTRACTIONS = [
    # Ampara
    a("Whiskey Point", "Ampara", 6.8530, 81.8304, 7, 3.0, "tier_2", ["beach", "adventure", "scenic"], ["must_see", "photography", "day_trip"], "A surf-friendly east-coast point break that adds another serious beach option near Arugam Bay.", [SLTDA_REGIONAL, wiki("Whisky_Point,_Pottuvil")]),
    a("Panama Beach", "Ampara", 6.7837, 81.8222, 6, 2.5, "tier_3", ["beach", "scenic"], ["hidden_gem", "photography", "day_trip"], "A quieter southern stretch of coast useful for travelers exploring beyond the main Arugam Bay strip.", [SLTDA_REGIONAL, wiki("Panama,_Sri_Lanka")]),
    a("Kudumbigala Monastery", "Ampara", 6.6790, 81.6950, 6, 2.0, "tier_3", ["historic", "religious", "adventure"], ["hidden_gem", "photography", "day_trip"], "An ancient forest monastery site that adds archaeological depth to Ampara's safari-and-beach mix.", [SLTDA_REGIONAL, wiki("Kudumbigala_Monastery")]),
    a("Gal Oya National Park", "Ampara", 7.2288, 81.5504, 8, 4.5, "tier_2", ["wildlife", "nature", "adventure"], ["must_see", "photography", "day_trip"], "A distinctive reservoir-based safari region known for boat trips and less crowded wildlife experiences.", [DWC_PROTECTED, wiki("Gal_Oya_National_Park")]),

    # Anuradhapura
    a("Thuparamaya", "Anuradhapura", 8.3518, 80.3947, 8, 1.0, "tier_2", ["religious", "historic", "cultural"], ["must_see", "photography", "day_trip"], "Anuradhapura's oldest dagoba is a meaningful stop within the sacred city's monument circuit.", [UNESCO_ANURADHAPURA, wiki("Thuparamaya")]),
    a("Abhayagiri Vihara", "Anuradhapura", 8.3690, 80.3958, 8, 1.5, "tier_2", ["historic", "religious", "cultural"], ["must_see", "photography", "day_trip"], "A major monastery complex that broadens the archaeological range of Anuradhapura itineraries.", [UNESCO_ANURADHAPURA, wiki("Abhayagiri_Vihara")]),
    a("Samadhi Buddha Statue", "Anuradhapura", 8.3697, 80.3950, 7, 0.75, "tier_3", ["historic", "religious", "cultural"], ["day_trip", "photography"], "One of Sri Lanka's most revered Buddha images and a rewarding short stop near Abhayagiri.", [UNESCO_ANURADHAPURA, wiki("Samadhi_Statue")]),
    a("Lovamahapaya", "Anuradhapura", 8.3450, 80.3954, 7, 0.75, "tier_3", ["historic", "cultural"], ["day_trip", "photography"], "The Brazen Palace ruins add scale and context to the core sacred-city walking loop.", [UNESCO_ANURADHAPURA, wiki("Lovamahapaya")]),
    a("Mirisawetiya", "Anuradhapura", 8.3456, 80.3876, 7, 0.75, "tier_3", ["religious", "historic", "cultural"], ["day_trip", "photography"], "A long-standing stupa stop that helps create a fuller monument circuit around the ancient city.", [UNESCO_ANURADHAPURA, wiki("Mirisawetiya")]),
    a("Kuttam Pokuna", "Anuradhapura", 8.3748, 80.4006, 7, 0.75, "tier_3", ["historic", "cultural"], ["day_trip", "photography"], "The twin ponds are among the most elegant pieces of ancient hydraulic architecture in Anuradhapura.", [UNESCO_ANURADHAPURA, wiki("Kuttam_Pokuna")]),
    a("Ritigala", "Anuradhapura", 8.1399, 80.6648, 8, 2.5, "tier_2", ["nature", "historic", "adventure"], ["hidden_gem", "photography", "day_trip"], "A forested mountain monastery site that adds a very different atmosphere from the main city ruins.", [SLTDA_REGIONAL, wiki("Ritigala")]),
    a("Aukana Buddha Statue", "Anuradhapura", 8.0554, 80.5273, 8, 1.5, "tier_2", ["religious", "historic", "cultural"], ["must_see", "photography", "day_trip"], "A towering ancient Buddha image that remains one of the strongest outlying heritage stops in the district.", [SLTDA_REGIONAL, wiki("Aukana_Buddha_statue")]),

    # Badulla
    a("Ella Gap", "Badulla", 6.8660, 81.0460, 7, 0.75, "tier_3", ["scenic", "nature"], ["photography", "day_trip"], "The famous southern panorama is a practical scenic stop even on short Ella itineraries.", [SLTDA_REGIONAL, wiki("Ella")]),
    a("Ravana Cave", "Badulla", 6.8409, 81.0643, 6, 1.0, "tier_3", ["historic", "adventure", "scenic"], ["day_trip", "photography"], "A myth-linked cave stop that pairs naturally with Ravana Falls on Ella side trips.", [SLTDA_REGIONAL, wiki("Ravana_Cave")]),
    a("Dowa Rock Temple", "Badulla", 6.8977, 81.0540, 6, 1.0, "tier_3", ["religious", "historic", "cultural"], ["day_trip", "photography"], "An easy roadside temple stop known for its rock-cut Buddha image and cave murals.", [SLTDA_REGIONAL, wiki("Dowa_Rock_Temple")]),
    a("Dunhinda Falls", "Badulla", 6.9225, 81.0570, 7, 2.0, "tier_2", ["waterfall", "nature", "scenic"], ["must_see", "photography", "day_trip"], "One of the island's best-known waterfalls and a stronger Badulla-town nature outing.", [SLTDA_REGIONAL, wiki("Dunhinda_Falls")]),
    a("Bambarakanda Falls", "Badulla", 6.7731, 80.8306, 8, 2.5, "tier_2", ["waterfall", "nature", "scenic"], ["must_see", "photography", "day_trip"], "Sri Lanka's tallest waterfall is a high-value addition for southern hill-country route planning.", [SLTDA_REGIONAL, wiki("Bambarakanda_Falls")]),
    a("Bogoda Wooden Bridge", "Badulla", 6.8950, 80.9210, 6, 1.0, "tier_3", ["historic", "cultural", "scenic"], ["hidden_gem", "photography", "day_trip"], "A rare wooden bridge-and-temple combination that adds heritage texture beyond Ella proper.", [SLTDA_REGIONAL, wiki("Bogoda_Wooden_Bridge")]),
    a("Halpewatte Tea Factory", "Badulla", 6.8721, 81.0398, 6, 1.5, "tier_3", ["cultural", "scenic"], ["day_trip", "photography"], "A tea-experience stop that helps diversify Ella stays beyond viewpoints and hikes.", [SLTDA_REGIONAL, wiki("Uva_Halpewatte_Tea_Factory")]),
    a("Madulsima Mini World's End", "Badulla", 6.7892, 81.0860, 7, 2.5, "tier_2", ["scenic", "nature", "adventure"], ["hidden_gem", "photography", "day_trip"], "A dramatic escarpment viewpoint that gives the district another serious landscape stop beyond Ella.", [SLTDA_REGIONAL, wiki("Madulsima")]),
    a("Namunukula Mountain Range", "Badulla", 6.8728, 81.1221, 6, 3.0, "tier_3", ["nature", "scenic", "adventure"], ["photography", "day_trip"], "A broad upland landscape area suited to more outdoors-focused Badulla itineraries.", [SLTDA_REGIONAL, wiki("Namunukula")]),
    a("Thangamale Sanctuary", "Badulla", 6.7741, 80.9827, 6, 2.0, "tier_3", ["nature", "wildlife", "scenic"], ["hidden_gem", "photography", "day_trip"], "A cool-climate birding and forest stop near Haputale that complements the viewpoint circuit.", [DWC_PROTECTED, wiki("Thangamale_Sanctuary")]),

    # Colombo
    a("Beira Lake", "Colombo", 6.9279, 79.8546, 7, 1.0, "tier_2", ["scenic", "cultural", "family"], ["day_trip", "photography", "couples"], "A central urban lake that supports easy city itineraries around Gangaramaya and nearby civic landmarks.", [SLTDA_REGIONAL, wiki("Beira_Lake")]),
    a("Seema Malaka", "Colombo", 6.9162, 79.8561, 7, 0.75, "tier_2", ["religious", "scenic", "cultural"], ["photography", "day_trip", "couples"], "The lakeside meditation temple is one of Colombo's most graceful short stops.", [GANGARAMAYA_HOME, wiki("Seema_Malaka")]),
    a("Lotus Tower", "Colombo", 6.9275, 79.8588, 7, 1.5, "tier_2", ["scenic", "family"], ["iconic", "photography", "day_trip"], "Colombo's modern skyline landmark gives the city stronger contemporary-viewpoint coverage.", [SLTDA_REGIONAL, wiki("Lotus_Tower")]),
    a("Old Dutch Hospital", "Colombo", 6.9358, 79.8416, 6, 1.0, "tier_3", ["historic", "cultural"], ["day_trip", "photography"], "A restored colonial complex that works well on compact Fort-area walking routes.", [SLTDA_REGIONAL, wiki("Old_Dutch_Hospital,_Colombo")]),
    a("Pettah Market", "Colombo", 6.9394, 79.8527, 6, 1.0, "tier_3", ["cultural", "family"], ["budget_friendly", "photography", "day_trip"], "A dense market district that adds urban texture and everyday life to heritage-led Colombo routes.", [SLTDA_REGIONAL, wiki("Pettah,_Sri_Lanka")]),
    a("Sambodhi Chaithya", "Colombo", 6.9441, 79.8437, 6, 0.75, "tier_3", ["religious", "scenic"], ["photography", "day_trip"], "The harbor-edge stupa is a visually distinctive stop near central Colombo's seafront.", [SLTDA_REGIONAL, wiki("Sambodhi_Chaithya")]),
    a("Geoffrey Bawa's Number 11", "Colombo", 6.9128, 79.8652, 7, 1.0, "tier_2", ["museum", "cultural", "historic"], ["day_trip", "couples"], "The architect's former home is a high-value design and architecture stop in Colombo.", [SLTDA_REGIONAL, wiki("Geoffrey_Bawa%27s_home_Number_11")]),
    a("Bellanwila Rajamaha Viharaya", "Colombo", 6.8478, 79.8845, 6, 1.0, "tier_3", ["religious", "cultural"], ["day_trip", "photography"], "A substantial temple stop in the Colombo urban area that can support culture-heavy city days.", [SLTDA_REGIONAL, wiki("Bellanwila_Raja_Maha_Viharaya")]),
    a("National Art Gallery", "Colombo", 6.9109, 79.8620, 6, 1.0, "tier_3", ["museum", "cultural"], ["day_trip", "family_friendly"], "A useful fine-arts stop near the museum cluster that improves Colombo's cultural breadth.", [MUSEUM_LIST, wiki("National_Art_Gallery_(Sri_Lanka)")]),

    # Galle
    a("Ahangama Beach", "Galle", 5.9735, 80.3613, 6, 3.0, "tier_3", ["beach", "adventure", "scenic"], ["couples", "photography", "day_trip"], "A surf-oriented south-coast beach that expands options east of the fort and Unawatuna zone.", [SLTDA_REGIONAL, wiki("Ahangama")]),
    a("Wijaya Beach", "Galle", 6.0065, 80.2536, 6, 2.0, "tier_3", ["beach", "family", "scenic"], ["family_friendly", "couples", "photography"], "A smaller beach stop valued for easier swimming and a calmer setting near Unawatuna.", [SLTDA_REGIONAL, wiki("Wijaya_Beach")]),
    a("Koggala Lake", "Galle", 5.9957, 80.3377, 6, 2.0, "tier_3", ["nature", "scenic", "family"], ["couples", "photography", "day_trip"], "A lagoon-and-islands outing that adds inland water scenery to coastal Galle itineraries.", [SLTDA_REGIONAL, wiki("Koggala_Lake")]),
    a("Handunugoda Tea Estate", "Galle", 6.0382, 80.3790, 6, 1.5, "tier_3", ["cultural", "scenic"], ["day_trip", "couples"], "A worthwhile tea stop that broadens the district beyond beaches and fort heritage.", [SLTDA_REGIONAL, wiki("Handunugoda_Tea_Estate")]),
    a("Ariyapala Mask Museum", "Galle", 6.2357, 80.0520, 6, 1.0, "tier_3", ["museum", "cultural", "family"], ["family_friendly", "day_trip"], "A classic Ambalangoda stop that supports traditional arts coverage on the southwest corridor.", [MUSEUM_LIST, wiki("Ariyapala_Mask_Museum")]),
    a("Seenigama Devalaya", "Galle", 6.1417, 80.0992, 6, 0.75, "tier_3", ["religious", "scenic", "cultural"], ["photography", "day_trip"], "The offshore shrine is a memorable short stop near Hikkaduwa's main strip.", [SLTDA_REGIONAL, wiki("Seenigama_Muhudu_Viharaya")]),
    a("Madu Ganga", "Galle", 6.2568, 80.0356, 7, 2.5, "tier_2", ["nature", "scenic", "family"], ["must_see", "photography", "day_trip"], "A boat-friendly estuary ecosystem that significantly improves route options on the Galle-Kalutara corridor.", [SLTDA_REGIONAL, wiki("Madu_Ganga")]),
    a("Kosgoda Turtle Hatchery", "Galle", 6.3322, 80.0277, 6, 1.0, "tier_3", ["family", "nature"], ["family_friendly", "day_trip"], "A popular short educational stop on the southwest coast, especially for mixed-age itineraries.", [SLTDA_REGIONAL, wiki("Kosgoda")]),
    a("Balapitiya Beach", "Galle", 6.2726, 80.0340, 6, 2.0, "tier_3", ["beach", "scenic"], ["couples", "photography", "day_trip"], "A quieter southern beach stop that complements Madu Ganga and Ambalangoda-side sightseeing.", [SLTDA_REGIONAL, wiki("Balapitiya")]),
    a("Stilt Fishermen, Koggala", "Galle", 5.9940, 80.3284, 5, 0.5, "tier_3", ["cultural", "scenic"], ["photography", "day_trip"], "A classic south-coast image stop that still works as a short supporting attraction in the Koggala area.", [SLTDA_REGIONAL, wiki("Stilt_fishing")]),
    a("All Saints' Church, Galle", "Galle", 6.0273, 80.2170, 5, 0.5, "tier_3", ["historic", "religious", "cultural"], ["day_trip", "photography"], "A worthwhile small-scale heritage stop inside the fort area for travelers who enjoy layered walking routes.", [UNESCO_GALLE, wiki("All_Saints%27_Church,_Galle")]),

    # Hambantota
    a("Ussangoda National Park", "Hambantota", 6.0773, 80.9312, 7, 1.5, "tier_2", ["nature", "scenic"], ["hidden_gem", "photography", "day_trip"], "A striking coastal plateau and protected area that adds geological variety to the south-coast route.", [DWC_PROTECTED, wiki("Ussangoda_National_Park")]),
    a("Kalametiya Bird Sanctuary", "Hambantota", 6.0795, 80.9181, 6, 2.0, "tier_3", ["wildlife", "nature", "scenic"], ["photography", "day_trip"], "A calmer birding and lagoon stop that suits wildlife-oriented itineraries near Tangalle.", [DWC_PROTECTED, wiki("Kalametiya_Bird_Sanctuary")]),
    a("Kirinda Temple", "Hambantota", 6.2212, 81.3381, 6, 1.0, "tier_3", ["religious", "scenic", "historic"], ["photography", "day_trip"], "A cliffside temple stop that combines seascapes with local legend and pilgrimage value.", [SLTDA_REGIONAL, wiki("Kirinda_Temple")]),
    a("Kirinda Beach", "Hambantota", 6.2233, 81.3375, 6, 2.0, "tier_3", ["beach", "scenic"], ["photography", "day_trip"], "A scenic beach detour that works well with Kirinda temple and Yala-side routing.", [SLTDA_REGIONAL, wiki("Kirinda")]),
    a("Wewurukannala Temple", "Hambantota", 6.0047, 80.6990, 6, 1.5, "tier_3", ["religious", "cultural"], ["photography", "day_trip"], "A visually distinctive temple complex with strong roadside appeal on southern itineraries.", [SLTDA_REGIONAL, wiki("Wewurukannala_Vihara")]),
    a("Yatala Vehera", "Hambantota", 6.1245, 81.1238, 6, 1.0, "tier_3", ["religious", "historic", "cultural"], ["day_trip", "photography"], "An old stupa site that gives the district more archaeological depth beyond safari travel.", [SLTDA_REGIONAL, wiki("Yatala_Vehera")]),
    a("Tangalle Lagoon", "Hambantota", 6.0260, 80.8045, 6, 1.5, "tier_3", ["nature", "scenic"], ["couples", "photography", "day_trip"], "A soft-adventure and birdlife add-on that helps make Tangalle stays more varied.", [SLTDA_REGIONAL, wiki("Tangalle")]),
    a("Bundala Lagoons", "Hambantota", 6.1878, 81.2109, 6, 1.5, "tier_3", ["wildlife", "scenic", "nature"], ["photography", "day_trip"], "Useful as a supporting wetland stop around Bundala-focused wildlife itineraries.", [DWC_PROTECTED, wiki("Bundala_National_Park")]),

    # Jaffna
    a("Keerimalai Springs", "Jaffna", 9.8221, 79.9645, 6, 0.75, "tier_3", ["scenic", "cultural"], ["photography", "day_trip"], "The famous mineral spring site strengthens the north coast's visitor circuit around Keerimalai.", [SLTDA_REGIONAL, wiki("Keerimalai")]),
    a("Fort Hammenhiel", "Jaffna", 9.7198, 79.8792, 6, 1.0, "tier_3", ["historic", "scenic"], ["photography", "day_trip"], "A compact island fort that adds a different colonial stop to Jaffna day trips.", [SLTDA_REGIONAL, wiki("Fort_Hammenhiel")]),
    a("Nilavarai Bottomless Well", "Jaffna", 9.7340, 80.0471, 5, 0.5, "tier_3", ["scenic", "cultural"], ["day_trip", "budget_friendly"], "A short curiosity stop that can fit naturally into Jaffna peninsula loops.", [SLTDA_REGIONAL, wiki("Nilavarai")]),
    a("Kadurugoda Vihara", "Jaffna", 9.7572, 80.0370, 6, 0.75, "tier_3", ["historic", "religious", "cultural"], ["day_trip", "hidden_gem"], "The small ancient stupa field adds archaeological variety to northern cultural routes.", [SLTDA_REGIONAL, wiki("Kandarodai")]),
    a("Point Pedro", "Jaffna", 9.8167, 80.2333, 6, 1.0, "tier_3", ["scenic", "cultural"], ["photography", "day_trip"], "Sri Lanka's northern tip adds geographic character and broadens peninsula day-trip options.", [SLTDA_REGIONAL, wiki("Point_Pedro")]),
    a("Point Pedro Lighthouse", "Jaffna", 9.8225, 80.2474, 5, 0.5, "tier_3", ["scenic", "historic"], ["photography", "day_trip"], "A quick coastal landmark stop that works well alongside Point Pedro and surrounding beaches.", [SLTDA_REGIONAL, wiki("Point_Pedro_Lighthouse")]),
    a("Maviddapuram Kandaswamy Temple", "Jaffna", 9.7906, 79.9637, 6, 1.0, "tier_3", ["religious", "cultural", "historic"], ["day_trip", "photography"], "A notable northern temple that gives the district more depth beyond Nallur and Nagadeepa.", [SLTDA_REGIONAL, wiki("Maviddapuram_Kandaswamy_Temple")]),
    a("Manalkadu Sand Dunes", "Jaffna", 9.8460, 80.1420, 6, 1.5, "tier_3", ["scenic", "nature"], ["hidden_gem", "photography", "day_trip"], "A less-urban landscape stop that adds dunes and open coast to Jaffna peninsula itineraries.", [SLTDA_REGIONAL, wiki("Vadamarachchi_East")]),

    # Kalutara
    a("Lunuganga", "Kalutara", 6.4360, 80.0147, 7, 1.5, "tier_2", ["cultural", "scenic", "family"], ["couples", "photography", "day_trip"], "Geoffrey Bawa's garden estate is one of the strongest supporting cultural stops on the southwest corridor.", [SLTDA_REGIONAL, wiki("Lunuganga")]),
    a("Bentota River", "Kalutara", 6.4255, 79.9969, 7, 2.0, "tier_2", ["nature", "adventure", "scenic"], ["must_see", "photography", "day_trip"], "River safaris and mangrove scenery make this a valuable alternative to pure beach time.", [SLTDA_REGIONAL, wiki("Bentota_River")]),
    a("Moragalla Beach", "Kalutara", 6.4728, 79.9798, 6, 2.0, "tier_3", ["beach", "scenic", "family"], ["family_friendly", "day_trip"], "A calmer beach option near Beruwala that helps diversify short southwest coastal stays.", [SLTDA_REGIONAL, wiki("Moragalla")]),
    a("Kande Viharaya", "Kalutara", 6.4811, 79.9836, 7, 1.0, "tier_2", ["religious", "cultural"], ["iconic", "day_trip", "photography"], "A popular Buddhist temple known for its giant seated Buddha image and easy roadside access.", [SLTDA_REGIONAL, wiki("Kande_Viharaya")]),
    a("Kosgoda Beach", "Kalutara", 6.3390, 80.0302, 6, 2.0, "tier_3", ["beach", "scenic"], ["couples", "photography", "day_trip"], "A quieter coastal stretch that works well for low-key west-to-south corridor itineraries.", [SLTDA_REGIONAL, wiki("Kosgoda")]),
    a("Barberyn Lighthouse", "Kalutara", 6.4722, 79.9768, 6, 0.75, "tier_3", ["historic", "scenic"], ["photography", "day_trip"], "A seafront lighthouse landmark that adds visual variety to Beruwala-side routes.", [SLTDA_REGIONAL, wiki("Beruwala_Lighthouse")]),
    a("Ketchimalai Mosque", "Kalutara", 6.4746, 79.9806, 6, 0.75, "tier_3", ["religious", "historic", "cultural"], ["day_trip", "photography"], "A meaningful multi-faith coastal heritage stop within the Beruwala area.", [SLTDA_REGIONAL, wiki("Kechimalai_Mosque")]),

    # Kandy
    a("Asgiriya Maha Vihara", "Kandy", 7.3001, 80.6358, 6, 0.75, "tier_3", ["religious", "historic", "cultural"], ["day_trip", "photography"], "An old monastic institution that adds more texture to Kandy's sacred-city circuit.", [SLTDA_REGIONAL, wiki("Asgiriya_Maha_Vihara")]),
    a("Natha Devale", "Kandy", 7.2930, 80.6420, 7, 0.5, "tier_3", ["religious", "historic", "cultural"], ["day_trip", "photography"], "The oldest surviving building in Kandy's sacred core is a meaningful short supporting stop.", [UNESCO_KANDY, wiki("Natha_Devale")]),
    a("International Buddhist Museum", "Kandy", 7.2932, 80.6417, 6, 1.0, "tier_3", ["museum", "religious", "cultural"], ["day_trip", "family_friendly"], "A practical museum add-on inside the palace complex that rounds out central Kandy visits.", [MUSEUM_LIST, wiki("International_Buddhist_Museum")]),
    a("Wales Park", "Kandy", 7.2902, 80.6416, 6, 0.75, "tier_3", ["scenic", "family"], ["budget_friendly", "photography", "day_trip"], "A simple elevated park stop that works well for quick city views and pacing between monuments.", [SLTDA_REGIONAL, wiki("Wales_Park,_Kandy")]),
    a("Kandy Garrison Cemetery", "Kandy", 7.2928, 80.6414, 6, 0.75, "tier_3", ["historic", "cultural"], ["day_trip", "photography"], "A compact colonial cemetery that helps broaden Kandy's heritage offering beyond temples.", [SLTDA_REGIONAL, wiki("Kandy_Garrison_Cemetery")]),
    a("Ambuluwawa Tower", "Kandy", 7.1630, 80.5690, 7, 2.0, "tier_2", ["scenic", "adventure", "family"], ["must_see", "photography", "day_trip"], "A high-value viewpoint tower excursion that adds a more adventurous panoramic option near Kandy.", [SLTDA_REGIONAL, wiki("Ambuluwawa_Tower")]),
    a("Ranawana Purana Rajamaha Viharaya", "Kandy", 7.3138, 80.5821, 6, 1.0, "tier_3", ["religious", "cultural"], ["day_trip", "photography"], "A visually distinctive temple complex that works well on Peradeniya-side routes.", [SLTDA_REGIONAL, wiki("Ranawana_Purana_Rajamaha_Viharaya")]),
    a("Hantana Mountain Range", "Kandy", 7.2530, 80.6289, 7, 3.5, "tier_2", ["nature", "scenic", "adventure"], ["photography", "day_trip"], "A serious viewpoint and hiking area that gives Kandy better outdoor depth.", [SLTDA_REGIONAL, wiki("Hanthana_Mountain_Range")]),
    a("Ceylon Tea Museum Viewpoint", "Kandy", 7.2689, 80.6333, 5, 0.5, "tier_3", ["scenic", "cultural"], ["photography", "day_trip"], "Useful as a compact supporting stop alongside the tea museum and Hantana side of the city.", [SLTDA_REGIONAL, wiki("Ceylon_Tea_Museum")]),
    a("Commonwealth War Cemetery, Kandy", "Kandy", 7.2960, 80.6035, 5, 0.5, "tier_3", ["historic", "cultural"], ["day_trip"], "A quiet but meaningful heritage stop that complements Kandy's colonial-era historical layer.", [SLTDA_REGIONAL, wiki("Kandy_War_Cemetery")]),

    # Kurunegala
    a("Arankele Monastery", "Kurunegala", 7.8307, 80.3027, 7, 2.0, "tier_2", ["historic", "religious", "nature"], ["hidden_gem", "photography", "day_trip"], "A forest monastery ruin complex that meaningfully upgrades Kurunegala for heritage travelers.", [SLTDA_REGIONAL, wiki("Arankele")]),
    a("Haththikuchchi", "Kurunegala", 7.7096, 80.1241, 6, 1.5, "tier_3", ["historic", "religious", "cultural"], ["hidden_gem", "day_trip"], "An under-visited archaeological site that adds real substance to inland route planning.", [SLTDA_REGIONAL, wiki("Haththikuchchi")]),
    a("Yapahuwa Museum", "Kurunegala", 7.8226, 80.3026, 5, 0.75, "tier_3", ["museum", "historic", "cultural"], ["day_trip"], "A useful add-on for visitors already spending time at the Yapahuwa rock fortress complex.", [MUSEUM_LIST, wiki("Yapahuwa")]),
    a("Dambadeniya Archaeological Site", "Kurunegala", 7.3700, 80.1704, 6, 1.5, "tier_3", ["historic", "cultural"], ["day_trip", "photography"], "The core ruins area gives Dambadeniya stronger standalone visitor value within the district.", [SLTDA_REGIONAL, wiki("Dambadeniya")]),
    a("Kurunegala Lake", "Kurunegala", 7.4898, 80.3640, 5, 0.75, "tier_3", ["scenic", "family"], ["budget_friendly", "day_trip"], "A low-effort town stop that helps shape shorter transit-day itineraries in Kurunegala.", [SLTDA_REGIONAL, wiki("Kurunegala")]),
    a("Athugala Viharaya", "Kurunegala", 7.4875, 80.3650, 6, 1.0, "tier_3", ["religious", "scenic"], ["photography", "day_trip"], "The hilltop temple area complements Athugala's viewpoint function and improves heritage-scene balance.", [SLTDA_REGIONAL, wiki("Athugala")]),

    # Matale
    a("Sigiriya Museum", "Matale", 7.9567, 80.7607, 7, 1.0, "tier_2", ["museum", "historic", "cultural"], ["day_trip", "family_friendly"], "A genuinely useful interpretive stop that enriches Sigiriya visits for itinerary planning.", [SLTDA_REGIONAL, wiki("Sigiriya")]),
    a("Cobra Hood Cave", "Matale", 7.9564, 80.7605, 6, 0.75, "tier_3", ["historic", "cultural"], ["day_trip", "photography"], "A small but worthwhile supporting stop within the broader Sigiriya archaeological landscape.", [UNESCO_SIGIRIYA, wiki("Sigiriya")]),
    a("Kaludiya Pokuna", "Matale", 7.8715, 80.6932, 6, 1.5, "tier_3", ["historic", "nature", "cultural"], ["hidden_gem", "day_trip"], "A quieter forest monastery site that adds variety around Dambulla and Kandalama routes.", [SLTDA_REGIONAL, wiki("Kaludiya_Pokuna")]),
    a("Popham's Arboretum", "Matale", 7.5110, 80.6065, 6, 1.5, "tier_3", ["nature", "family", "wildlife"], ["hidden_gem", "day_trip"], "A valuable biodiversity stop near Matale town with good family and birding appeal.", [SLTDA_REGIONAL, wiki("Popham%27s_Arboretum")]),
    a("Rose Quartz Mountain", "Matale", 7.4257, 80.6908, 6, 1.5, "tier_3", ["scenic", "nature"], ["photography", "day_trip"], "A lesser-known scenic stop that helps diversify Matale beyond the better-known UNESCO circuit.", [SLTDA_REGIONAL, wiki("Jathika_Namala_Uyana")]),
    a("Erawula Pottery Village", "Matale", 7.5653, 80.6393, 5, 1.0, "tier_3", ["cultural", "family"], ["day_trip", "budget_friendly"], "A useful crafts-and-living-culture stop for travelers who want more than ruins and viewpoints.", [SLTDA_REGIONAL, wiki("Matale")]),
    a("Golden Temple of Dambulla", "Matale", 7.8560, 80.6491, 6, 0.75, "tier_3", ["religious", "cultural"], ["photography", "day_trip"], "The entrance-side temple complex is a practical supporting stop alongside the cave temple visit.", [UNESCO_DAMBULLA, wiki("Dambulla_cave_temple")]),
    a("Boulder Gardens of Sigiriya", "Matale", 7.9571, 80.7601, 6, 0.75, "tier_3", ["historic", "scenic"], ["day_trip", "photography"], "A meaningful sub-attraction within the Sigiriya complex that helps fine-tune day planning.", [UNESCO_SIGIRIYA, wiki("Sigiriya")]),
    a("Kandalama Reservoir Viewpoint", "Matale", 7.8952, 80.7087, 5, 0.5, "tier_3", ["scenic", "nature"], ["photography", "day_trip"], "A practical scenic stop that works well between Dambulla, Kandalama, and Sigiriya routing.", [SLTDA_REGIONAL, wiki("Kandalama")]),

    # Matara
    a("Secret Beach, Mirissa", "Matara", 5.9446, 80.4588, 6, 2.0, "tier_3", ["beach", "scenic"], ["couples", "photography", "day_trip"], "A sheltered alternative beach that gives Mirissa stays more choice without adding noise.", [SLTDA_REGIONAL, wiki("Mirissa")]),
    a("Coconut Tree Hill", "Matara", 5.9488, 80.4666, 6, 0.75, "tier_3", ["scenic", "nature"], ["photography", "couples", "day_trip"], "One of the most popular sunrise and sunset viewpoints in the Mirissa area.", [SLTDA_REGIONAL, wiki("Mirissa")]),
    a("Madiha Beach", "Matara", 5.9403, 80.4997, 6, 2.0, "tier_3", ["beach", "scenic", "adventure"], ["couples", "photography", "day_trip"], "A surf-friendly and lower-key beach that widens Matara's coastal planning options.", [SLTDA_REGIONAL, wiki("Madiha")]),
    a("Paravi Duwa Temple", "Matara", 5.9489, 80.5480, 6, 0.75, "tier_3", ["religious", "scenic", "cultural"], ["photography", "day_trip"], "A small island temple linked by footbridge that adds charm to central Matara sightseeing.", [SLTDA_REGIONAL, wiki("Paravi_Duwa_Temple")]),
    a("Devinuwara Temple", "Matara", 5.9306, 80.5881, 6, 1.0, "tier_3", ["religious", "historic", "cultural"], ["day_trip", "photography"], "A long-standing pilgrimage site that pairs naturally with the Dondra headland area.", [SLTDA_REGIONAL, wiki("Dondra,_Sri_Lanka")]),
    a("Talalla Beach", "Matara", 5.9021, 80.4932, 7, 2.5, "tier_2", ["beach", "scenic"], ["couples", "photography", "day_trip"], "A broad and attractive southern beach that strengthens the district beyond Mirissa and Weligama.", [SLTDA_REGIONAL, wiki("Talalla")]),
    a("Hiriketiya Beach", "Matara", 5.9640, 80.6928, 7, 3.0, "tier_2", ["beach", "adventure", "scenic"], ["must_see", "couples", "photography"], "A highly popular bay for surf-and-cafe style stays that materially improves south-coast route options.", [SLTDA_REGIONAL, wiki("Hiriketiya")]),
    a("Dikwella Beach", "Matara", 5.9650, 80.6852, 6, 2.0, "tier_3", ["beach", "family", "scenic"], ["family_friendly", "day_trip"], "A calmer supporting beach near Hiriketiya that helps balance surfing and swimming options.", [SLTDA_REGIONAL, wiki("Dickwella")]),

    # Nuwara Eliya
    a("St Clair's Falls", "Nuwara Eliya", 6.9042, 80.5986, 7, 0.75, "tier_2", ["waterfall", "nature", "scenic"], ["photography", "day_trip"], "A famous tea-country waterfall viewpoint on the western approach to Nuwara Eliya.", [SLTDA_REGIONAL, wiki("St._Clair%27s_Falls")]),
    a("Pidurutalagala", "Nuwara Eliya", 6.9786, 80.7731, 7, 1.5, "tier_2", ["scenic", "nature", "adventure"], ["must_see", "photography", "day_trip"], "Sri Lanka's highest mountain adds a strong summit-style landscape stop to the district.", [SLTDA_REGIONAL, wiki("Pidurutalagala")]),
    a("Ambewela Farm", "Nuwara Eliya", 6.8784, 80.8001, 6, 1.0, "tier_3", ["family", "scenic"], ["family_friendly", "day_trip"], "A popular hill-country farm stop that fits well into softer family-oriented Nuwara Eliya days.", [SLTDA_REGIONAL, wiki("Ambewela_Farm")]),
    a("Damro Labookellie Tea Centre", "Nuwara Eliya", 7.0119, 80.7446, 6, 1.0, "tier_3", ["cultural", "scenic"], ["day_trip", "photography"], "A practical tea-estate stop on the Kandy-Nuwara Eliya corridor for scenic and production-focused visits.", [SLTDA_REGIONAL, wiki("Labookellie_Tea_Centre")]),
    a("Blue Field Tea Gardens", "Nuwara Eliya", 6.9396, 80.7899, 6, 1.0, "tier_3", ["cultural", "scenic"], ["day_trip", "photography"], "A town-adjacent tea stop that works well for shorter hill-country itineraries.", [SLTDA_REGIONAL, wiki("Bluefield_Tea_Gardens")]),
    a("Holy Trinity Church, Nuwara Eliya", "Nuwara Eliya", 6.9698, 80.7685, 6, 0.75, "tier_3", ["historic", "religious", "cultural"], ["day_trip", "photography"], "A compact colonial church stop that adds heritage texture to the Little England identity of town.", [SLTDA_REGIONAL, wiki("Holy_Trinity_Church,_Nuwara_Eliya")]),
    a("Blackpool Falls", "Nuwara Eliya", 6.9348, 80.7736, 5, 0.75, "tier_3", ["waterfall", "nature", "scenic"], ["photography", "day_trip"], "A quick waterfall stop on the edge of town that helps enrich short local circuits.", [SLTDA_REGIONAL, wiki("Blackpool,_Nuwara_Eliya")]),
    a("Aberdeen Falls", "Nuwara Eliya", 7.0326, 80.6865, 7, 2.0, "tier_2", ["waterfall", "nature", "adventure"], ["photography", "day_trip"], "A strong waterfall excursion on the western side of the district, useful for corridor itineraries.", [SLTDA_REGIONAL, wiki("Aberdeen_Falls")]),
    a("Kande Ela Reservoir", "Nuwara Eliya", 6.8879, 80.7870, 5, 1.0, "tier_3", ["scenic", "nature"], ["day_trip", "photography"], "A scenic reservoir stop that can support quieter day loops around Ambewela and Hakgala.", [SLTDA_REGIONAL, wiki("Kande_Ela_Reservoir")]),
    a("Nanu Oya Railway Station", "Nuwara Eliya", 6.9457, 80.7604, 5, 0.5, "tier_3", ["historic", "scenic"], ["day_trip", "photography"], "A classic hill-country rail stop that can be useful in itineraries built around train travel and transfers.", [SLTDA_REGIONAL, wiki("Nanu_Oya_railway_station")]),

    # Polonnaruwa
    a("Royal Palace of King Parakramabahu", "Polonnaruwa", 7.9409, 81.0013, 7, 0.75, "tier_3", ["historic", "cultural"], ["day_trip", "photography"], "One of the most useful sub-stops inside Polonnaruwa for understanding the scale of the old capital.", [UNESCO_POLONNARUWA, wiki("Polonnaruwa")]),
    a("Polonnaruwa Vatadage", "Polonnaruwa", 7.9681, 81.0117, 8, 0.75, "tier_2", ["historic", "religious", "cultural"], ["must_see", "photography", "day_trip"], "A beautifully preserved circular shrine that is genuinely worth surfacing as its own itinerary stop.", [UNESCO_POLONNARUWA, wiki("Polonnaruwa_Vatadage")]),
    a("Rankoth Vehera", "Polonnaruwa", 7.9602, 81.0108, 7, 0.75, "tier_3", ["religious", "historic", "cultural"], ["day_trip", "photography"], "A major stupa that helps round out the monument mix inside the ancient city zone.", [UNESCO_POLONNARUWA, wiki("Rankoth_Vehera")]),
    a("Shiva Devale No. 2", "Polonnaruwa", 7.9650, 81.0091, 7, 0.75, "tier_3", ["historic", "religious", "cultural"], ["day_trip", "photography"], "The best-preserved Hindu shrine in Polonnaruwa adds welcome religious and architectural variety.", [UNESCO_POLONNARUWA, wiki("Shiva_Devale_No._2")]),
    a("Thuparama Image House", "Polonnaruwa", 7.9691, 81.0112, 7, 0.75, "tier_3", ["historic", "religious", "cultural"], ["day_trip", "photography"], "A compact but important image house that helps produce more granular Polonnaruwa day planning.", [UNESCO_POLONNARUWA, wiki("Thuparama,_Polonnaruwa")]),
    a("Pabalu Vehera", "Polonnaruwa", 7.9684, 81.0111, 6, 0.75, "tier_3", ["religious", "historic", "cultural"], ["day_trip"], "A supporting ancient-city monument that adds useful density to heritage-heavy route generation.", [UNESCO_POLONNARUWA, wiki("Pabalu_Vehera")]),
    a("Lankatilaka Image House", "Polonnaruwa", 7.9657, 81.0105, 7, 0.75, "tier_3", ["historic", "religious", "cultural"], ["day_trip", "photography"], "An important ruined image house that complements Gal Vihara and nearby monuments.", [UNESCO_POLONNARUWA, wiki("Lankatilaka_Temple,_Polonnaruwa")]),
    a("Gal Potha", "Polonnaruwa", 7.9686, 81.0110, 6, 0.5, "tier_3", ["historic", "cultural"], ["day_trip"], "The giant stone book is a worthwhile interpretive stop within the monument core.", [UNESCO_POLONNARUWA, wiki("Gal_Pota")]),

    # Puttalam
    a("Kalpitiya Lagoon", "Puttalam", 8.2406, 79.7565, 6, 2.0, "tier_3", ["nature", "scenic", "adventure"], ["photography", "day_trip"], "A key part of the Kalpitiya experience that supports lagoon-based boating and birding itineraries.", [SLTDA_REGIONAL, wiki("Kalpitiya_Lagoon")]),
    a("Alankuda Beach", "Puttalam", 8.1163, 79.7266, 6, 2.5, "tier_3", ["beach", "scenic"], ["couples", "photography", "day_trip"], "A quieter beach alternative on the Kalpitiya side of the district.", [SLTDA_REGIONAL, wiki("Alankuda")]),
    a("St. Anne's Shrine, Thalawila", "Puttalam", 8.1255, 79.7349, 7, 1.0, "tier_2", ["religious", "cultural"], ["iconic", "day_trip"], "One of the island's best-known Catholic shrines and a meaningful stop beyond the coast and parks.", [SLTDA_REGIONAL, wiki("St._Anne%27s_Shrine,_Thalawila")]),
    a("Talawila Beach", "Puttalam", 8.1184, 79.7352, 5, 1.5, "tier_3", ["beach", "scenic"], ["photography", "day_trip"], "A supporting coastal stop that pairs naturally with the Thalawila shrine visit.", [SLTDA_REGIONAL, wiki("Thalawila")]),
    a("Dutch Reformed Church, Kalpitiya", "Puttalam", 8.2333, 79.7661, 5, 0.5, "tier_3", ["historic", "religious", "cultural"], ["day_trip"], "A small but worthwhile heritage add-on near Kalpitiya Fort.", [SLTDA_REGIONAL, wiki("Kalpitiya")]),
    a("Baththalangunduwa", "Puttalam", 8.4328, 79.7075, 6, 5.0, "tier_3", ["beach", "scenic", "adventure"], ["hidden_gem", "photography", "day_trip"], "A remote island excursion that can meaningfully enrich specialized Kalpitiya itineraries.", [SLTDA_REGIONAL, wiki("Battalangunduwa")]),

    # Ratnapura
    a("Belihuloya", "Ratnapura", 6.7178, 80.7345, 7, 2.5, "tier_2", ["nature", "scenic", "adventure"], ["photography", "day_trip"], "A valuable southern hill-country stop that helps connect Ratnapura with the central highlands.", [SLTDA_REGIONAL, wiki("Belihuloya")]),
    a("Kirindi Ella", "Ratnapura", 6.7313, 80.5244, 6, 1.5, "tier_3", ["waterfall", "nature", "scenic"], ["photography", "day_trip"], "A worthwhile waterfall detour that gives Ratnapura more nature variety beyond the marquee sites.", [SLTDA_REGIONAL, wiki("Kirindi_Ella")]),
    a("Katugas Ella", "Ratnapura", 6.7087, 80.6988, 6, 1.5, "tier_3", ["waterfall", "nature", "scenic"], ["hidden_gem", "photography", "day_trip"], "A scenic waterfall stop around Belihuloya that supports the district's route-corridor value.", [SLTDA_REGIONAL, wiki("Belihuloya")]),
    a("Saman Devalaya", "Ratnapura", 6.6822, 80.4038, 6, 1.0, "tier_3", ["religious", "cultural", "historic"], ["day_trip", "photography"], "A notable local pilgrimage site that helps root Ratnapura itineraries in regional culture.", [SLTDA_REGIONAL, wiki("Saman_Devalaya")]),
    a("Wavulpane Cave", "Ratnapura", 6.6570, 80.1960, 6, 2.0, "tier_3", ["nature", "adventure"], ["hidden_gem", "day_trip"], "A bat cave excursion that adds a different kind of nature outing to the district.", [SLTDA_REGIONAL, wiki("Wavulpane_Cave")]),
    a("Kuragala", "Ratnapura", 6.6590, 80.7274, 6, 1.0, "tier_3", ["religious", "historic", "scenic"], ["day_trip", "photography"], "A hillside religious and historical site that fits naturally into Belihuloya-side route building.", [SLTDA_REGIONAL, wiki("Kuragala")]),

    # Trincomalee
    a("Uppuveli Beach", "Trincomalee", 8.6097, 81.2190, 7, 3.0, "tier_2", ["beach", "scenic", "family"], ["couples", "family_friendly", "photography"], "A strong beach base option closer to town than Nilaveli, useful for flexible east-coast itineraries.", [SLTDA_REGIONAL, wiki("Uppuveli")]),
    a("Dutch Bay Beach", "Trincomalee", 8.5718, 81.2332, 5, 1.5, "tier_3", ["beach", "scenic"], ["day_trip", "photography"], "A practical small beach stop near the fort peninsula and Koneswaram side of town.", [SLTDA_REGIONAL, wiki("Dutch_Bay")]),
    a("Swami Rock", "Trincomalee", 8.5713, 81.2334, 7, 0.75, "tier_2", ["scenic", "historic"], ["must_see", "photography", "day_trip"], "The dramatic clifftop viewpoint is one of Trincomalee's defining scenic stops.", [SLTDA_REGIONAL, wiki("Swami_Rock")]),
    a("Lover's Leap, Trincomalee", "Trincomalee", 8.5705, 81.2329, 6, 0.5, "tier_3", ["scenic", "historic"], ["photography", "day_trip"], "A short viewpoint stop closely tied to the Koneswaram and fort peninsula experience.", [SLTDA_REGIONAL, wiki("Lover%27s_Leap_(Trincomalee)")]),
    a("Pathirakali Amman Temple", "Trincomalee", 8.5759, 81.2340, 6, 0.75, "tier_3", ["religious", "cultural"], ["photography", "day_trip"], "A colorful urban temple that adds Hindu cultural coverage within Trincomalee town.", [SLTDA_REGIONAL, wiki("Pathirakali_Amman_Temple")]),
    a("Velgam Vehera", "Trincomalee", 8.6683, 81.0273, 6, 1.0, "tier_3", ["historic", "religious", "cultural"], ["hidden_gem", "day_trip"], "A lesser-visited Buddhist site that adds heritage depth to longer district itineraries.", [SLTDA_REGIONAL, wiki("Velgam_Vehera")]),
    a("Seruwila Mangala Raja Maha Vihara", "Trincomalee", 8.3570, 81.0915, 7, 1.5, "tier_2", ["religious", "historic", "cultural"], ["iconic", "day_trip"], "An important pilgrimage temple that meaningfully broadens Trincomalee beyond beaches and harbour stops.", [SLTDA_REGIONAL, wiki("Seruwila_Mangala_Raja_Maha_Vihara")]),

    # Second-pass controlled expansion
    a("Lankarama", "Anuradhapura", 8.3677, 80.3970, 7, 0.75, "tier_3", ["religious", "historic", "cultural"], ["day_trip", "photography"], "A compact but important dagoba that helps create richer monument sequencing in Anuradhapura.", [UNESCO_ANURADHAPURA, wiki("Lankarama")]),
    a("Ranmasu Uyana", "Anuradhapura", 8.3359, 80.3887, 6, 0.75, "tier_3", ["historic", "cultural", "scenic"], ["day_trip", "photography"], "The royal gardens add a softer landscape and hydraulic layer to ancient-city exploration.", [UNESCO_ANURADHAPURA, wiki("Ranmasu_Uyana")]),
    a("Vessagiriya Monastery", "Anuradhapura", 8.3296, 80.3872, 6, 1.0, "tier_3", ["historic", "religious", "nature"], ["hidden_gem", "day_trip"], "A quieter rock-monastery zone that helps diversify heritage-heavy days in the district.", [UNESCO_ANURADHAPURA, wiki("Vessagiriya")]),
    a("Tissa Wewa, Anuradhapura", "Anuradhapura", 8.3320, 80.3900, 6, 0.75, "tier_3", ["scenic", "historic", "nature"], ["photography", "day_trip"], "The ancient reservoir adds sunset and landscape pacing to Anuradhapura itineraries.", [UNESCO_ANURADHAPURA, wiki("Tissa_Wewa")]),

    a("Upper Diyaluma Pools", "Badulla", 6.7404, 81.0254, 7, 2.5, "tier_2", ["waterfall", "nature", "adventure", "scenic"], ["must_see", "photography", "day_trip"], "A strong adventure-oriented addition for travelers who want more than the lower waterfall viewpoint.", [SLTDA_REGIONAL, wiki("Diyaluma_Falls")]),
    a("Muthiyangana Raja Maha Vihara", "Badulla", 6.9937, 81.0552, 6, 1.0, "tier_3", ["religious", "historic", "cultural"], ["day_trip", "photography"], "An important temple in Badulla town that improves the district's non-Ella cultural range.", [SLTDA_REGIONAL, wiki("Muthiyangana_Raja_Maha_Vihara")]),
    a("Peacock Hill", "Badulla", 6.7910, 80.9466, 6, 2.0, "tier_3", ["scenic", "nature", "adventure"], ["hidden_gem", "photography", "day_trip"], "A lesser-known viewpoint hike that works well around Haputale and Lipton's Seat routing.", [SLTDA_REGIONAL, wiki("Peacock_Hill,_Sri_Lanka")]),
    a("Demodara Railway Station", "Badulla", 6.8997, 81.0559, 5, 0.5, "tier_3", ["historic", "scenic"], ["day_trip", "budget_friendly"], "A useful supporting rail heritage stop near the loop and bridge attractions.", [SLTDA_REGIONAL, wiki("Demodara_railway_station")]),

    a("Kallady Bridge", "Batticaloa", 7.7111, 81.7088, 5, 0.5, "tier_3", ["historic", "scenic"], ["photography", "day_trip"], "A recognizable bridge-and-lagoon stop that complements Batticaloa town sightseeing.", [SLTDA_REGIONAL, wiki("Kallady_Bridge")]),
    a("Batticaloa Lighthouse", "Batticaloa", 7.6958, 81.7264, 5, 0.5, "tier_3", ["scenic", "historic"], ["photography", "day_trip"], "A short coastal landmark stop useful for strengthening Batticaloa's seafront loop.", [SLTDA_REGIONAL, wiki("Batticaloa_Lighthouse")]),
    a("St. Mary's Cathedral, Batticaloa", "Batticaloa", 7.7160, 81.6968, 5, 0.75, "tier_3", ["religious", "historic", "cultural"], ["day_trip"], "A meaningful church landmark that adds more urban heritage substance to the district.", [SLTDA_REGIONAL, wiki("St._Mary%27s_Cathedral,_Batticaloa")]),
    a("Mamangam Temple", "Batticaloa", 7.7213, 81.7013, 5, 0.75, "tier_3", ["religious", "cultural"], ["day_trip", "photography"], "A supporting Hindu temple stop that improves Batticaloa's cultural diversity for itinerary planning.", [SLTDA_REGIONAL, wiki("Mamangam_Temple")]),

    a("Attanagalla Rajamaha Viharaya", "Gampaha", 7.1127, 80.1313, 6, 1.0, "tier_3", ["religious", "historic", "cultural"], ["day_trip", "photography"], "An inland heritage temple that gives Gampaha more depth beyond its Negombo cluster.", [SLTDA_REGIONAL, wiki("Attanagalla_Raja_Maha_Vihara")]),
    a("St. Sebastian's Church, Negombo", "Gampaha", 7.2325, 79.8411, 6, 0.75, "tier_3", ["religious", "historic", "cultural"], ["day_trip", "photography"], "A major church façade and festival site that fits naturally into Negombo heritage walks.", [SLTDA_REGIONAL, wiki("St._Sebastian%27s_Church,_Negombo")]),
    a("Ave Maria Convent, Negombo", "Gampaha", 7.2098, 79.8406, 5, 0.75, "tier_3", ["historic", "cultural"], ["day_trip"], "A smaller but useful colonial-era landmark that supports a more complete Negombo town circuit.", [SLTDA_REGIONAL, wiki("Negombo")]),

    a("Asupini Ella", "Kegalle", 7.0550, 80.3700, 6, 1.5, "tier_3", ["waterfall", "nature", "scenic"], ["photography", "day_trip"], "A meaningful waterfall stop that gives Kegalle more nature interest beyond Pinnawala.", [SLTDA_REGIONAL, wiki("Asupini_Ella")]),
    a("Bathalegala (Bible Rock)", "Kegalle", 7.0628, 80.4740, 7, 4.0, "tier_2", ["nature", "adventure", "scenic"], ["hidden_gem", "photography", "day_trip"], "A serious hike and viewpoint that materially improves Kegalle for outdoor-oriented route building.", [SLTDA_REGIONAL, wiki("Bible_Rock_(Sri_Lanka)")]),
    a("Saradiel Village", "Kegalle", 7.2412, 80.3560, 5, 1.0, "tier_3", ["cultural", "family"], ["family_friendly", "day_trip"], "A light cultural stop that can help fill family-friendly itineraries around Kegalle and Pinnawala.", [SLTDA_REGIONAL, wiki("Utuwankanda")]),
    a("Pinnawala Elephant Bathing Point", "Kegalle", 7.3022, 80.3886, 5, 0.75, "tier_3", ["family", "wildlife"], ["family_friendly", "photography", "day_trip"], "A useful supporting stop for travelers already committing time to the Pinnawala cluster.", [SLTDA_REGIONAL, wiki("Pinnawala_Elephant_Orphanage")]),

    a("Talaimannar Pier", "Mannar", 8.9682, 79.7281, 6, 1.0, "tier_3", ["historic", "scenic"], ["photography", "day_trip"], "A distinctive coastal remnant that adds real character to Mannar itineraries.", [SLTDA_REGIONAL, wiki("Talaimannar")]),
    a("Adam's Bridge Viewpoint", "Mannar", 9.0900, 79.7240, 6, 1.0, "tier_3", ["scenic", "historic"], ["photography", "day_trip"], "A meaningful geography-and-history stop for travelers exploring Talaimannar side trips.", [SLTDA_REGIONAL, wiki("Adam%27s_Bridge")]),
    a("Doric Bungalow", "Mannar", 8.9812, 79.9056, 5, 0.75, "tier_3", ["historic", "cultural"], ["day_trip", "photography"], "A colonial-period building that strengthens Mannar's compact heritage inventory.", [SLTDA_REGIONAL, wiki("Doric_Bungalow")]),
    a("Talaimannar Lighthouse", "Mannar", 9.0968, 79.7216, 5, 0.75, "tier_3", ["scenic", "historic"], ["photography", "day_trip"], "A coastal lighthouse stop that pairs naturally with the pier and Adam's Bridge side of Mannar.", [SLTDA_REGIONAL, wiki("Talaimannar")]),

    a("Maligawila Buddha Statue", "Monaragala", 6.8910, 81.1322, 7, 1.0, "tier_2", ["religious", "historic", "cultural"], ["must_see", "photography", "day_trip"], "A major ancient standing Buddha image that substantially improves Monaragala's tourism quality.", [SLTDA_REGIONAL, wiki("Maligawila")]),
    a("Dematamal Viharaya", "Monaragala", 6.7441, 81.1413, 5, 0.75, "tier_3", ["religious", "historic", "cultural"], ["day_trip"], "A useful supporting temple stop that adds more heritage texture to the district.", [SLTDA_REGIONAL, wiki("Dematamal_Viharaya")]),
    a("Duwili Ella", "Monaragala", 6.8778, 81.3264, 6, 2.0, "tier_3", ["waterfall", "nature", "scenic"], ["hidden_gem", "photography", "day_trip"], "A worthwhile waterfall stop that broadens Monaragala beyond shrines and archaeology.", [SLTDA_REGIONAL, wiki("Duwili_Ella")]),
    a("Maligawila Archaeological Museum", "Monaragala", 6.8912, 81.1320, 5, 0.75, "tier_3", ["museum", "historic", "cultural"], ["day_trip"], "A useful interpretive stop for travelers visiting the Maligawila sculpture complex.", [MUSEUM_LIST, wiki("Maligawila")]),

    a("Baker's Falls", "Nuwara Eliya", 6.8010, 80.8045, 7, 0.75, "tier_2", ["waterfall", "nature", "scenic"], ["photography", "day_trip"], "A signature waterfall stop inside Horton Plains that is genuinely useful as a sub-attraction.", [UNESCO_CENTRAL_HIGHLANDS, wiki("Baker%27s_Falls")]),
    a("World's End", "Nuwara Eliya", 6.8013, 80.8037, 8, 0.75, "tier_2", ["scenic", "nature", "adventure"], ["must_see", "photography", "day_trip"], "The iconic cliff-edge viewpoint deserves its own place in itinerary logic within Horton Plains.", [UNESCO_CENTRAL_HIGHLANDS, wiki("World%27s_End,_Sri_Lanka")]),
    a("Mini World's End", "Nuwara Eliya", 6.8072, 80.8058, 6, 0.5, "tier_3", ["scenic", "nature"], ["photography", "day_trip"], "A useful supporting viewpoint for more granular route building inside Horton Plains.", [UNESCO_CENTRAL_HIGHLANDS, wiki("World%27s_End,_Sri_Lanka")]),
    a("Pattipola Railway Station", "Nuwara Eliya", 6.8747, 80.7920, 5, 0.5, "tier_3", ["historic", "scenic"], ["day_trip", "photography"], "The island's highest broad-gauge railway station is a worthwhile hill-country supporting stop.", [SLTDA_REGIONAL, wiki("Pattipola_railway_station")]),

    a("Maduwanwela Walawwa", "Ratnapura", 6.4037, 80.5451, 6, 1.5, "tier_3", ["historic", "cultural"], ["day_trip", "photography"], "A substantial manor house stop that adds elite social history to Ratnapura itineraries.", [SLTDA_REGIONAL, wiki("Maduwanwela_Walawwa")]),
    a("Surathali Ella", "Ratnapura", 6.7197, 80.7267, 6, 1.5, "tier_3", ["waterfall", "nature", "scenic"], ["photography", "day_trip"], "A scenic Belihuloya-side waterfall that strengthens the southern hill-country edge corridor.", [SLTDA_REGIONAL, wiki("Belihuloya")]),
    a("Sankhapala Raja Maha Viharaya", "Ratnapura", 6.7133, 80.6510, 6, 1.0, "tier_3", ["religious", "historic", "cultural"], ["day_trip", "photography"], "A cliffside temple stop that adds another meaningful cultural option around Belihuloya-side routes.", [SLTDA_REGIONAL, wiki("Sankhapala_Raja_Maha_Viharaya")]),
    a("Kudawa Entrance, Sinharaja", "Ratnapura", 6.4014, 80.5708, 6, 1.0, "tier_3", ["nature", "wildlife", "adventure"], ["day_trip", "photography"], "A practical trailhead-level entry that helps make Sinharaja-related planning more flexible.", [UNESCO_SINHARAJA, wiki("Sinharaja_Forest_Reserve")]),

    a("Naval and Maritime Museum, Trincomalee", "Trincomalee", 8.5685, 81.2351, 6, 1.0, "tier_3", ["museum", "historic", "cultural"], ["day_trip"], "A useful specialty museum stop for fort-peninsula itineraries in Trincomalee.", [MUSEUM_LIST, wiki("Hoods_Tower_Museum")]),
    a("Trincomalee War Cemetery", "Trincomalee", 8.5887, 81.2186, 5, 0.75, "tier_3", ["historic", "cultural"], ["day_trip"], "A quieter but meaningful heritage stop that can complement town-based Trincomalee days.", [SLTDA_REGIONAL, wiki("Trincomalee_War_Cemetery")]),
    a("Sober Island", "Trincomalee", 8.5964, 81.2502, 5, 2.0, "tier_3", ["scenic", "nature"], ["hidden_gem", "photography", "day_trip"], "A lesser-known harbour-island excursion that adds variety for longer Trincomalee stays.", [SLTDA_REGIONAL, wiki("Sober_Island")]),
    a("Orr's Hill Army Museum", "Trincomalee", 8.5750, 81.2030, 5, 1.0, "tier_3", ["museum", "historic"], ["day_trip"], "A specialist history stop that can add extra depth for visitors interested in the district's military past.", [MUSEUM_LIST, wiki("Trincomalee")]),
]

ATTRACTIONS.extend(EXTRA_ATTRACTIONS)


def build_dataset() -> dict:
    seen_ids = set()
    district_rows = {
        district: {"district": district, "province": province, "attractions": []}
        for district, province in DISTRICTS
    }
    tier_counts = Counter()

    for item in ATTRACTIONS:
        row = dict(item)
        row["id"] = f"lk_{slugify(row['district'])}_{slugify(row['name'])}"

        if row["id"] in seen_ids:
            raise ValueError(f"Duplicate id: {row['id']}")
        seen_ids.add(row["id"])

        required = {
            "id",
            "name",
            "district",
            "province",
            "categories",
            "latitude",
            "longitude",
            "importance_score",
            "estimated_visit_hours",
            "tier",
            "tags",
            "summary",
            "source_urls",
        }
        missing = required - row.keys()
        if missing:
            raise ValueError(f"Missing fields for {row['name']}: {sorted(missing)}")

        if row["district"] not in PROVINCE_BY_DISTRICT:
            raise ValueError(f"Unknown district: {row['district']}")

        if row["province"] != PROVINCE_BY_DISTRICT[row["district"]]:
            raise ValueError(f"Province mismatch for {row['name']}")

        if row["tier"] not in TIER_ORDER:
            raise ValueError(f"Invalid tier for {row['name']}: {row['tier']}")

        if not 1 <= row["importance_score"] <= 10:
            raise ValueError(f"Invalid importance score for {row['name']}")

        if row["estimated_visit_hours"] <= 0:
            raise ValueError(f"Invalid visit hours for {row['name']}")

        if not set(row["categories"]).issubset(CATEGORY_SET):
            raise ValueError(f"Invalid categories for {row['name']}: {row['categories']}")

        if not set(row["tags"]).issubset(TAG_SET):
            raise ValueError(f"Invalid tags for {row['name']}: {row['tags']}")

        if not row["source_urls"]:
            raise ValueError(f"No sources for {row['name']}")

        sltda_label = SLTDA_CROSS_REFERENCE_MAP.get(row["name"])
        if sltda_label and SLTDA_ATTRACTIONS not in row["source_urls"]:
            row["source_urls"] = list(row["source_urls"]) + [SLTDA_ATTRACTIONS]

        row["categories"] = sorted(set(row["categories"]))
        row["tags"] = sorted(set(row["tags"]))
        row["source_urls"] = list(dict.fromkeys(row["source_urls"]))
        district_rows[row["district"]]["attractions"].append(row)
        tier_counts[row["tier"]] += 1

    districts = []
    for district, province in DISTRICTS:
        attractions = sorted(
            district_rows[district]["attractions"],
            key=lambda item: (
                TIER_ORDER[item["tier"]],
                -item["importance_score"],
                item["name"],
            ),
        )
        districts.append(
            {
                "district": district,
                "province": province,
                "attraction_count": len(attractions),
                "attractions": attractions,
            }
        )

    item_count = sum(d["attraction_count"] for d in districts)
    return {
        "metadata": {
            "dataset_name": "Sri Lanka Curated Tourist Attractions",
            "schema_version": "3.1.0",
            "generated_on": "2026-06-05",
            "generated_by": "build_sri_lanka_attractions.py",
            "country": "Sri Lanka",
            "organization": "district",
            "item_count": item_count,
            "district_count": len(districts),
            "required_fields": [
                "id",
                "name",
                "district",
                "province",
                "categories",
                "latitude",
                "longitude",
                "importance_score",
                "estimated_visit_hours",
                "tier",
                "tags",
                "summary",
                "source_urls",
            ],
            "tier_counts": {
                "tier_1": tier_counts["tier_1"],
                "tier_2": tier_counts["tier_2"],
                "tier_3": tier_counts["tier_3"],
            },
            "official_cross_reference_source": SLTDA_ATTRACTIONS,
            "official_cross_referenced_attraction_count": len(SLTDA_CROSS_REFERENCE_MAP),
            "coverage_strategy": "Curated itinerary dataset with richer district coverage rather than exhaustive POI scraping.",
            "districts_intentionally_sparse": SPARSE_DISTRICT_NOTES,
        },
        "districts": districts,
    }


def write_summary(dataset: dict) -> None:
    districts = dataset["districts"]
    tier_counts = dataset["metadata"]["tier_counts"]
    district_counts = {row["district"]: row["attraction_count"] for row in districts}
    district_deltas = {
        district: district_counts[district] - BASELINE_DISTRICT_COUNTS[district]
        for district in district_counts
    }
    top_districts = sorted(
        district_deltas.items(),
        key=lambda item: (-item[1], item[0]),
    )
    corridor_deltas = []
    for corridor, members in CORRIDORS.items():
        delta = sum(district_deltas[district] for district in members)
        current_total = sum(district_counts[district] for district in members)
        corridor_deltas.append((corridor, delta, current_total))
    corridor_deltas.sort(key=lambda item: (-item[1], item[0]))
    sparse_rows = [
        f"- `{district}`: {note}"
        for district, note in SPARSE_DISTRICT_NOTES.items()
    ]

    lines = [
        "# Dataset Summary",
        "",
        f"- Total attractions: **{dataset['metadata']['item_count']}**",
        f"- Districts covered: **{dataset['metadata']['district_count']}**",
        f"- `tier_1` attractions: **{tier_counts['tier_1']}**",
        f"- `tier_2` attractions: **{tier_counts['tier_2']}**",
        f"- `tier_3` attractions: **{tier_counts['tier_3']}**",
        "",
        "## SLTDA Cross-Reference Use",
        "",
        f"- Official validation source used: `{dataset['metadata']['official_cross_reference_source']}`",
        f"- Attractions with explicit SLTDA cross-reference mapping in the builder: **{dataset['metadata']['official_cross_referenced_attraction_count']}**",
        "- SLTDA was used to validate tourism relevance, strengthen source support, and identify careful additions rather than to replace the curated dataset.",
        "",
        "## Focus District Counts",
        "",
    ]

    for district in FOCUS_DISTRICTS:
        lines.append(f"- `{district}`: {district_counts[district]}")

    lines.extend(
        [
            "",
            "## Most Expanded Districts",
            "",
        ]
    )

    for district, delta in top_districts[:10]:
        if delta > 0:
            lines.append(f"- `{district}`: +{delta} attractions, now `{district_counts[district]}` total")
    if not any(delta > 0 for _, delta in top_districts):
        lines.append("- No district counts changed in this pass.")

    lines.extend(
        [
            "",
            "## Most Expanded Corridors",
            "",
        ]
    )

    for corridor, delta, current_total in corridor_deltas:
        if delta > 0:
            lines.append(f"- `{corridor}`: +{delta} attractions across the corridor, now `{current_total}` total")
    if not any(delta > 0 for _, delta, _ in corridor_deltas):
        lines.append("- No corridor totals changed materially in this SLTDA pass; the main update was a targeted district-level addition plus broader source strengthening.")

    lines.extend(
        [
            "",
            "## Attraction Count by District",
            "",
        ]
    )

    for row in districts:
        lines.append(f"- `{row['district']}`: {row['attraction_count']}")

    lines.extend(
        [
            "",
            "## Intentionally Sparse Districts",
            "",
            *sparse_rows,
            "",
            "## Intentionally Unresolved Gaps",
            "",
            "- Some SLTDA entries describe broader destination areas such as Colombo, Hambantota, Negombo, Matara, Puttalam, and Jaffna rather than a single attraction. These were used mainly as official validation for corridor importance when the dataset already had stronger sub-attraction coverage.",
            "- A few low-tourism northern districts remain intentionally selective even after SLTDA review because official destination mention alone was not enough to justify adding weak filler.",
            "",
        ]
    )
    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    dataset = build_dataset()
    OUTPUT_PATH.write_text(
        json.dumps(dataset, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    write_summary(dataset)
    print(
        f"Wrote {OUTPUT_PATH} with {dataset['metadata']['item_count']} attractions "
        f"and {SUMMARY_PATH.name}."
    )


if __name__ == "__main__":
    main()
