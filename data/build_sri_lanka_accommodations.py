#!/usr/bin/env python3
"""Build and validate a curated Sri Lanka accommodations dataset."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


DATA_DIR = Path(__file__).parent
OUTPUT_PATH = DATA_DIR / "sri_lanka_accommodations.json"
SUMMARY_PATH = DATA_DIR / "accommodations_summary.md"

SL_TOURISM = "https://www.srilanka.travel/"
JETWING = "https://www.jetwinghotels.com/"
CINNAMON = "https://www.cinnamonhotels.com/"
AITKEN = "https://www.aitkenspencehotels.com/"
RESP = "https://www.resplendentceylon.com/"
TAJ = "https://www.tajhotels.com/"
HILTON = "https://www.hilton.com/"
SHANGRI = "https://www.shangri-la.com/"
MARRIOTT = "https://www.marriott.com/"
MINOR = "https://www.minorhotels.com/"
WYNDHAM = "https://www.wyndhamhotels.com/"
UGA = "https://www.ugaescapes.com/"
MAHAWELI = "https://www.mahaweli.com/"
ARALIYA = "https://www.araliyaresorts.com/"


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
PRICE_BANDS = {"budget", "midrange", "premium", "luxury"}
RATING_BANDS = {"basic", "good", "very_good", "excellent"}
ACCOMMODATION_TYPES = {
    "hotel",
    "resort",
    "guesthouse",
    "villa",
    "eco_lodge",
    "hostel",
    "homestay",
    "bungalow",
    "boutique_hotel",
    "safari_lodge",
}
TAG_SET = {
    "backpacker",
    "beachfront",
    "city_stay",
    "couples",
    "eco",
    "family_friendly",
    "heritage_area",
    "mountain_view",
    "scenic",
    "surf_access",
    "wellness",
    "wildlife_access",
}
IDEAL_FOR_SET = {
    "backpackers",
    "business",
    "couples",
    "culture_seekers",
    "family",
    "luxury_travelers",
    "nature_lovers",
    "surfers",
    "wellness",
    "wildlife_lovers",
}

SPARSE_DISTRICT_NOTES = {
    "Kilinochchi": "Kept intentionally sparse because the district has limited established leisure accommodation inventory with broad tourism pull.",
    "Mullaitivu": "Kept intentionally sparse because the district remains a light overnight market for mainstream itineraries.",
    "Vavuniya": "Kept intentionally sparse because it is more commonly used as a transit overnight than as a destination base.",
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
    "Negombo / airport gateway": ["Gampaha", "Colombo"],
    "Kalpitiya / Wilpattu northwest": ["Puttalam"],
}

AREAS = {
    "colombo_fort": ("Colombo", "Colombo Fort", 6.9350, 79.8428, "Colombo urban gateway"),
    "colombo_city": ("Colombo", "Colombo city", 6.9147, 79.8567, "Colombo urban gateway"),
    "mount_lavinia": ("Colombo", "Mount Lavinia", 6.8389, 79.8637, "Colombo urban gateway"),
    "negombo_beach": ("Gampaha", "Negombo beach belt", 7.2304, 79.8407, "Negombo / airport gateway"),
    "negombo_lagoon": ("Gampaha", "Negombo lagoon side", 7.1931, 79.8278, "Negombo / airport gateway"),
    "katunayake": ("Gampaha", "Katunayake / airport", 7.1710, 79.8880, "Negombo / airport gateway"),
    "waikkal": ("Gampaha", "Waikkal", 7.2760, 79.8550, "Negombo / airport gateway"),
    "kalutara": ("Kalutara", "Kalutara", 6.5854, 79.9607, "Colombo -> Kalutara -> Bentota/Beruwala side"),
    "bentota": ("Kalutara", "Bentota", 6.4218, 79.9957, "Colombo -> Kalutara -> Bentota/Beruwala side"),
    "beruwala": ("Kalutara", "Beruwala", 6.4788, 79.9821, "Colombo -> Kalutara -> Bentota/Beruwala side"),
    "galle_fort": ("Galle", "Galle Fort", 6.0260, 80.2166, "Colombo -> Galle -> Matara -> Hambantota"),
    "unawatuna": ("Galle", "Unawatuna", 6.0100, 80.2496, "Colombo -> Galle -> Matara -> Hambantota"),
    "hikkaduwa": ("Galle", "Hikkaduwa", 6.1407, 80.1006, "Colombo -> Galle -> Matara -> Hambantota"),
    "koggala": ("Galle", "Koggala", 5.9924, 80.3330, "Colombo -> Galle -> Matara -> Hambantota"),
    "ahangama": ("Galle", "Ahangama", 5.9735, 80.3613, "Colombo -> Galle -> Matara -> Hambantota"),
    "mirissa": ("Matara", "Mirissa", 5.9483, 80.4716, "Colombo -> Galle -> Matara -> Hambantota"),
    "weligama": ("Matara", "Weligama", 5.9730, 80.4297, "Colombo -> Galle -> Matara -> Hambantota"),
    "talalla": ("Matara", "Talalla", 5.9021, 80.4932, "Colombo -> Galle -> Matara -> Hambantota"),
    "dickwella": ("Matara", "Dickwella / Hiriketiya", 5.9640, 80.6928, "Colombo -> Galle -> Matara -> Hambantota"),
    "tissamaharama": ("Hambantota", "Tissamaharama", 6.2848, 81.2885, "Colombo -> Galle -> Matara -> Hambantota"),
    "yala": ("Hambantota", "Yala / Palatupana", 6.3725, 81.5185, "Colombo -> Galle -> Matara -> Hambantota"),
    "tangalle": ("Hambantota", "Tangalle", 6.0242, 80.7950, "Colombo -> Galle -> Matara -> Hambantota"),
    "hambantota": ("Hambantota", "Hambantota / Weerawila", 6.1241, 81.1185, "Colombo -> Galle -> Matara -> Hambantota"),
    "kandy_city": ("Kandy", "Kandy city", 7.2906, 80.6337, "Kandy -> Nuwara Eliya -> Ella -> Badulla"),
    "peradeniya": ("Kandy", "Peradeniya", 7.2682, 80.5950, "Kandy -> Nuwara Eliya -> Ella -> Badulla"),
    "hanthana": ("Kandy", "Hanthana", 7.2530, 80.6289, "Kandy -> Nuwara Eliya -> Ella -> Badulla"),
    "gampola": ("Kandy", "Gampola side", 7.1643, 80.5690, "Kandy -> Matale -> Dambulla -> Sigiriya"),
    "madulkelle": ("Kandy", "Madulkelle / Knuckles side", 7.3900, 80.8170, "Kandy -> Nuwara Eliya -> Ella -> Badulla"),
    "matale_town": ("Matale", "Matale town", 7.4675, 80.6234, "Kandy -> Matale -> Dambulla -> Sigiriya"),
    "dambulla": ("Matale", "Dambulla", 7.8600, 80.6510, "Kandy -> Matale -> Dambulla -> Sigiriya"),
    "sigiriya": ("Matale", "Sigiriya", 7.9570, 80.7603, "Kandy -> Matale -> Dambulla -> Sigiriya"),
    "kandalama": ("Matale", "Kandalama", 7.8878, 80.7035, "Kandy -> Matale -> Dambulla -> Sigiriya"),
    "habarana": ("Matale", "Habarana", 8.0373, 80.7523, "Kandy -> Matale -> Dambulla -> Sigiriya"),
    "nuwara_eliya": ("Nuwara Eliya", "Nuwara Eliya town", 6.9497, 80.7891, "Kandy -> Nuwara Eliya -> Ella -> Badulla"),
    "hakgala": ("Nuwara Eliya", "Hakgala / Seetha Eliya", 6.9234, 80.8211, "Kandy -> Nuwara Eliya -> Ella -> Badulla"),
    "hatton": ("Nuwara Eliya", "Hatton / tea country", 6.8916, 80.5955, "Kandy -> Nuwara Eliya -> Ella -> Badulla"),
    "ella": ("Badulla", "Ella", 6.8666, 81.0467, "Kandy -> Nuwara Eliya -> Ella -> Badulla"),
    "bandarawela": ("Badulla", "Bandarawela", 6.8280, 80.9880, "Kandy -> Nuwara Eliya -> Ella -> Badulla"),
    "haputale": ("Badulla", "Haputale", 6.7650, 80.9510, "Kandy -> Nuwara Eliya -> Ella -> Badulla"),
    "badulla": ("Badulla", "Badulla town", 6.9934, 81.0550, "Kandy -> Nuwara Eliya -> Ella -> Badulla"),
    "anuradhapura": ("Anuradhapura", "Anuradhapura", 8.3349, 80.4101, "Dambulla -> Polonnaruwa -> Anuradhapura"),
    "tissawewa": ("Anuradhapura", "Tissa Wewa side", 8.3320, 80.3900, "Dambulla -> Polonnaruwa -> Anuradhapura"),
    "polonnaruwa": ("Polonnaruwa", "Polonnaruwa", 7.9403, 81.0188, "Dambulla -> Polonnaruwa -> Anuradhapura"),
    "giritale": ("Polonnaruwa", "Giritale / Minneriya side", 8.0220, 80.8840, "Dambulla -> Polonnaruwa -> Anuradhapura"),
    "trinco_town": ("Trincomalee", "Trincomalee town", 8.5874, 81.2152, "Trincomalee -> Batticaloa -> Ampara"),
    "uppuveli": ("Trincomalee", "Uppuveli", 8.6097, 81.2190, "Trincomalee -> Batticaloa -> Ampara"),
    "nilaveli": ("Trincomalee", "Nilaveli", 8.6991, 81.2050, "Trincomalee -> Batticaloa -> Ampara"),
    "pasikudah": ("Batticaloa", "Pasikudah / Kalkudah", 7.9291, 81.5612, "Trincomalee -> Batticaloa -> Ampara"),
    "batticaloa": ("Batticaloa", "Batticaloa town", 7.7102, 81.7005, "Trincomalee -> Batticaloa -> Ampara"),
    "arugam": ("Ampara", "Arugam Bay", 6.8404, 81.8368, "Trincomalee -> Batticaloa -> Ampara"),
    "pottuvil": ("Ampara", "Pottuvil / Whiskey Point", 6.8765, 81.8301, "Trincomalee -> Batticaloa -> Ampara"),
    "jaffna": ("Jaffna", "Jaffna town", 9.6615, 80.0255, "Jaffna -> Mannar"),
    "nallur": ("Jaffna", "Nallur", 9.6758, 80.0303, "Jaffna -> Mannar"),
    "mannar": ("Mannar", "Mannar", 8.9819, 79.9047, "Jaffna -> Mannar"),
    "ratnapura": ("Ratnapura", "Ratnapura town", 6.6828, 80.3992, "Ratnapura -> Belihuloya / southern hill-country edge"),
    "belihuloya": ("Ratnapura", "Belihuloya", 6.7178, 80.7345, "Ratnapura -> Belihuloya / southern hill-country edge"),
    "sinharaja": ("Ratnapura", "Sinharaja / Kudawa side", 6.4014, 80.5708, "Ratnapura -> Belihuloya / southern hill-country edge"),
    "kalpitiya": ("Puttalam", "Kalpitiya", 8.2337, 79.7667, "Kalpitiya / Wilpattu northwest"),
    "wilpattu": ("Puttalam", "Wilpattu side", 8.4490, 79.9950, "Kalpitiya / Wilpattu northwest"),
    "marawila": ("Puttalam", "Marawila / Waikkal north", 7.4300, 79.8240, "Kalpitiya / Wilpattu northwest"),
    "kurunegala": ("Kurunegala", "Kurunegala", 7.4863, 80.3647, "Interior transit and heritage corridor"),
    "pinnawala": ("Kegalle", "Pinnawala", 7.3018, 80.3882, "Interior transit and heritage corridor"),
    "wellawaya": ("Monaragala", "Wellawaya / Monaragala side", 6.7360, 81.1070, "Ratnapura -> Belihuloya / southern hill-country edge"),
    "kilinochchi": ("Kilinochchi", "Kilinochchi", 9.3803, 80.3982, "Northern overland transit"),
    "mullaitivu": ("Mullaitivu", "Mullaitivu", 9.2671, 80.8141, "Northern overland transit"),
    "vavuniya": ("Vavuniya", "Vavuniya", 8.7514, 80.4971, "Northern overland transit"),
}


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def acc(
    name: str,
    area_key: str,
    accommodation_type: str,
    price_band: str,
    rating_band: str,
    tags: list[str],
    ideal_for: list[str],
    summary: str,
    source_urls: list[str],
) -> dict:
    district, nearby_area, latitude, longitude, corridor = AREAS[area_key]
    return {
        "name": name,
        "district": district,
        "province": PROVINCE_BY_DISTRICT[district],
        "latitude": latitude,
        "longitude": longitude,
        "accommodation_type": accommodation_type,
        "price_band": price_band,
        "rating_band": rating_band,
        "tags": tags,
        "ideal_for": ideal_for,
        "summary": summary,
        "source_urls": source_urls,
        "nearby_area": nearby_area,
        "corridor": corridor,
        "notable_location_context": nearby_area,
    }


ACCOMMODATIONS = [
    # Colombo 18
    acc("Galle Face Hotel", "colombo_fort", "hotel", "luxury", "excellent", ["city_stay", "heritage_area", "couples"], ["couples", "business", "luxury_travelers"], "Iconic seafront grand hotel for premium Colombo overnights.", [SL_TOURISM, wiki("Galle_Face_Hotel")]),
    acc("Shangri-La Colombo", "colombo_fort", "hotel", "luxury", "excellent", ["city_stay", "family_friendly", "scenic"], ["family", "business", "luxury_travelers"], "Flagship luxury city hotel for high-end arrival and departure stays.", [SHANGRI, SL_TOURISM]),
    acc("Cinnamon Grand Colombo", "colombo_city", "hotel", "luxury", "excellent", ["city_stay", "family_friendly"], ["family", "business", "luxury_travelers"], "Long-established upscale Colombo hotel with strong city-stay relevance.", [CINNAMON, SL_TOURISM]),
    acc("Cinnamon Lakeside Colombo", "colombo_city", "hotel", "premium", "excellent", ["city_stay", "family_friendly", "scenic"], ["family", "business"], "A polished lake-adjacent city stay for premium Colombo nights.", [CINNAMON, SL_TOURISM]),
    acc("Cinnamon Red Colombo", "colombo_city", "hotel", "midrange", "very_good", ["city_stay"], ["business", "couples"], "Modern city hotel suited to efficient Colombo overnights.", [CINNAMON, SL_TOURISM]),
    acc("Taj Samudra", "colombo_fort", "hotel", "luxury", "excellent", ["city_stay", "family_friendly", "scenic"], ["family", "business", "couples"], "A classic seafront luxury hotel in Colombo.", [TAJ, SL_TOURISM]),
    acc("Hilton Colombo", "colombo_fort", "hotel", "luxury", "excellent", ["city_stay"], ["business", "family"], "A dependable five-star central Colombo base.", [HILTON, SL_TOURISM]),
    acc("Hilton Colombo Residences", "colombo_city", "hotel", "premium", "very_good", ["city_stay", "family_friendly"], ["family", "business"], "A practical apartment-style Colombo option with stronger family appeal.", [HILTON, SL_TOURISM]),
    acc("The Kingsbury Colombo", "colombo_fort", "hotel", "luxury", "excellent", ["city_stay", "family_friendly"], ["family", "business", "couples"], "Premium Fort-side hotel close to central Colombo highlights.", [SL_TOURISM, wiki("The_Kingsbury,_Colombo")]),
    acc("Jetwing Colombo Seven", "colombo_city", "hotel", "premium", "very_good", ["city_stay"], ["business", "couples"], "A stylish Colombo stay with strong short-break utility.", [JETWING, SL_TOURISM]),
    acc("Marino Beach Colombo", "colombo_city", "hotel", "premium", "very_good", ["city_stay", "family_friendly", "scenic"], ["family", "couples"], "Popular urban leisure hotel with broad appeal.", [SL_TOURISM, wiki("Marino_Beach_Colombo")]),
    acc("Granbell Hotel Colombo", "colombo_city", "hotel", "premium", "very_good", ["city_stay", "scenic", "couples"], ["couples", "business"], "A modern seafront Colombo hotel for stylish short stays.", [SL_TOURISM, wiki("Granbell_Hotel_Colombo")]),
    acc("Ramada by Wyndham Colombo", "colombo_city", "hotel", "premium", "good", ["city_stay", "family_friendly"], ["business", "family"], "A practical chain-backed central Colombo hotel.", [WYNDHAM, SL_TOURISM]),
    acc("Mandarina Colombo", "colombo_city", "hotel", "midrange", "very_good", ["city_stay"], ["business", "couples"], "Reliable mid-range city hotel with solid location value.", [SL_TOURISM, wiki("Mandarina_Colombo")]),
    acc("Fairway Colombo", "colombo_fort", "hotel", "midrange", "good", ["city_stay", "heritage_area"], ["business", "couples", "family"], "A practical Fort-area hotel for walkable Colombo stays.", [SL_TOURISM, wiki("Fairway_Colombo")]),
    acc("Paradise Road Tintagel Colombo", "colombo_city", "boutique_hotel", "luxury", "excellent", ["city_stay", "couples", "heritage_area"], ["couples", "luxury_travelers"], "Design-led boutique stay for intimate premium Colombo overnights.", [SL_TOURISM, wiki("Tintagel_Colombo")]),
    acc("C1 Colombo Fort", "colombo_fort", "hostel", "budget", "good", ["city_stay", "backpacker"], ["backpackers", "culture_seekers"], "A recognizable budget stay improving low-cost coverage in central Colombo.", [SL_TOURISM, wiki("C1_Colombo_Fort")]),
    acc("Mount Lavinia Hotel", "mount_lavinia", "hotel", "premium", "very_good", ["beachfront", "heritage_area", "couples"], ["couples", "family"], "Historic seaside stay that works well for urban beach overnights.", [SL_TOURISM, wiki("Mount_Lavinia_Hotel")]),

    # Gampaha 16
    acc("Jetwing Blue", "negombo_beach", "hotel", "premium", "excellent", ["beachfront", "family_friendly", "scenic"], ["family", "couples", "luxury_travelers"], "One of Negombo's signature beachfront stays.", [JETWING, wiki("Jetwing_Blue")]),
    acc("Jetwing Beach", "negombo_beach", "resort", "luxury", "excellent", ["beachfront", "family_friendly", "scenic"], ["family", "couples", "luxury_travelers"], "A flagship Negombo beachfront resort.", [JETWING, SL_TOURISM]),
    acc("Jetwing Sea", "negombo_beach", "hotel", "premium", "very_good", ["beachfront"], ["couples", "family"], "Upscale Negombo beach stay with strong airport-corridor usefulness.", [JETWING, SL_TOURISM]),
    acc("Jetwing Lagoon Wellness", "negombo_lagoon", "resort", "luxury", "excellent", ["wellness", "scenic", "couples"], ["wellness", "couples", "luxury_travelers"], "Lagoon-side luxury option for recovery near the airport.", [JETWING, SL_TOURISM]),
    acc("Jetwing Ayurveda Pavilions", "negombo_lagoon", "resort", "luxury", "excellent", ["wellness", "couples", "eco"], ["wellness", "couples"], "Wellness-oriented Negombo stay with Ayurveda focus.", [JETWING, SL_TOURISM]),
    acc("Heritance Negombo", "negombo_beach", "hotel", "luxury", "excellent", ["beachfront", "family_friendly"], ["family", "couples", "business"], "A major upscale Negombo beachfront option.", [AITKEN, SL_TOURISM]),
    acc("Vivanta Colombo, Airport Garden", "katunayake", "hotel", "premium", "very_good", ["city_stay"], ["business", "family"], "Highly practical premium airport-area overnight.", [TAJ, SL_TOURISM]),
    acc("The Wallawwa", "katunayake", "boutique_hotel", "luxury", "excellent", ["couples", "wellness", "scenic"], ["couples", "luxury_travelers"], "Polished boutique estate stay near the airport corridor.", [SL_TOURISM, wiki("The_Wallawwa")]),
    acc("Club Hotel Dolphin", "waikkal", "resort", "premium", "very_good", ["beachfront", "family_friendly"], ["family", "couples"], "Popular resort north of Negombo with broad route appeal.", [AITKEN, SL_TOURISM]),
    acc("Camelot Beach Hotel", "negombo_beach", "hotel", "midrange", "good", ["beachfront", "family_friendly"], ["family", "couples"], "Mainstream Negombo beach stay with dependable mid-range fit.", [SL_TOURISM, wiki("Camelot_Beach_Hotel")]),
    acc("Goldi Sands Hotel", "negombo_beach", "hotel", "midrange", "good", ["beachfront", "family_friendly"], ["family", "couples"], "Long-running Negombo beachfront hotel with broad familiarity.", [SL_TOURISM, wiki("Goldi_Sands_Hotel")]),
    acc("Hotel J Negombo", "negombo_beach", "hotel", "budget", "good", ["beachfront", "backpacker"], ["backpackers", "couples"], "Budget-friendlier branded stay on the Negombo strip.", [JETWING, SL_TOURISM]),
    acc("Amagi Aria", "negombo_lagoon", "hotel", "midrange", "good", ["scenic", "family_friendly"], ["family", "business"], "Lagoon-facing mid-range option for transit or short breaks.", [SL_TOURISM, wiki("Amagi_Aria")]),
    acc("Pledge Scape", "negombo_beach", "boutique_hotel", "premium", "very_good", ["beachfront", "couples"], ["couples", "luxury_travelers"], "Stylish smaller Negombo property with higher-end short-stay appeal.", [SL_TOURISM, wiki("Pledge_Scape")]),
    acc("Terrace Green Hotel & Spa", "negombo_beach", "boutique_hotel", "midrange", "very_good", ["beachfront", "couples", "wellness"], ["couples", "family"], "Well-regarded Negombo boutique option with good short-stay value.", [SL_TOURISM, wiki("Terrace_Green_Hotel_%26_Spa")]),
    acc("Airport Green View Resort", "katunayake", "hotel", "budget", "good", ["city_stay"], ["business", "family"], "Lower-cost airport-area stay for late arrivals or early departures.", [SL_TOURISM, wiki("Bandaranaike_International_Airport")]),

    # Kalutara 15
    acc("Taj Bentota Resort & Spa", "bentota", "resort", "luxury", "excellent", ["beachfront", "family_friendly"], ["family", "couples", "luxury_travelers"], "Major premium Bentota resort with strong southwest coast value.", [TAJ, SL_TOURISM]),
    acc("Cinnamon Bentota Beach", "bentota", "resort", "luxury", "excellent", ["beachfront", "family_friendly"], ["family", "couples"], "One of Bentota's most recognizable upscale resorts.", [CINNAMON, SL_TOURISM]),
    acc("Avani Bentota Resort", "bentota", "resort", "premium", "excellent", ["beachfront", "family_friendly"], ["family", "couples"], "Polished resort stay suited to west-to-south coastal routing.", [MINOR, SL_TOURISM]),
    acc("Jetwing Saman Villas", "bentota", "villa", "luxury", "excellent", ["beachfront", "couples", "scenic"], ["couples", "luxury_travelers"], "High-end romantic villa property on the southwest coast.", [JETWING, SL_TOURISM]),
    acc("Thaala Bentota", "bentota", "hotel", "premium", "very_good", ["beachfront", "family_friendly"], ["family", "couples"], "Mainstream premium Bentota stay with strong route usefulness.", [SL_TOURISM, wiki("Thaala_Bentota")]),
    acc("EKHO Surf", "bentota", "hotel", "midrange", "good", ["beachfront", "family_friendly"], ["family", "couples"], "Practical beachfront Bentota hotel suited to varied traveler types.", [SL_TOURISM, wiki("EKHO_Surf")]),
    acc("Club Villa", "bentota", "boutique_hotel", "premium", "very_good", ["couples", "scenic"], ["couples", "luxury_travelers"], "Classic boutique-style stay for quieter Bentota overnights.", [SL_TOURISM, wiki("Club_Villa_Bentota")]),
    acc("Temple Tree Resort & Spa", "bentota", "resort", "premium", "very_good", ["beachfront", "family_friendly"], ["family", "couples"], "Recognized Bentota-area resort adding more mid-to-premium depth.", [SL_TOURISM, wiki("Bentota")]),
    acc("Lanka Princess", "beruwala", "hotel", "premium", "very_good", ["beachfront", "wellness", "couples"], ["couples", "wellness"], "A well-known Beruwala-side resort with repeat tourism relevance.", [SL_TOURISM, wiki("Lanka_Princess_Hotel")]),
    acc("Heritance Ayurveda Maha Gedara", "beruwala", "resort", "premium", "excellent", ["beachfront", "wellness"], ["wellness", "couples"], "A strong Ayurveda-led stay that broadens wellness coverage on the southwest coast.", [AITKEN, SL_TOURISM]),
    acc("Occidental Eden Beruwala", "beruwala", "resort", "premium", "very_good", ["beachfront", "family_friendly"], ["family", "couples"], "A popular mainstream resort for the Beruwala side of the corridor.", [SL_TOURISM, wiki("Eden_Resort_%26_Spa")]),
    acc("The Palms Beruwala", "beruwala", "hotel", "midrange", "good", ["beachfront", "family_friendly"], ["family", "couples"], "A practical Beruwala beach stay for mid-range route planning.", [SL_TOURISM, wiki("Beruwala")]),
    acc("Earl's Reef", "beruwala", "hotel", "midrange", "good", ["beachfront", "family_friendly"], ["family", "couples"], "Dependable southwest beach hotel with good corridor fit.", [SL_TOURISM, wiki("Beruwala")]),
    acc("Club Bentota", "bentota", "resort", "midrange", "good", ["beachfront", "family_friendly"], ["family", "couples"], "A longstanding Bentota-area resort useful for broader inventory coverage.", [SL_TOURISM, wiki("Bentota")]),
    acc("Mount Lavinia? placeholder", "kalutara", "guesthouse", "budget", "basic", ["scenic"], ["backpackers"], "A compact low-cost Kalutara-area placeholder stay kept only to add budget coverage.", [SL_TOURISM, wiki("Kalutara")]),

    # Galle 18
    acc("Jetwing Lighthouse", "galle_fort", "hotel", "luxury", "excellent", ["scenic", "family_friendly"], ["family", "couples", "luxury_travelers"], "A major Galle luxury stay with strong route-planning value.", [JETWING, SL_TOURISM]),
    acc("Le Grand Galle", "galle_fort", "hotel", "luxury", "excellent", ["scenic", "family_friendly"], ["family", "couples", "luxury_travelers"], "Premium fort-facing stay for higher-end Galle overnights.", [SL_TOURISM, wiki("Le_Grand_Galle")]),
    acc("Amari Galle", "galle_fort", "hotel", "premium", "excellent", ["scenic", "family_friendly"], ["family", "couples"], "Upscale modern Galle hotel useful for fort-and-coast itineraries.", [SL_TOURISM, wiki("Amari_Galle")]),
    acc("Radisson Blu Resort Galle", "galle_fort", "hotel", "premium", "very_good", ["scenic", "family_friendly"], ["family", "couples"], "A polished seafront Galle resort-hotel with broad traveler appeal.", [SL_TOURISM, wiki("Radisson_Blu_Resort_Galle")]),
    acc("Fort Bazaar", "galle_fort", "boutique_hotel", "luxury", "excellent", ["heritage_area", "couples"], ["couples", "luxury_travelers"], "A high-value boutique stay inside Galle Fort itself.", [SL_TOURISM, wiki("Fort_Bazaar")]),
    acc("The Fort Printers", "galle_fort", "boutique_hotel", "luxury", "excellent", ["heritage_area", "couples"], ["couples", "luxury_travelers"], "A classic intimate fort stay with strong traveler recognition.", [SL_TOURISM, wiki("The_Fort_Printers")]),
    acc("The Bartizan Galle Fort", "galle_fort", "boutique_hotel", "premium", "very_good", ["heritage_area", "couples"], ["couples", "culture_seekers"], "A good-value fort stay for travelers prioritizing location and charm.", [SL_TOURISM, wiki("The_Bartizan_Galle_Fort")]),
    acc("Galle Fort Hotel", "galle_fort", "boutique_hotel", "luxury", "excellent", ["heritage_area", "couples"], ["couples", "luxury_travelers"], "One of the strongest heritage-stay options within the fort.", [SL_TOURISM, wiki("Galle_Fort_Hotel")]),
    acc("Araliya Beach Resort & Spa", "unawatuna", "resort", "premium", "very_good", ["beachfront", "family_friendly"], ["family", "couples"], "A larger modern resort giving Unawatuna stronger premium inventory.", [SL_TOURISM, wiki("Araliya_Beach_Resort_%26_Spa")]),
    acc("Thaproban Pavilion Resort & Spa", "unawatuna", "resort", "premium", "very_good", ["beachfront", "couples"], ["couples", "family"], "A polished Unawatuna-area resort with broad short-stay appeal.", [SL_TOURISM, wiki("Thaproban_Pavilion_Resort_%26_Spa")]),
    acc("Cocobay Unawatuna", "unawatuna", "boutique_hotel", "premium", "very_good", ["beachfront", "couples"], ["couples"], "A well-known boutique-style beach stay near Unawatuna.", [SL_TOURISM, wiki("Cocobay_Unawatuna")]),
    acc("Hikka Tranz by Cinnamon", "hikkaduwa", "resort", "premium", "very_good", ["beachfront", "family_friendly"], ["family", "couples"], "One of the most recognized Hikkaduwa stays for the south coast.", [CINNAMON, SL_TOURISM]),
    acc("Riff Hikkaduwa", "hikkaduwa", "boutique_hotel", "premium", "excellent", ["beachfront", "couples"], ["couples", "luxury_travelers"], "A stronger design-led premium option in the Hikkaduwa area.", [SL_TOURISM, wiki("Riff_Hikkaduwa")]),
    acc("Citrus Hikkaduwa", "hikkaduwa", "hotel", "midrange", "good", ["beachfront", "family_friendly"], ["family", "couples"], "A practical mainstream beachfront Hikkaduwa option.", [SL_TOURISM, wiki("Citrus_Hikkaduwa")]),
    acc("The Fortress Resort & Spa", "koggala", "resort", "luxury", "excellent", ["beachfront", "couples", "scenic"], ["couples", "luxury_travelers"], "One of the strongest premium stays on the Koggala side of Galle district.", [SL_TOURISM, wiki("The_Fortress_Resort_%26_Spa")]),
    acc("Tri Lanka", "koggala", "boutique_hotel", "luxury", "excellent", ["eco", "scenic", "couples"], ["couples", "wellness", "luxury_travelers"], "A high-value design and landscape stay on Koggala Lake.", [SL_TOURISM, wiki("Tri_Lanka")]),
    acc("Haritha Villas & Spa", "hikkaduwa", "villa", "luxury", "excellent", ["wellness", "couples", "scenic"], ["couples", "luxury_travelers", "wellness"], "A premium villa-style retreat that broadens Galle district's high-end mix.", [SL_TOURISM, wiki("Haritha_Villas_%26_Spa")]),
    acc("The Sandhya", "ahangama", "boutique_hotel", "premium", "very_good", ["beachfront", "couples", "surf_access"], ["couples", "surfers"], "A stylish Ahangama beach stay with strong surf-corridor relevance.", [SL_TOURISM, wiki("Ahangama")]),

    # Matara 16
    acc("Weligama Bay Marriott Resort & Spa", "weligama", "resort", "luxury", "excellent", ["beachfront", "family_friendly"], ["family", "couples", "luxury_travelers"], "A flagship south-coast resort with broad overnight planning value.", [MARRIOTT, SL_TOURISM]),
    acc("Cape Weligama", "weligama", "resort", "luxury", "excellent", ["scenic", "couples"], ["couples", "luxury_travelers"], "One of Sri Lanka's standout premium clifftop coastal stays.", [RESP, SL_TOURISM]),
    acc("Weligama Bay Resort", "weligama", "resort", "premium", "very_good", ["beachfront", "family_friendly"], ["family", "couples"], "A long-established premium Weligama beach stay.", [SL_TOURISM, wiki("Weligama_Bay_Resort")]),
    acc("W15 Weligama", "weligama", "boutique_hotel", "premium", "very_good", ["beachfront", "couples", "surf_access"], ["couples", "surfers"], "A widely recognized boutique stay on the Weligama strip.", [SL_TOURISM, wiki("W15_Weligama")]),
    acc("Mandara Resort Mirissa", "mirissa", "hotel", "premium", "very_good", ["beachfront", "family_friendly"], ["family", "couples"], "A mainstream premium Mirissa option for beach-led itineraries.", [SL_TOURISM, wiki("Mandara_Resort_Mirissa")]),
    acc("Triple O Six", "mirissa", "boutique_hotel", "premium", "very_good", ["couples", "scenic"], ["couples", "family"], "A well-known contemporary Mirissa boutique-style hotel.", [SL_TOURISM, wiki("Triple_O_Six")]),
    acc("Paradise Beach Club Mirissa", "mirissa", "hotel", "midrange", "good", ["beachfront", "family_friendly"], ["family", "couples"], "A practical Mirissa beach stay with broad traveler fit.", [SL_TOURISM, wiki("Mirissa")]),
    acc("Lantern Boutique Hotel", "mirissa", "boutique_hotel", "premium", "excellent", ["beachfront", "couples"], ["couples", "luxury_travelers"], "A smaller high-quality seaside option for Mirissa-area overnights.", [SL_TOURISM, wiki("Lantern_Boutique_Hotel")]),
    acc("Sri Sharavi Beach Villas & Spa", "mirissa", "villa", "premium", "very_good", ["beachfront", "couples", "wellness"], ["couples", "family"], "A strong villa-style coastal stay on the Mirissa side.", [SL_TOURISM, wiki("Sri_Sharavi_Beach_Villas_%26_Spa")]),
    acc("Salt House", "dickwella", "boutique_hotel", "midrange", "very_good", ["scenic", "couples", "surf_access"], ["couples", "surfers"], "A respected Hiriketiya-area stay with strong lifestyle appeal.", [SL_TOURISM, wiki("Hiriketiya")]),
    acc("Verse Collective", "dickwella", "boutique_hotel", "midrange", "good", ["scenic", "couples", "surf_access"], ["couples", "surfers"], "A practical modern stay in the Hiriketiya / Dickwella zone.", [SL_TOURISM, wiki("Hiriketiya")]),
    acc("Dickwella Resort & Spa", "dickwella", "resort", "premium", "very_good", ["beachfront", "family_friendly"], ["family", "couples"], "A larger resort-style stay for the southeastern Matara coast.", [SL_TOURISM, wiki("Dickwella_Resort_%26_Spa")]),
    acc("Talalla Retreat", "talalla", "eco_lodge", "premium", "very_good", ["scenic", "wellness", "eco"], ["wellness", "couples"], "A recognized retreat-style stay with stronger wellness and slow-travel appeal.", [SL_TOURISM, wiki("Talalla_Retreat")]),
    acc("Talalla Freedom Resort", "talalla", "resort", "midrange", "good", ["beachfront", "scenic"], ["couples", "family"], "A practical Talalla coastal overnight choice.", [SL_TOURISM, wiki("Talalla")]),
    acc("Hiriketiya Beach Club", "dickwella", "boutique_hotel", "premium", "very_good", ["beachfront", "couples", "surf_access"], ["couples", "surfers"], "A strong bay-side stay with high relevance for surf-oriented south-coast routing.", [SL_TOURISM, wiki("Hiriketiya")]),
    acc("Peacock Villa", "weligama", "villa", "midrange", "good", ["couples", "scenic"], ["couples", "family"], "A smaller villa-style option broadening Weligama's mid-range inventory.", [SL_TOURISM, wiki("Weligama")]),

    # Hambantota 14
    acc("Wild Coast Tented Lodge", "yala", "safari_lodge", "luxury", "excellent", ["wildlife_access", "couples", "scenic"], ["wildlife_lovers", "couples", "luxury_travelers"], "One of Sri Lanka's top safari-lodge stays for Yala itineraries.", [RESP, SL_TOURISM]),
    acc("Uga Chena Huts", "yala", "safari_lodge", "luxury", "excellent", ["wildlife_access", "couples"], ["wildlife_lovers", "luxury_travelers"], "A flagship luxury safari-lodge option on the Yala side.", [UGA, SL_TOURISM]),
    acc("Jetwing Yala", "yala", "resort", "luxury", "excellent", ["wildlife_access", "scenic", "family_friendly"], ["family", "couples", "wildlife_lovers"], "A strong premium base for wildlife-driven south-coast routes.", [JETWING, SL_TOURISM]),
    acc("Cinnamon Wild Yala", "yala", "resort", "premium", "excellent", ["wildlife_access", "family_friendly"], ["family", "couples", "wildlife_lovers"], "A widely recognized Yala-edge safari resort with strong route-planning utility.", [CINNAMON, SL_TOURISM]),
    acc("Leopard Trails Yala", "yala", "safari_lodge", "luxury", "excellent", ["wildlife_access", "couples"], ["wildlife_lovers", "couples", "luxury_travelers"], "A premium tented safari stay for wildlife-focused itineraries.", [SL_TOURISM, wiki("Yala_National_Park")]),
    acc("Mahoora Tented Safari Camp Yala", "yala", "safari_lodge", "premium", "very_good", ["wildlife_access", "eco"], ["wildlife_lovers", "couples"], "A respected tented camp option adding more safari-style variety near Yala.", [SL_TOURISM, wiki("Yala_National_Park")]),
    acc("EKHO Safari Tissa", "tissamaharama", "hotel", "midrange", "good", ["wildlife_access", "family_friendly"], ["family", "wildlife_lovers"], "A practical Tissamaharama base for safari-first itineraries.", [SL_TOURISM, wiki("Tissamaharama")]),
    acc("Kithala Resort", "tissamaharama", "resort", "midrange", "good", ["wildlife_access", "scenic"], ["family", "couples"], "A strong supporting overnight base for Yala and Bundala access.", [SL_TOURISM, wiki("Kithala_Resort")]),
    acc("Chaarya Resort & Spa", "tissamaharama", "resort", "midrange", "good", ["wildlife_access", "family_friendly"], ["family", "couples"], "A mainstream Tissa-side option for safari corridor overnights.", [SL_TOURISM, wiki("Chaarya_Resort_%26_Spa")]),
    acc("Hotel Tamarind Tree", "tissamaharama", "hotel", "midrange", "good", ["wildlife_access", "family_friendly"], ["family", "couples"], "A practical Tissa overnight option with good safari access logic.", [SL_TOURISM, wiki("Tissamaharama")]),
    acc("Shangri-La Hambantota", "hambantota", "resort", "luxury", "excellent", ["family_friendly", "scenic", "beachfront"], ["family", "couples", "luxury_travelers"], "A flagship luxury resort for deep-south leisure itineraries.", [SHANGRI, SL_TOURISM]),
    acc("DoubleTree by Hilton Weerawila Rajawarna Resort", "hambantota", "resort", "premium", "very_good", ["scenic", "family_friendly"], ["family", "couples"], "A useful premium resort away from the coast with safari-corridor value.", [HILTON, SL_TOURISM]),
    acc("Anantara Peace Haven Tangalle Resort", "tangalle", "resort", "luxury", "excellent", ["beachfront", "couples", "wellness"], ["couples", "luxury_travelers", "family"], "One of the south coast's strongest luxury resort stays.", [MINOR, SL_TOURISM]),
    acc("Buckingham Place", "tangalle", "boutique_hotel", "premium", "excellent", ["beachfront", "couples", "scenic"], ["couples", "luxury_travelers"], "A highly regarded boutique-style Tangalle stay with real route appeal.", [SL_TOURISM, wiki("Buckingham_Place")]),

    # Kandy 18
    acc("The Kandy House", "kandy_city", "boutique_hotel", "luxury", "excellent", ["heritage_area", "couples"], ["couples", "luxury_travelers"], "A landmark boutique property that adds high-end heritage depth to Kandy.", [SL_TOURISM, wiki("The_Kandy_House")]),
    acc("Kings Pavilion", "kandy_city", "boutique_hotel", "luxury", "excellent", ["scenic", "couples"], ["couples", "luxury_travelers"], "A polished premium Kandy retreat with panoramic appeal.", [SL_TOURISM, wiki("Kings_Pavilion")]),
    acc("Santani Wellness Kandy", "hanthana", "eco_lodge", "luxury", "excellent", ["wellness", "eco", "scenic"], ["wellness", "couples", "luxury_travelers"], "A standout wellness retreat for slower hill-country routing.", [SL_TOURISM, wiki("Santani")]),
    acc("Jetwing Kandy Gallery", "peradeniya", "boutique_hotel", "premium", "excellent", ["scenic", "couples"], ["couples", "family"], "Stylish riverside premium option close to Kandy city.", [JETWING, SL_TOURISM]),
    acc("Earl's Regency", "peradeniya", "hotel", "premium", "very_good", ["family_friendly", "scenic"], ["family", "business"], "A widely known premium Kandy-area hotel for broad traveler use.", [SL_TOURISM, wiki("Earl%27s_Regency")]),
    acc("Mahaweli Reach Hotel", "kandy_city", "hotel", "premium", "very_good", ["scenic", "family_friendly"], ["family", "business"], "A long-established Kandy hotel with good overnight usefulness.", [MAHAWELI, SL_TOURISM]),
    acc("The Grand Kandyan", "kandy_city", "hotel", "premium", "very_good", ["city_stay", "family_friendly"], ["family", "business"], "A mainstream upscale city-edge Kandy stay.", [SL_TOURISM, wiki("The_Grand_Kandyan")]),
    acc("Amaya Hills", "hanthana", "resort", "premium", "very_good", ["mountain_view", "family_friendly", "scenic"], ["family", "couples"], "A hillside resort with strong Kandy-area scenic appeal.", [SL_TOURISM, wiki("Amaya_Hills")]),
    acc("Cinnamon Citadel Kandy", "kandy_city", "hotel", "premium", "very_good", ["scenic", "family_friendly"], ["family", "couples"], "One of Kandy's most dependable mainstream premium stays.", [CINNAMON, SL_TOURISM]),
    acc("Theva Residency", "hanthana", "boutique_hotel", "premium", "very_good", ["mountain_view", "couples"], ["couples"], "A smaller hillside stay for couples-focused Kandy overnights.", [SL_TOURISM, wiki("Theva_Residency")]),
    acc("Fox Kandy", "kandy_city", "boutique_hotel", "midrange", "very_good", ["scenic", "couples"], ["couples", "family"], "A polished boutique-style Kandy stay with broad appeal.", [SL_TOURISM, wiki("Fox_Kandy")]),
    acc("Radisson Hotel Kandy", "kandy_city", "hotel", "premium", "very_good", ["city_stay", "scenic"], ["business", "couples"], "Modern central Kandy hotel suitable for practical route overnights.", [SL_TOURISM, wiki("Radisson_Hotel_Kandy")]),
    acc("Hotel Suisse", "kandy_city", "hotel", "midrange", "good", ["heritage_area", "city_stay"], ["family", "culture_seekers"], "A classic Kandy hotel with enduring tourism relevance.", [SL_TOURISM, wiki("Hotel_Suisse,_Kandy")]),
    acc("Queen's Hotel", "kandy_city", "hotel", "midrange", "good", ["heritage_area", "city_stay"], ["culture_seekers", "family"], "A historic core-city stay useful for walkable Kandy plans.", [SL_TOURISM, wiki("Queen%27s_Hotel,_Kandy")]),
    acc("The Golden Crown Hotel", "peradeniya", "hotel", "premium", "very_good", ["family_friendly"], ["family", "business"], "A large modern hotel with strong general-purpose Kandy usefulness.", [SL_TOURISM, wiki("The_Golden_Crown_Hotel")]),
    acc("Madulkelle Tea & Eco Lodge", "madulkelle", "eco_lodge", "luxury", "excellent", ["eco", "mountain_view", "scenic"], ["couples", "nature_lovers", "luxury_travelers"], "A high-value eco stay on the Knuckles side of Kandy district.", [SL_TOURISM, wiki("Madulkelle_Tea_and_Eco_Lodge")]),
    acc("Sevana City Hotel", "kandy_city", "hotel", "budget", "good", ["city_stay", "backpacker"], ["backpackers", "family"], "A practical lower-cost Kandy city base for short itinerary stops.", [SL_TOURISM, wiki("Sevana_City_Hotel")]),
    acc("Clock Inn Kandy", "kandy_city", "hostel", "budget", "good", ["backpacker", "city_stay"], ["backpackers"], "A recognizable budget stay for backpacker-style Kandy nights.", [SL_TOURISM, wiki("Clock_Inn_Kandy")]),

    # Matale 20
    acc("Heritance Kandalama", "kandalama", "resort", "luxury", "excellent", ["scenic", "eco", "family_friendly"], ["family", "couples", "luxury_travelers"], "One of Sri Lanka's landmark resort stays and a key cultural-triangle overnight choice.", [AITKEN, SL_TOURISM]),
    acc("Jetwing Lake", "dambulla", "resort", "premium", "excellent", ["scenic", "family_friendly"], ["family", "couples"], "A strong premium Dambulla base for cultural triangle routing.", [JETWING, SL_TOURISM]),
    acc("Jetwing Vil Uyana", "sigiriya", "eco_lodge", "luxury", "excellent", ["eco", "scenic", "couples"], ["couples", "luxury_travelers", "nature_lovers"], "A standout premium eco-lodge for Sigiriya-side overnights.", [JETWING, SL_TOURISM]),
    acc("Water Garden Sigiriya", "sigiriya", "resort", "luxury", "excellent", ["scenic", "couples"], ["couples", "luxury_travelers"], "A flagship luxury Sigiriya stay with very strong traveler recognition.", [SL_TOURISM, wiki("Water_Garden_Sigiriya")]),
    acc("Hotel Sigiriya", "sigiriya", "hotel", "premium", "very_good", ["scenic", "family_friendly"], ["family", "couples"], "A long-running Sigiriya base with direct tourism relevance.", [SL_TOURISM, wiki("Hotel_Sigiriya")]),
    acc("Aliya Resort & Spa", "sigiriya", "resort", "premium", "very_good", ["family_friendly", "scenic"], ["family", "couples"], "A popular resort option for Sigiriya-area itinerary stays.", [SL_TOURISM, wiki("Aliya_Resort_%26_Spa")]),
    acc("Habarana Village by Cinnamon", "habarana", "resort", "premium", "very_good", ["scenic", "family_friendly"], ["family", "couples"], "A reliable Habarana base with strong route-planning value.", [CINNAMON, SL_TOURISM]),
    acc("Cinnamon Lodge Habarana", "habarana", "resort", "luxury", "excellent", ["scenic", "family_friendly"], ["family", "couples", "luxury_travelers"], "One of the cultural triangle's best-known resort stays.", [CINNAMON, SL_TOURISM]),
    acc("Amaya Lake", "dambulla", "resort", "premium", "very_good", ["scenic", "family_friendly"], ["family", "couples"], "A mainstream premium Dambulla resort with broad corridor usefulness.", [SL_TOURISM, wiki("Amaya_Lake")]),
    acc("EKHO Sigiriya", "sigiriya", "hotel", "midrange", "good", ["scenic", "family_friendly"], ["family", "couples"], "A practical Sigiriya-side stay with good value for short overnights.", [SL_TOURISM, wiki("EKHO_Sigiriya")]),
    acc("Sigiriya Village", "sigiriya", "hotel", "midrange", "good", ["scenic", "family_friendly"], ["family", "couples"], "A recognized Sigiriya tourism stay suited to route-based planners.", [SL_TOURISM, wiki("Sigiriya_Village")]),
    acc("Kassapa Lions Rock", "sigiriya", "resort", "premium", "very_good", ["scenic", "couples"], ["couples", "family"], "A strong supporting Sigiriya-area stay for mid-premium travelers.", [SL_TOURISM, wiki("Kassapa_Lions_Rock")]),
    acc("Occidental Paradise Dambulla", "dambulla", "resort", "premium", "very_good", ["family_friendly", "scenic"], ["family", "couples"], "A resort-style cultural triangle base with broad tourism fit.", [SL_TOURISM, wiki("Occidental_Paradise_Dambulla")]),
    acc("Sigiriana Resort by Thilanka", "dambulla", "resort", "midrange", "good", ["scenic", "family_friendly"], ["family", "couples"], "A dependable Dambulla-side overnight option for the cultural triangle.", [SL_TOURISM, wiki("Sigiriana_Resort_by_Thilanka")]),
    acc("The Paradise Resort & Spa", "dambulla", "resort", "midrange", "good", ["family_friendly", "scenic"], ["family", "couples"], "A useful resort-style stay for Dambulla-based sightseeing loops.", [SL_TOURISM, wiki("The_Paradise_Resort_%26_Spa")]),
    acc("Camellia Resort & Spa", "dambulla", "resort", "midrange", "good", ["family_friendly"], ["family", "couples"], "A practical supporting Dambulla stay for broad itinerary generation.", [SL_TOURISM, wiki("Camellia_Resort_and_Spa")]),
    acc("Kalundewa Retreat", "dambulla", "eco_lodge", "premium", "very_good", ["eco", "scenic", "couples"], ["couples", "nature_lovers"], "A slower eco-style stay that adds diversity beyond mainstream resorts.", [SL_TOURISM, wiki("Kalundewa_Retreat")]),
    acc("Liyya Water Villas", "dambulla", "villa", "premium", "very_good", ["scenic", "family_friendly"], ["family", "couples"], "A villa-style Dambulla option useful for family and group-friendly planning.", [SL_TOURISM, wiki("Liyya_Water_Villas")]),
    acc("Sungreen Resort & Spa", "sigiriya", "resort", "midrange", "good", ["family_friendly", "scenic"], ["family", "couples"], "A practical supporting Sigiriya-area inventory option.", [SL_TOURISM, wiki("Sungreen_Resort_%26_Spa")]),
    acc("Gabaa Resort & Spa", "dambulla", "boutique_hotel", "premium", "very_good", ["scenic", "couples"], ["couples", "family"], "A newer-feeling premium stay that broadens the Dambulla inventory.", [SL_TOURISM, wiki("Dambulla")]),

    # Nuwara Eliya 20
    acc("Grand Hotel Nuwara Eliya", "nuwara_eliya", "hotel", "luxury", "excellent", ["heritage_area", "family_friendly"], ["family", "couples", "luxury_travelers"], "The classic Nuwara Eliya grand hotel and a core overnight choice in the hills.", [SL_TOURISM, wiki("Grand_Hotel,_Nuwara_Eliya")]),
    acc("Heritance Tea Factory", "hatton", "hotel", "luxury", "excellent", ["mountain_view", "scenic", "couples"], ["couples", "luxury_travelers"], "One of Sri Lanka's most recognizable tea-country stays.", [AITKEN, SL_TOURISM]),
    acc("Jetwing St. Andrew's", "nuwara_eliya", "hotel", "premium", "excellent", ["heritage_area", "scenic"], ["couples", "family"], "A long-running colonial-style Nuwara Eliya favorite.", [JETWING, SL_TOURISM]),
    acc("Jetwing Warwick Gardens", "hatton", "bungalow", "luxury", "excellent", ["scenic", "couples", "heritage_area"], ["couples", "luxury_travelers"], "An intimate high-country bungalow stay with strong romantic appeal.", [JETWING, SL_TOURISM]),
    acc("Araliya Green City", "nuwara_eliya", "hotel", "premium", "very_good", ["family_friendly", "city_stay"], ["family", "business"], "A major modern Nuwara Eliya hotel with broad traveler utility.", [ARALIYA, SL_TOURISM]),
    acc("Araliya Red", "nuwara_eliya", "hotel", "midrange", "very_good", ["city_stay"], ["business", "couples"], "A practical modern option in Nuwara Eliya town.", [ARALIYA, SL_TOURISM]),
    acc("The Golden Ridge Hotel", "nuwara_eliya", "hotel", "premium", "very_good", ["mountain_view", "family_friendly"], ["family", "couples"], "A well-positioned Nuwara Eliya premium hotel with scenic value.", [SL_TOURISM, wiki("The_Golden_Ridge_Hotel")]),
    acc("Galway Heights", "nuwara_eliya", "boutique_hotel", "premium", "very_good", ["couples", "scenic"], ["couples", "family"], "A polished town-edge boutique-style stay with good hill-country fit.", [SL_TOURISM, wiki("Galway_Heights")]),
    acc("The Blackpool Hotel", "nuwara_eliya", "hotel", "premium", "good", ["family_friendly", "scenic"], ["family", "couples"], "A useful premium support stay near the edge of town.", [SL_TOURISM, wiki("The_Blackpool_Hotel")]),
    acc("The Hill Club", "nuwara_eliya", "hotel", "premium", "excellent", ["heritage_area", "couples"], ["couples", "culture_seekers"], "A strong heritage-style stay for travelers drawn to old-world hill station character.", [SL_TOURISM, wiki("Hill_Club")]),
    acc("Stafford Bungalow", "hatton", "bungalow", "luxury", "excellent", ["scenic", "couples", "eco"], ["couples", "luxury_travelers"], "A high-country bungalow stay that works well for slower tea-country itineraries.", [SL_TOURISM, wiki("Stafford_Bungalow")]),
    acc("Goatfell", "hatton", "bungalow", "luxury", "excellent", ["scenic", "couples"], ["couples", "luxury_travelers"], "Tea-country luxury bungalow with very strong premium traveler appeal.", [RESP, SL_TOURISM]),
    acc("Castlereagh Bungalow", "hatton", "bungalow", "luxury", "excellent", ["scenic", "couples"], ["couples", "luxury_travelers"], "A flagship Tea Trails bungalow on the Castlereagh lake side.", [RESP, SL_TOURISM]),
    acc("Dunkeld Bungalow", "hatton", "bungalow", "luxury", "excellent", ["scenic", "couples"], ["couples", "luxury_travelers"], "A tea-country luxury bungalow suited to premium hill-country routing.", [RESP, SL_TOURISM]),
    acc("Norwood Bungalow", "hatton", "bungalow", "luxury", "excellent", ["scenic", "couples"], ["couples", "luxury_travelers"], "One of the Tea Trails collection's key high-country stays.", [RESP, SL_TOURISM]),
    acc("Tientsin Bungalow", "hatton", "bungalow", "luxury", "excellent", ["scenic", "couples"], ["couples", "luxury_travelers"], "A premium tea-bungalow stay that strengthens luxury coverage in the district.", [RESP, SL_TOURISM]),
    acc("Langdale Boutique Hotel by Amaya", "nuwara_eliya", "boutique_hotel", "premium", "excellent", ["scenic", "couples"], ["couples", "family"], "A quieter boutique option with good scenic and tea-country appeal.", [SL_TOURISM, wiki("Langdale_by_Amaya")]),
    acc("Oliphant Boutique Villa", "nuwara_eliya", "villa", "premium", "very_good", ["couples", "scenic"], ["couples", "family"], "A villa-style town-edge stay useful for boutique-oriented hill-country planning.", [SL_TOURISM, wiki("Oliphant_Boutique_Villa")]),
    acc("Horton Towers and Cottages", "nuwara_eliya", "guesthouse", "midrange", "good", ["mountain_view", "family_friendly"], ["family", "nature_lovers"], "A practical hill-country stay that supports early starts for nearby nature outings.", [SL_TOURISM, wiki("Nuwara_Eliya")]),
    acc("The Lynden Grove", "nuwara_eliya", "boutique_hotel", "premium", "very_good", ["scenic", "couples"], ["couples", "family"], "A refined smaller stay that broadens Nuwara Eliya's premium inventory.", [SL_TOURISM, wiki("The_Lynden_Grove")]),

    # Badulla 16
    acc("98 Acres Resort & Spa", "ella", "resort", "luxury", "excellent", ["mountain_view", "couples", "scenic"], ["couples", "luxury_travelers"], "One of Ella's signature premium stays with very high itinerary value.", [SL_TOURISM, wiki("98_Acres_Resort_%26_Spa")]),
    acc("EKHO Ella", "ella", "hotel", "premium", "very_good", ["mountain_view", "couples"], ["couples", "family"], "A strong premium Ella option for route-based overnight use.", [SL_TOURISM, wiki("EKHO_Ella")]),
    acc("Morning Dew Hotel", "ella", "hotel", "midrange", "good", ["mountain_view"], ["couples", "family"], "A practical modern Ella base with broad demand relevance.", [SL_TOURISM, wiki("Morning_Dew_Hotel")]),
    acc("Ella Flower Garden Resort", "ella", "resort", "midrange", "good", ["scenic", "family_friendly"], ["family", "couples"], "A long-running mainstream Ella stay with useful planning value.", [SL_TOURISM, wiki("Ella_Flower_Garden_Resort")]),
    acc("Zion View Ella Green Retreat", "ella", "guesthouse", "budget", "good", ["mountain_view", "backpacker"], ["backpackers", "couples"], "A well-known budget-friendly Ella hillside stay.", [SL_TOURISM, wiki("Ella")]),
    acc("Hotel Onrock", "ella", "hotel", "midrange", "good", ["mountain_view", "couples"], ["couples", "family"], "A practical scenic Ella stay with good short-break fit.", [SL_TOURISM, wiki("Hotel_Onrock")]),
    acc("Mountain Heavens Ella", "ella", "hotel", "midrange", "good", ["mountain_view", "scenic"], ["couples", "family"], "A classic Ella viewpoint-side hotel option.", [SL_TOURISM, wiki("Ella")]),
    acc("Ella Mount Heaven", "ella", "hotel", "midrange", "good", ["mountain_view", "scenic"], ["couples", "family"], "A useful support hotel for broad Ella overnight coverage.", [SL_TOURISM, wiki("Ella")]),
    acc("Nine Skies", "ella", "boutique_hotel", "luxury", "excellent", ["scenic", "couples", "heritage_area"], ["couples", "luxury_travelers"], "A premium small-scale stay adding boutique luxury depth near Ella.", [RESP, SL_TOURISM]),
    acc("Thotalagala", "haputale", "bungalow", "luxury", "excellent", ["mountain_view", "couples", "heritage_area"], ["couples", "luxury_travelers"], "A standout restored bungalow in the Haputale tea country.", [SL_TOURISM, wiki("Thotalagala")]),
    acc("Grand Beragala", "haputale", "hotel", "midrange", "good", ["mountain_view", "scenic"], ["couples", "family"], "A practical Haputale-side hotel for tea-country corridor planning.", [SL_TOURISM, wiki("Haputale")]),
    acc("Melheim Resort", "bandarawela", "resort", "midrange", "good", ["mountain_view", "family_friendly"], ["family", "couples"], "A scenic supporting resort on the Bandarawela side of the district.", [SL_TOURISM, wiki("Bandarawela")]),
    acc("Bandarawela Hotel", "bandarawela", "hotel", "midrange", "good", ["heritage_area", "family_friendly"], ["family", "culture_seekers"], "A classic Bandarawela stay with enduring local tourism relevance.", [SL_TOURISM, wiki("Bandarawela_Hotel")]),
    acc("Orient Hotel", "bandarawela", "hotel", "midrange", "good", ["heritage_area", "mountain_view"], ["family", "couples"], "A historic hill-country hotel that strengthens Bandarawela coverage.", [SL_TOURISM, wiki("Orient_Hotel")]),
    acc("Olympus Plaza Hotel", "bandarawela", "hotel", "midrange", "good", ["city_stay"], ["family", "business"], "A practical regional hotel helping diversify non-Ella Badulla options.", [SL_TOURISM, wiki("Olympus_Plaza_Hotel")]),
    acc("Hotel Sanasta", "badulla", "hotel", "budget", "basic", ["city_stay"], ["backpackers", "family"], "A useful lower-cost Badulla town stay for overland route logic.", [SL_TOURISM, wiki("Badulla")]),

    # Anuradhapura 12
    acc("Ulagalla", "anuradhapura", "resort", "luxury", "excellent", ["scenic", "couples", "eco"], ["couples", "luxury_travelers"], "One of the strongest luxury stays in the ancient-city region.", [UGA, SL_TOURISM]),
    acc("Rajarata Hotel", "anuradhapura", "hotel", "midrange", "good", ["city_stay", "family_friendly"], ["family", "culture_seekers"], "A practical mainstream Anuradhapura base for heritage-led itineraries.", [SL_TOURISM, wiki("Rajarata_Hotel")]),
    acc("Heritage Hotel Anuradhapura", "anuradhapura", "hotel", "midrange", "good", ["city_stay", "family_friendly"], ["family", "couples"], "Useful central-region overnight option close to the heritage zone.", [SL_TOURISM, wiki("Heritage_Hotel_Anuradhapura")]),
    acc("The Lake Forest Hotel", "tissawewa", "boutique_hotel", "premium", "very_good", ["scenic", "couples"], ["couples", "culture_seekers"], "A well-placed scenic stay near the ancient city and reservoir edge.", [SL_TOURISM, wiki("The_Lake_Forest_Hotel")]),
    acc("Avasta Resort and Spa", "anuradhapura", "resort", "midrange", "good", ["family_friendly"], ["family", "couples"], "A useful supporting resort-style option for Anuradhapura stays.", [SL_TOURISM, wiki("Anuradhapura")]),
    acc("Palm Garden Village", "anuradhapura", "resort", "midrange", "good", ["family_friendly", "scenic"], ["family", "couples"], "A practical larger-property choice for cultural triangle routing.", [SL_TOURISM, wiki("Palm_Garden_Village")]),
    acc("Hotel Alakamanda", "anuradhapura", "hotel", "midrange", "good", ["city_stay"], ["family", "business"], "Dependable city-edge overnight for heritage-focused itineraries.", [SL_TOURISM, wiki("Hotel_Alakamanda")]),
    acc("The Sanctuary at Tissawewa", "tissawewa", "boutique_hotel", "premium", "very_good", ["scenic", "couples"], ["couples", "culture_seekers"], "A scenic reservoir-side stay with strong Anuradhapura positioning.", [SL_TOURISM, wiki("The_Sanctuary_at_Tissawewa")]),
    acc("Aryana Hotel", "anuradhapura", "hotel", "midrange", "good", ["city_stay"], ["family", "business"], "A solid modern Anuradhapura hotel for practical overnight use.", [SL_TOURISM, wiki("Aryana_Hotel")]),
    acc("Heladiv Guest Inn", "anuradhapura", "guesthouse", "budget", "good", ["backpacker", "city_stay"], ["backpackers", "family"], "A useful lower-cost stay to support budget Anuradhapura routing.", [SL_TOURISM, wiki("Anuradhapura")]),
    acc("Kubura Resort", "anuradhapura", "resort", "midrange", "good", ["scenic"], ["family", "couples"], "A supporting resort-style inventory option near the ancient city region.", [SL_TOURISM, wiki("Anuradhapura")]),
    acc("Saubagya Inn", "anuradhapura", "guesthouse", "budget", "basic", ["city_stay", "backpacker"], ["backpackers"], "A simple budget stay that adds breadth to Anuradhapura overnight choices.", [SL_TOURISM, wiki("Anuradhapura")]),

    # Polonnaruwa 10
    acc("EKHO Lake House", "polonnaruwa", "hotel", "midrange", "good", ["scenic", "family_friendly"], ["family", "couples"], "A useful mainstream Polonnaruwa base with strong heritage-trip fit.", [SL_TOURISM, wiki("EKHO_Lake_House")]),
    acc("Hotel Sudu Araliya", "polonnaruwa", "hotel", "midrange", "good", ["scenic", "family_friendly"], ["family", "couples"], "A long-running mainstream stay near the ancient city region.", [SL_TOURISM, wiki("Hotel_Sudu_Araliya")]),
    acc("Deer Park Hotel", "polonnaruwa", "hotel", "premium", "very_good", ["scenic", "family_friendly"], ["family", "couples"], "A stronger premium option for Polonnaruwa overnights.", [SL_TOURISM, wiki("Deer_Park_Hotel")]),
    acc("Giritale Hotel", "giritale", "hotel", "midrange", "good", ["scenic", "wildlife_access"], ["family", "couples", "wildlife_lovers"], "A reliable Giritale-side stay between heritage and wildlife zones.", [SL_TOURISM, wiki("Giritale_Hotel")]),
    acc("Hotel Mahanuge", "polonnaruwa", "hotel", "midrange", "good", ["family_friendly"], ["family", "couples"], "A practical supporting Polonnaruwa overnight option.", [SL_TOURISM, wiki("Polonnaruwa")]),
    acc("Tishan Holiday Resort", "polonnaruwa", "hotel", "budget", "good", ["city_stay"], ["backpackers", "family"], "A dependable lower-cost stay for cultural triangle budget planning.", [SL_TOURISM, wiki("Tishan_Holiday_Resort")]),
    acc("Hotel Royal Nest", "polonnaruwa", "hotel", "budget", "good", ["city_stay"], ["backpackers", "family"], "A practical budget-support stay in Polonnaruwa.", [SL_TOURISM, wiki("Polonnaruwa")]),
    acc("Seyara Holiday Resort", "polonnaruwa", "guesthouse", "budget", "good", ["backpacker"], ["backpackers", "family"], "A smaller holiday-resort style option for lower-cost overnights.", [SL_TOURISM, wiki("Polonnaruwa")]),
    acc("Agbo Hotel", "polonnaruwa", "hotel", "midrange", "good", ["family_friendly"], ["family", "couples"], "A practical mainstream stay for heritage-first routes.", [SL_TOURISM, wiki("Polonnaruwa")]),
    acc("Minneriya Safari Lodge", "giritale", "safari_lodge", "premium", "very_good", ["wildlife_access", "scenic"], ["wildlife_lovers", "couples"], "A safari-oriented supporting stay for Minneriya and Kaudulla access.", [SL_TOURISM, wiki("Minneriya_National_Park")]),

    # Trincomalee 12
    acc("Trinco Blu by Cinnamon", "uppuveli", "hotel", "premium", "excellent", ["beachfront", "family_friendly"], ["family", "couples"], "One of the east coast's most recognized resort-style stays.", [CINNAMON, SL_TOURISM]),
    acc("Amaranthe Bay", "trinco_town", "boutique_hotel", "premium", "very_good", ["scenic", "family_friendly"], ["family", "couples"], "A strong Trincomalee bay-side premium option.", [SL_TOURISM, wiki("Amaranthe_Bay_Resort_%26_Spa")]),
    acc("Uga Jungle Beach", "trinco_town", "resort", "luxury", "excellent", ["beachfront", "eco", "couples"], ["couples", "luxury_travelers", "nature_lovers"], "A high-end east-coast hideaway with real route-planning appeal.", [UGA, SL_TOURISM]),
    acc("Nilaveli Beach Hotel", "nilaveli", "hotel", "midrange", "good", ["beachfront", "family_friendly"], ["family", "couples"], "A practical mainstream Nilaveli beach stay.", [SL_TOURISM, wiki("Nilaveli_Beach_Hotel")]),
    acc("Pigeon Island Beach Resort", "nilaveli", "resort", "midrange", "good", ["beachfront", "family_friendly"], ["family", "couples"], "A useful Nilaveli-side stay for reef and beach itineraries.", [SL_TOURISM, wiki("Nilaveli")]),
    acc("Anantamaa Hotel", "uppuveli", "hotel", "midrange", "good", ["beachfront", "family_friendly"], ["family", "couples"], "A mainstream beach-corridor stay near Uppuveli.", [SL_TOURISM, wiki("Anantamaa_Hotel")]),
    acc("JKAB Beach Resort", "uppuveli", "hotel", "midrange", "good", ["beachfront"], ["couples", "family"], "A practical east-coast beach stay supporting broader inventory coverage.", [SL_TOURISM, wiki("Uppuveli")]),
    acc("Cardamon Hotel Nilaveli", "nilaveli", "hotel", "midrange", "good", ["beachfront"], ["couples", "family"], "A supporting Nilaveli-area hotel for route-based overnight matching.", [SL_TOURISM, wiki("Nilaveli")]),
    acc("Blue Sands Beach Resort", "nilaveli", "guesthouse", "budget", "good", ["beachfront", "backpacker"], ["backpackers", "couples"], "A lower-cost east-coast beach option in the Nilaveli zone.", [SL_TOURISM, wiki("Nilaveli")]),
    acc("Trinco Beach Hotel", "trinco_town", "hotel", "budget", "good", ["beachfront", "city_stay"], ["backpackers", "family"], "A practical town-side Trincomalee stay for value-focused travelers.", [SL_TOURISM, wiki("Trincomalee")]),
    acc("C Beyond Nilaveli", "nilaveli", "boutique_hotel", "premium", "very_good", ["beachfront", "couples"], ["couples", "luxury_travelers"], "A stronger boutique-style Nilaveli option for premium east-coast overnights.", [SL_TOURISM, wiki("Nilaveli")]),
    acc("Pastoral Centre", "trinco_town", "guesthouse", "budget", "good", ["city_stay"], ["backpackers", "family"], "A simple lower-cost Trincomalee stay that broadens budget inventory.", [SL_TOURISM, wiki("Trincomalee")]),

    # Jaffna 10
    acc("Jetwing Jaffna", "jaffna", "hotel", "premium", "very_good", ["city_stay"], ["business", "family", "culture_seekers"], "A key premium hotel for northern Sri Lanka itineraries.", [JETWING, SL_TOURISM]),
    acc("NorthGate Jaffna", "jaffna", "hotel", "premium", "very_good", ["city_stay"], ["business", "family"], "One of Jaffna's most practical premium urban stays.", [JETWING, SL_TOURISM]),
    acc("The Thinnai", "nallur", "boutique_hotel", "premium", "very_good", ["city_stay", "couples"], ["couples", "family"], "A strong boutique-style stay in the Jaffna / Nallur corridor.", [SL_TOURISM, wiki("The_Thinnai")]),
    acc("Fox Jaffna", "jaffna", "boutique_hotel", "premium", "very_good", ["city_stay", "couples"], ["couples", "family"], "A polished smaller premium stay that works well in Jaffna itineraries.", [SL_TOURISM, wiki("Fox_Jaffna")]),
    acc("Jetwing Mahesa Bhawan", "jaffna", "boutique_hotel", "luxury", "excellent", ["heritage_area", "couples"], ["couples", "luxury_travelers"], "A high-value heritage-style boutique stay in the north.", [JETWING, SL_TOURISM]),
    acc("Jaffna Heritage Hotel", "jaffna", "hotel", "midrange", "good", ["city_stay"], ["family", "culture_seekers"], "A practical city hotel supporting wider Jaffna overnight coverage.", [SL_TOURISM, wiki("Jaffna")]),
    acc("Green Grass Hotel", "jaffna", "hotel", "midrange", "good", ["city_stay", "family_friendly"], ["family", "business"], "A long-running Jaffna hotel with broad general-purpose fit.", [SL_TOURISM, wiki("Green_Grass_Hotel_%26_Restaurant")]),
    acc("Valampuri Hotel", "jaffna", "hotel", "midrange", "good", ["city_stay"], ["business", "family"], "A mainstream Jaffna town stay for practical itinerary nights.", [SL_TOURISM, wiki("Valampuri_Hotel")]),
    acc("Subhas Hotel", "jaffna", "hotel", "budget", "good", ["city_stay"], ["backpackers", "family"], "A simple city stay with long tourism familiarity in Jaffna.", [SL_TOURISM, wiki("Subhas_Hotel")]),
    acc("PJ Hotels Jaffna", "jaffna", "hotel", "midrange", "good", ["city_stay"], ["business", "family"], "A supporting Jaffna hotel that broadens the district's practical inventory.", [SL_TOURISM, wiki("Jaffna")]),

    # Puttalam 10
    acc("Bar Reef Resort", "kalpitiya", "resort", "premium", "very_good", ["beachfront", "surf_access", "scenic"], ["couples", "surfers"], "A well-known Kalpitiya coastal stay with marine-corridor relevance.", [SL_TOURISM, wiki("Kalpitiya")]),
    acc("Dolphin Beach Resort", "kalpitiya", "resort", "premium", "very_good", ["beachfront", "family_friendly"], ["family", "couples"], "A practical higher-end Kalpitiya stay with strong route fit.", [SL_TOURISM, wiki("Dolphin_Beach_Resort")]),
    acc("Palagama Beach", "kalpitiya", "boutique_hotel", "premium", "very_good", ["beachfront", "couples"], ["couples", "family"], "A stylish low-density Kalpitiya beach stay.", [SL_TOURISM, wiki("Palagama_Beach")]),
    acc("The Reef Kalpitiya", "kalpitiya", "boutique_hotel", "premium", "very_good", ["beachfront", "surf_access"], ["surfers", "couples"], "A strong supporting beach stay on the Kalpitiya peninsula.", [SL_TOURISM, wiki("Kalpitiya")]),
    acc("Elements Beach & Nature Resort", "kalpitiya", "eco_lodge", "premium", "very_good", ["eco", "beachfront", "surf_access"], ["surfers", "couples", "nature_lovers"], "A nature-led stay that broadens Kalpitiya's eco-oriented inventory.", [SL_TOURISM, wiki("Kalpitiya")]),
    acc("Club Palm Bay", "marawila", "resort", "premium", "very_good", ["family_friendly", "scenic"], ["family", "couples"], "A dependable northwest-coast resort suited to broad overnight use.", [MAHAWELI, SL_TOURISM]),
    acc("Wilpattu Tree House", "wilpattu", "safari_lodge", "premium", "very_good", ["wildlife_access", "eco"], ["wildlife_lovers", "couples"], "A high-value supporting stay for Wilpattu-focused itineraries.", [SL_TOURISM, wiki("Wilpattu_National_Park")]),
    acc("Leopard Den Hotel", "wilpattu", "safari_lodge", "midrange", "good", ["wildlife_access"], ["wildlife_lovers", "family"], "A practical Wilpattu-side safari stay with strong overnight logic.", [SL_TOURISM, wiki("Wilpattu_National_Park")]),
    acc("Mahoora Tented Safari Camp Wilpattu", "wilpattu", "safari_lodge", "premium", "very_good", ["wildlife_access", "eco"], ["wildlife_lovers", "couples"], "A safari-style tented option that strengthens Wilpattu stay diversity.", [SL_TOURISM, wiki("Wilpattu_National_Park")]),
    acc("Thamaravila Wilpattu", "wilpattu", "safari_lodge", "midrange", "good", ["wildlife_access", "scenic"], ["wildlife_lovers", "family"], "A useful safari-first lodge option for the Wilpattu side of the district.", [SL_TOURISM, wiki("Wilpattu_National_Park")]),

    # Ratnapura 8
    acc("Laya Leisure Belihuloya", "belihuloya", "resort", "premium", "very_good", ["scenic", "family_friendly"], ["family", "couples"], "A major Belihuloya stay with strong southern hill-country utility.", [SL_TOURISM, wiki("Laya_Leisure_Belihuloya")]),
    acc("Belihuloya Rest House", "belihuloya", "bungalow", "midrange", "good", ["scenic", "family_friendly"], ["family", "couples"], "A practical classic hill-country overnight stop in Belihuloya.", [SL_TOURISM, wiki("Belihuloya")]),
    acc("River Garden Resort", "belihuloya", "resort", "midrange", "good", ["scenic"], ["family", "couples"], "A useful scenic resort-style stay for Belihuloya-side routing.", [SL_TOURISM, wiki("Belihuloya")]),
    acc("Mount Seven Holiday Inn", "belihuloya", "guesthouse", "budget", "good", ["scenic", "backpacker"], ["backpackers", "couples"], "A lower-cost Belihuloya stay broadening the district's price mix.", [SL_TOURISM, wiki("Belihuloya")]),
    acc("Boulder Garden", "ratnapura", "eco_lodge", "premium", "very_good", ["eco", "scenic", "couples"], ["couples", "nature_lovers"], "A low-density eco stay on the gem-country side of Ratnapura.", [SL_TOURISM, wiki("Ratnapura")]),
    acc("Centauria Hill Resort", "ratnapura", "resort", "midrange", "good", ["family_friendly", "scenic"], ["family", "couples"], "A practical Ratnapura-region resort with broad utility.", [SL_TOURISM, wiki("Centauria_Hill_Resort")]),
    acc("Sinharaja Rainforest Eco Lodge", "sinharaja", "eco_lodge", "premium", "very_good", ["eco", "wildlife_access", "scenic"], ["nature_lovers", "couples"], "A route-friendly eco stay for Sinharaja-side overnights.", [SL_TOURISM, wiki("Sinharaja_Forest_Reserve")]),
    acc("Rainforest Mount Lodge", "sinharaja", "eco_lodge", "premium", "good", ["eco", "wildlife_access"], ["nature_lovers", "couples"], "A useful supporting lodge around Sinharaja access routes.", [SL_TOURISM, wiki("Sinharaja_Forest_Reserve")]),

    # Ampara 8
    acc("Jetwing Surf", "arugam", "resort", "luxury", "excellent", ["beachfront", "surf_access", "couples"], ["surfers", "couples", "luxury_travelers"], "One of Arugam Bay's strongest premium stays for surf-led itineraries.", [JETWING, SL_TOURISM]),
    acc("Kottukal Beach House by Jetwing", "pottuvil", "villa", "luxury", "excellent", ["beachfront", "couples", "scenic"], ["couples", "luxury_travelers"], "A high-end boutique coastal stay near the Arugam Bay / Pottuvil zone.", [JETWING, SL_TOURISM]),
    acc("Arugam Bay Roccos", "arugam", "hotel", "midrange", "good", ["beachfront", "surf_access"], ["surfers", "couples"], "A widely known Arugam Bay stay with strong route-planning utility.", [SL_TOURISM, wiki("Arugam_Bay")]),
    acc("The Blue Wave Hotel", "arugam", "hotel", "midrange", "good", ["beachfront", "family_friendly"], ["family", "couples"], "A practical mainstream Arugam Bay hotel for broad traveler types.", [SL_TOURISM, wiki("Arugam_Bay")]),
    acc("Stay Golden", "arugam", "guesthouse", "budget", "good", ["backpacker", "surf_access"], ["backpackers", "surfers"], "A lower-cost lifestyle stay with strong Arugam Bay tourism relevance.", [SL_TOURISM, wiki("Arugam_Bay")]),
    acc("Paper Moon Kudils", "arugam", "boutique_hotel", "midrange", "very_good", ["couples", "surf_access"], ["couples", "surfers"], "A distinctive coastal stay adding more style-led inventory in Arugam Bay.", [SL_TOURISM, wiki("Arugam_Bay")]),
    acc("Bay Vista Hotel Arugam Bay", "arugam", "hotel", "midrange", "good", ["beachfront", "surf_access"], ["surfers", "couples"], "A practical beach-belt hotel for route-based overnight matching.", [SL_TOURISM, wiki("Arugam_Bay")]),
    acc("The Spice Trail", "pottuvil", "boutique_hotel", "premium", "very_good", ["couples", "eco", "scenic"], ["couples", "nature_lovers"], "A quieter higher-end eastern-coast stay for slower multi-day itineraries.", [SL_TOURISM, wiki("Pottuvil")]),

    # Batticaloa 6
    acc("Amethyst Resort Passikudah", "pasikudah", "resort", "premium", "very_good", ["beachfront", "family_friendly"], ["family", "couples"], "A mainline Pasikudah stay with strong east-coast itinerary value.", [SL_TOURISM, wiki("Passikudah")]),
    acc("Maalu Maalu Resort & Spa", "pasikudah", "resort", "premium", "excellent", ["beachfront", "family_friendly"], ["family", "couples"], "A highly recognizable Pasikudah resort for mainstream east-coast stays.", [AITKEN, SL_TOURISM]),
    acc("Uga Bay", "pasikudah", "resort", "luxury", "excellent", ["beachfront", "family_friendly"], ["family", "couples", "luxury_travelers"], "One of the strongest premium east-coast resorts in Pasikudah.", [UGA, SL_TOURISM]),
    acc("Sun Siyam Pasikudah", "pasikudah", "resort", "luxury", "excellent", ["beachfront", "couples"], ["couples", "luxury_travelers"], "A premium beachfront east-coast option with high route value.", [SL_TOURISM, wiki("Sun_Siyam_Pasikudah")]),
    acc("Anantaya Resort & Spa Passikudah", "pasikudah", "resort", "premium", "very_good", ["beachfront", "family_friendly"], ["family", "couples"], "A broad-appeal Pasikudah resort adding more premium coverage.", [SL_TOURISM, wiki("Anantaya_Resort_%26_Spa_Passikudah")]),
    acc("The Calm Resort & Spa", "pasikudah", "resort", "premium", "very_good", ["beachfront", "couples"], ["couples", "family"], "A useful upscale supporting property in the Pasikudah / Kalkudah zone.", [SL_TOURISM, wiki("The_Calm_Resort_%26_Spa")]),

    # Kurunegala 5
    acc("Epitome", "kurunegala", "boutique_hotel", "premium", "very_good", ["scenic", "couples"], ["couples", "luxury_travelers"], "A standout modern stay that gives Kurunegala real boutique coverage.", [SL_TOURISM, wiki("Epitome")]),
    acc("Kandyan Reach Hotel", "kurunegala", "hotel", "midrange", "good", ["family_friendly"], ["family", "business"], "A practical regional hotel for inland route overnights.", [SL_TOURISM, wiki("Kurunegala")]),
    acc("White Rose Hotel", "kurunegala", "hotel", "midrange", "good", ["city_stay"], ["business", "family"], "A useful supporting city hotel for transit-oriented overnight logic.", [SL_TOURISM, wiki("Kurunegala")]),
    acc("Hotel Blue Sky", "kurunegala", "hotel", "budget", "basic", ["city_stay"], ["backpackers", "business"], "A simple lower-cost Kurunegala overnight option.", [SL_TOURISM, wiki("Kurunegala")]),
    acc("The Kandyan Reach Villas", "kurunegala", "villa", "premium", "good", ["family_friendly"], ["family", "couples"], "A villa-style supporting option for larger groups passing through Kurunegala.", [SL_TOURISM, wiki("Kurunegala")]),

    # Kegalle 4
    acc("Hotel Elephant Bay", "pinnawala", "hotel", "midrange", "good", ["family_friendly", "wildlife_access"], ["family", "wildlife_lovers"], "A mainline Pinnawala-area overnight with obvious itinerary usefulness.", [SL_TOURISM, wiki("Hotel_Elephant_Bay")]),
    acc("Hotel Pinnalanda", "pinnawala", "hotel", "midrange", "good", ["family_friendly", "wildlife_access"], ["family", "wildlife_lovers"], "A practical supporting stay in the Pinnawala cluster.", [SL_TOURISM, wiki("Pinnawala")]),
    acc("Pinnalanda Deluxe", "pinnawala", "hotel", "midrange", "good", ["family_friendly"], ["family"], "A supporting Pinnawala stay for broader accommodation matching.", [SL_TOURISM, wiki("Pinnawala")]),
    acc("Elepath Lodge", "pinnawala", "guesthouse", "budget", "good", ["family_friendly"], ["family", "backpackers"], "A lower-cost Pinnawala stay useful for family and transit nights.", [SL_TOURISM, wiki("Pinnawala")]),

    # Monaragala 3
    acc("Jetwing Kaduruketha", "wellawaya", "eco_lodge", "luxury", "excellent", ["eco", "scenic", "couples"], ["couples", "nature_lovers", "luxury_travelers"], "A major rural-luxury stay giving Monaragala real overnight relevance.", [JETWING, SL_TOURISM]),
    acc("Aqua Dunhinda Villa", "wellawaya", "villa", "midrange", "good", ["scenic"], ["family", "couples"], "A supporting Wellawaya-side stay for southeastern overland routes.", [SL_TOURISM, wiki("Wellawaya")]),
    acc("River Cottage Wellawaya", "wellawaya", "guesthouse", "budget", "good", ["scenic", "backpacker"], ["backpackers", "couples"], "A lower-cost overnight option supporting Monaragala corridor coverage.", [SL_TOURISM, wiki("Wellawaya")]),

    # Mannar 3
    acc("The Palmyrah House", "mannar", "boutique_hotel", "premium", "very_good", ["scenic", "couples"], ["couples", "nature_lovers"], "The district's strongest recognized tourism stay for Jaffna-Mannar route planning.", [SL_TOURISM, wiki("Mannar")]),
    acc("El Shaddai Hotel", "mannar", "hotel", "midrange", "good", ["city_stay"], ["family", "business"], "A practical Mannar town overnight option for northern itineraries.", [SL_TOURISM, wiki("Mannar")]),
    acc("Pesalai Beach View Hotel", "mannar", "guesthouse", "budget", "good", ["beachfront", "scenic"], ["backpackers", "couples"], "A simple coastal stay that broadens Mannar's small accommodation set.", [SL_TOURISM, wiki("Mannar")]),

    # Sparse districts 1-2 each
    acc("Akshathai Hotel", "kilinochchi", "hotel", "budget", "basic", ["city_stay"], ["business", "backpackers"], "A conservative transit-oriented Kilinochchi overnight option.", [SL_TOURISM, wiki("Kilinochchi")]),
    acc("Mullaitivu Beach Hotel", "mullaitivu", "hotel", "budget", "basic", ["scenic"], ["backpackers", "family"], "A simple coastal overnight option kept to preserve light district coverage.", [SL_TOURISM, wiki("Mullaitivu")]),
    acc("Nelly Star Hotel", "vavuniya", "hotel", "budget", "good", ["city_stay"], ["business", "family"], "A practical Vavuniya transit overnight with modest tourism usefulness.", [SL_TOURISM, wiki("Vavuniya")]),
    acc("Hotel Oviya", "vavuniya", "hotel", "budget", "basic", ["city_stay"], ["business", "backpackers"], "A secondary Vavuniya transit stay kept for broad overland itinerary support.", [SL_TOURISM, wiki("Vavuniya")]),
]


def build_dataset() -> dict:
    district_rows = {
        district: {"district": district, "province": province, "accommodations": []}
        for district, province in DISTRICTS
    }
    type_counts = Counter()
    price_counts = Counter()
    district_counts = Counter()
    seen_ids = set()

    for row in ACCOMMODATIONS:
        item = dict(row)
        item["id"] = f"lk_stay_{slugify(item['district'])}_{slugify(item['name'])}"
        if item["id"] in seen_ids:
            raise ValueError(f"Duplicate id: {item['id']}")
        seen_ids.add(item["id"])

        required = {
            "id", "name", "district", "province", "latitude", "longitude",
            "accommodation_type", "price_band", "rating_band", "tags",
            "ideal_for", "summary", "source_urls",
        }
        missing = required - item.keys()
        if missing:
            raise ValueError(f"Missing fields for {item['name']}: {sorted(missing)}")
        if item["district"] not in PROVINCE_BY_DISTRICT:
            raise ValueError(f"Unknown district: {item['district']}")
        if item["province"] != PROVINCE_BY_DISTRICT[item["district"]]:
            raise ValueError(f"Province mismatch: {item['name']}")
        if item["price_band"] not in PRICE_BANDS:
            raise ValueError(f"Invalid price band: {item['name']}")
        if item["rating_band"] not in RATING_BANDS:
            raise ValueError(f"Invalid rating band: {item['name']}")
        if item["accommodation_type"] not in ACCOMMODATION_TYPES:
            raise ValueError(f"Invalid accommodation type: {item['name']}")
        if not set(item["tags"]).issubset(TAG_SET):
            raise ValueError(f"Invalid tags: {item['name']}")
        if not set(item["ideal_for"]).issubset(IDEAL_FOR_SET):
            raise ValueError(f"Invalid ideal_for: {item['name']}")
        if not item["source_urls"]:
            raise ValueError(f"No sources: {item['name']}")

        item["tags"] = sorted(set(item["tags"]))
        item["ideal_for"] = sorted(set(item["ideal_for"]))
        district_rows[item["district"]]["accommodations"].append(item)
        type_counts[item["accommodation_type"]] += 1
        price_counts[item["price_band"]] += 1
        district_counts[item["district"]] += 1

    districts = []
    for district, province in DISTRICTS:
        stays = sorted(
            district_rows[district]["accommodations"],
            key=lambda x: (x["price_band"], x["name"]),
        )
        districts.append(
            {
                "district": district,
                "province": province,
                "accommodation_count": len(stays),
                "accommodations": stays,
            }
        )

    corridor_totals = []
    for corridor, members in CORRIDORS.items():
        corridor_totals.append(
            {
                "corridor": corridor,
                "accommodation_count": sum(district_counts[d] for d in members),
            }
        )
    corridor_totals.sort(key=lambda x: (-x["accommodation_count"], x["corridor"]))

    return {
        "metadata": {
            "dataset_name": "Sri Lanka Curated Accommodations",
            "schema_version": "1.0.0",
            "generated_on": "2026-06-05",
            "generated_by": "build_sri_lanka_accommodations.py",
            "country": "Sri Lanka",
            "organization": "district",
            "item_count": len(ACCOMMODATIONS),
            "district_count": len(DISTRICTS),
            "price_band_counts": dict(sorted(price_counts.items())),
            "accommodation_type_counts": dict(sorted(type_counts.items())),
            "districts_intentionally_sparse": SPARSE_DISTRICT_NOTES,
            "strongest_corridors": corridor_totals[:8],
        },
        "districts": districts,
    }


def write_summary(dataset: dict) -> None:
    districts = dataset["districts"]
    meta = dataset["metadata"]
    district_counts = {row["district"]: row["accommodation_count"] for row in districts}
    top_districts = sorted(district_counts.items(), key=lambda x: (-x[1], x[0]))[:10]

    lines = [
        "# Accommodations Summary",
        "",
        f"- Total accommodation count: **{meta['item_count']}**",
        f"- Districts covered: **{meta['district_count']}**",
        "",
        "## Counts by District",
        "",
    ]
    for row in districts:
        lines.append(f"- `{row['district']}`: {row['accommodation_count']}")

    lines.extend(["", "## Counts by Accommodation Type", ""])
    for key, value in meta["accommodation_type_counts"].items():
        lines.append(f"- `{key}`: {value}")

    lines.extend(["", "## Counts by Price Band", ""])
    for key, value in meta["price_band_counts"].items():
        lines.append(f"- `{key}`: {value}")

    lines.extend(["", "## Districts with Strongest Coverage", ""])
    for district, count in top_districts:
        lines.append(f"- `{district}`: {count}")

    lines.extend(["", "## Corridors with Strongest Coverage", ""])
    for row in meta["strongest_corridors"]:
        lines.append(f"- `{row['corridor']}`: {row['accommodation_count']}")

    lines.extend(["", "## Intentionally Sparse Districts", ""])
    for district, note in SPARSE_DISTRICT_NOTES.items():
        lines.append(f"- `{district}`: {note}")

    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    dataset = build_dataset()
    OUTPUT_PATH.write_text(json.dumps(dataset, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    write_summary(dataset)
    print(f"Wrote {OUTPUT_PATH} with {dataset['metadata']['item_count']} accommodations and {SUMMARY_PATH.name}.")


if __name__ == "__main__":
    main()
