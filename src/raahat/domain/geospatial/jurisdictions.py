"""Canonical Indian jurisdictions registry, geospatial boundaries, and dynamic fleet provisioner."""
from __future__ import annotations

from datetime import datetime, timezone
import math
import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from raahat.domain.geospatial.landmark import BoundingBox
from raahat.domain.shared.coordinates import PointCoordinates
from raahat.domain.resources import ResourceStatus, ResourceType
from raahat.infrastructure.database.models.resource import ResourceModel

SYSTEM_OPERATOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

# ---------------------------------------------------------------------------
# Canonical Dataset of Indian Jurisdictions (28 States & UTs with Districts)
# Includes GPS Centroids and Recommended Map Zoom Levels
# ---------------------------------------------------------------------------
INDIAN_JURISDICTIONS: list[dict[str, Any]] = [
    {
        "code": "KL",
        "name": "Kerala",
        "lat": 10.1076,
        "lng": 76.3516,
        "zoom": 9,
        "districts": [
            {"code": "KL-EKM", "name": "Ernakulam (Kochi / Aluva)", "lat": 9.9816, "lng": 76.2999, "zoom": 12},
            {"code": "KL-TSR", "name": "Thrissur (Chalakudy)", "lat": 10.5276, "lng": 76.2144, "zoom": 12},
            {"code": "KL-ALP", "name": "Alappuzha (Kuttanad)", "lat": 9.4981, "lng": 76.3388, "zoom": 12},
            {"code": "KL-IDK", "name": "Idukki (Dam Catchment)", "lat": 9.8500, "lng": 76.9700, "zoom": 11},
            {"code": "KL-WYD", "name": "Wayanad (Meppadi / Chooralmala)", "lat": 11.6854, "lng": 76.1320, "zoom": 12},
            {"code": "KL-PTA", "name": "Pathanamthitta (Ranni / Chengannur)", "lat": 9.2648, "lng": 76.7870, "zoom": 12},
            {"code": "KL-KTM", "name": "Kottayam", "lat": 9.5916, "lng": 76.5222, "zoom": 12},
            {"code": "KL-KKD", "name": "Kozhikode", "lat": 11.2588, "lng": 75.7804, "zoom": 12},
            {"code": "KL-MLP", "name": "Malappuram", "lat": 11.0732, "lng": 76.0740, "zoom": 11},
            {"code": "KL-PKD", "name": "Palakkad", "lat": 10.7867, "lng": 76.6548, "zoom": 11},
            {"code": "KL-KNR", "name": "Kannur", "lat": 11.8745, "lng": 75.3704, "zoom": 11},
            {"code": "KL-KSD", "name": "Kasaragod", "lat": 12.5102, "lng": 74.9852, "zoom": 11},
            {"code": "KL-KLM", "name": "Kollam", "lat": 8.8932, "lng": 76.6141, "zoom": 12},
            {"code": "KL-TVM", "name": "Thiruvananthapuram (State SEOC)", "lat": 8.5241, "lng": 76.9366, "zoom": 12},
        ],
    },
    {
        "code": "GA",
        "name": "Goa",
        "lat": 15.2993,
        "lng": 74.1240,
        "zoom": 9,
        "districts": [
            {"code": "GA-PNJ", "name": "North Goa (Panaji)", "lat": 15.4909, "lng": 73.8278, "zoom": 12},
            {"code": "GA-MGO", "name": "South Goa (Margao)", "lat": 15.2832, "lng": 73.9862, "zoom": 12},
        ],
    },
    {
        "code": "MH",
        "name": "Maharashtra",
        "lat": 19.7515,
        "lng": 75.7139,
        "zoom": 7,
        "districts": [
            {"code": "MH-MUM", "name": "Mumbai City", "lat": 18.9388, "lng": 72.8354, "zoom": 12},
            {"code": "MH-SUB", "name": "Mumbai Suburban", "lat": 19.1136, "lng": 72.8697, "zoom": 12},
            {"code": "MH-PUN", "name": "Pune", "lat": 18.5204, "lng": 73.8567, "zoom": 11},
            {"code": "MH-THN", "name": "Thane", "lat": 19.2183, "lng": 72.9781, "zoom": 12},
            {"code": "MH-RGD", "name": "Raigad (Mahad)", "lat": 18.5158, "lng": 73.1812, "zoom": 11},
            {"code": "MH-RTG", "name": "Ratnagiri (Chiplun)", "lat": 16.9902, "lng": 73.3120, "zoom": 11},
            {"code": "MH-KOP", "name": "Kolhapur (Panchganga)", "lat": 16.7050, "lng": 74.2433, "zoom": 11},
            {"code": "MH-SAT", "name": "Satara (Koyna)", "lat": 17.6805, "lng": 73.9997, "zoom": 11},
            {"code": "MH-NSK", "name": "Nashik", "lat": 19.9975, "lng": 73.7898, "zoom": 11},
            {"code": "MH-NGP", "name": "Nagpur", "lat": 21.1458, "lng": 79.0882, "zoom": 11},
        ],
    },
    {
        "code": "OD",
        "name": "Odisha",
        "lat": 20.9517,
        "lng": 85.0985,
        "zoom": 7,
        "districts": [
            {"code": "OD-PUR", "name": "Puri (Coastal Command)", "lat": 19.8135, "lng": 85.8312, "zoom": 12},
            {"code": "OD-KHD", "name": "Khordha (Bhubaneswar)", "lat": 20.2961, "lng": 85.8245, "zoom": 12},
            {"code": "OD-GNJ", "name": "Ganjam (Berhampur)", "lat": 19.3800, "lng": 85.0600, "zoom": 11},
            {"code": "OD-BLS", "name": "Balasore", "lat": 21.4934, "lng": 86.9135, "zoom": 11},
            {"code": "OD-KDP", "name": "Kendrapara", "lat": 20.5000, "lng": 86.4200, "zoom": 11},
            {"code": "OD-JSP", "name": "Jagatsinghpur (Paradeep)", "lat": 20.2600, "lng": 86.1700, "zoom": 11},
            {"code": "OD-CTC", "name": "Cuttack (Mahanadi)", "lat": 20.4625, "lng": 85.8828, "zoom": 12},
        ],
    },
    {
        "code": "AS",
        "name": "Assam",
        "lat": 26.2006,
        "lng": 92.9376,
        "zoom": 7,
        "districts": [
            {"code": "AS-GHY", "name": "Kamrup Metropolitan (Guwahati)", "lat": 26.1445, "lng": 91.7362, "zoom": 12},
            {"code": "AS-DHE", "name": "Dhemaji (Brahmaputra)", "lat": 27.4800, "lng": 94.5800, "zoom": 11},
            {"code": "AS-DIB", "name": "Dibrugarh", "lat": 27.4728, "lng": 94.9120, "zoom": 11},
            {"code": "AS-CAH", "name": "Cachar (Silchar)", "lat": 24.8333, "lng": 92.7789, "zoom": 11},
            {"code": "AS-BRP", "name": "Barpeta", "lat": 26.3216, "lng": 91.0062, "zoom": 11},
            {"code": "AS-NGN", "name": "Nagaon", "lat": 26.3468, "lng": 92.6840, "zoom": 11},
        ],
    },
    {
        "code": "TN",
        "name": "Tamil Nadu",
        "lat": 11.1271,
        "lng": 78.6569,
        "zoom": 7,
        "districts": [
            {"code": "TN-CHN", "name": "Chennai (GCC Command)", "lat": 13.0827, "lng": 80.2707, "zoom": 12},
            {"code": "TN-CDL", "name": "Cuddalore", "lat": 11.7480, "lng": 79.7714, "zoom": 11},
            {"code": "TN-NGP", "name": "Nagapattinam (Tsunami Command)", "lat": 10.7672, "lng": 79.8449, "zoom": 12},
            {"code": "TN-KNC", "name": "Kanchipuram", "lat": 12.8342, "lng": 79.7036, "zoom": 11},
            {"code": "TN-TVL", "name": "Tiruvallur", "lat": 13.1432, "lng": 79.9079, "zoom": 11},
            {"code": "TN-CBE", "name": "Coimbatore", "lat": 11.0168, "lng": 76.9558, "zoom": 11},
        ],
    },
    {
        "code": "GJ",
        "name": "Gujarat",
        "lat": 22.2587,
        "lng": 71.1924,
        "zoom": 7,
        "districts": [
            {"code": "GJ-KUT", "name": "Kutch (Bhuj Earthquake Command)", "lat": 23.2420, "lng": 69.6669, "zoom": 10},
            {"code": "GJ-SUR", "name": "Surat (Tapi Flood Plain)", "lat": 21.1702, "lng": 72.8311, "zoom": 12},
            {"code": "GJ-AHM", "name": "Ahmedabad", "lat": 23.0225, "lng": 72.5714, "zoom": 11},
            {"code": "GJ-JAM", "name": "Jamnagar (Cyclone Command)", "lat": 22.4707, "lng": 70.0577, "zoom": 11},
        ],
    },
    {
        "code": "UK",
        "name": "Uttarakhand",
        "lat": 30.0668,
        "lng": 79.0193,
        "zoom": 8,
        "districts": [
            {"code": "UK-CHM", "name": "Chamoli (Joshimath / Badrinath)", "lat": 30.5583, "lng": 79.5658, "zoom": 11},
            {"code": "UK-RDP", "name": "Rudraprayag (Kedarnath Valley)", "lat": 30.2844, "lng": 78.9811, "zoom": 11},
            {"code": "UK-UTK", "name": "Uttarkashi (Bhagirathi Basin)", "lat": 30.7268, "lng": 78.4354, "zoom": 11},
            {"code": "UK-DDN", "name": "Dehradun (State SEOC)", "lat": 30.3165, "lng": 78.0322, "zoom": 12},
            {"code": "UK-PTH", "name": "Pithoragarh (Flash Flood Command)", "lat": 29.5829, "lng": 80.2182, "zoom": 11},
        ],
    },
    {
        "code": "HP",
        "name": "Himachal Pradesh",
        "lat": 31.1048,
        "lng": 77.1734,
        "zoom": 8,
        "districts": [
            {"code": "HP-KLU", "name": "Kullu (Manali / Beas Valley)", "lat": 31.9579, "lng": 77.1095, "zoom": 11},
            {"code": "HP-MND", "name": "Mandi (Suketi Khad)", "lat": 31.7087, "lng": 76.9320, "zoom": 11},
            {"code": "HP-SML", "name": "Shimla (State SEOC)", "lat": 31.1048, "lng": 77.1734, "zoom": 12},
            {"code": "HP-KNG", "name": "Kangra (Dharamshala)", "lat": 32.0998, "lng": 76.2691, "zoom": 11},
        ],
    },
    {
        "code": "BR",
        "name": "Bihar",
        "lat": 25.0961,
        "lng": 85.3131,
        "zoom": 7,
        "districts": [
            {"code": "BR-PAT", "name": "Patna (Ganga Basin)", "lat": 25.6127, "lng": 85.1589, "zoom": 12},
            {"code": "BR-DBG", "name": "Darbhanga (Kosi Flood Zone)", "lat": 26.1542, "lng": 85.8918, "zoom": 11},
            {"code": "BR-MZF", "name": "Muzaffarpur", "lat": 26.1209, "lng": 85.3647, "zoom": 11},
            {"code": "BR-PUR", "name": "Purnia", "lat": 25.7771, "lng": 87.4753, "zoom": 11},
        ],
    },
    {
        "code": "WB",
        "name": "West Bengal",
        "lat": 22.9868,
        "lng": 87.8550,
        "zoom": 7,
        "districts": [
            {"code": "WB-KOL", "name": "Kolkata Metropolitan", "lat": 22.5726, "lng": 88.3639, "zoom": 12},
            {"code": "WB-S24", "name": "South 24 Parganas (Sundarbans)", "lat": 22.1352, "lng": 88.4016, "zoom": 11},
            {"code": "WB-N24", "name": "North 24 Parganas", "lat": 22.7210, "lng": 88.4810, "zoom": 11},
            {"code": "WB-DJL", "name": "Darjeeling", "lat": 27.0410, "lng": 88.2663, "zoom": 11},
        ],
    },
    {
        "code": "KA",
        "name": "Karnataka",
        "lat": 15.3173,
        "lng": 75.7139,
        "zoom": 7,
        "districts": [
            {"code": "KA-BLR", "name": "Bengaluru Urban (BBMP Command)", "lat": 12.9716, "lng": 77.5946, "zoom": 12},
            {"code": "KA-DKN", "name": "Dakshina Kannada (Mangalore)", "lat": 12.9141, "lng": 74.8560, "zoom": 11},
            {"code": "KA-KOD", "name": "Kodagu (Coorg)", "lat": 12.3375, "lng": 75.8069, "zoom": 11},
            {"code": "KA-UDP", "name": "Udupi", "lat": 13.3409, "lng": 74.7421, "zoom": 11},
        ],
    },
    {
        "code": "DL",
        "name": "Delhi",
        "lat": 28.6139,
        "lng": 77.2090,
        "zoom": 11,
        "districts": [
            {"code": "DL-CEN", "name": "Central Delhi (NDMC)", "lat": 28.6139, "lng": 77.2090, "zoom": 13},
            {"code": "DL-NOR", "name": "North Delhi (Yamuna Flood Plain)", "lat": 28.7041, "lng": 77.1025, "zoom": 12},
            {"code": "DL-SOU", "name": "South Delhi", "lat": 28.5355, "lng": 77.1990, "zoom": 12},
        ],
    },
    {
        "code": "UP",
        "name": "Uttar Pradesh",
        "lat": 26.8467,
        "lng": 80.9462,
        "zoom": 7,
        "districts": [
            {"code": "UP-LKO", "name": "Lucknow (State SEOC)", "lat": 26.8467, "lng": 80.9462, "zoom": 12},
            {"code": "UP-VNS", "name": "Varanasi", "lat": 25.3176, "lng": 82.9739, "zoom": 12},
            {"code": "UP-GKP", "name": "Gorakhpur (Rapti Basin)", "lat": 26.7606, "lng": 83.3732, "zoom": 11},
            {"code": "UP-PRG", "name": "Prayagraj (Sangam)", "lat": 25.4358, "lng": 81.8463, "zoom": 12},
        ],
    },
    {
        "code": "AP",
        "name": "Andhra Pradesh",
        "lat": 15.9129,
        "lng": 79.7400,
        "zoom": 7,
        "districts": [
            {"code": "AP-VSK", "name": "Visakhapatnam (Coastal Command)", "lat": 17.6868, "lng": 83.2185, "zoom": 12},
            {"code": "AP-VJW", "name": "Vijayawada (Krishna Basin)", "lat": 16.5062, "lng": 80.6480, "zoom": 12},
            {"code": "AP-EGD", "name": "East Godavari (Kakinada)", "lat": 17.0005, "lng": 81.8040, "zoom": 11},
        ],
    },
    {
        "code": "TG",
        "name": "Telangana",
        "lat": 18.1124,
        "lng": 79.0193,
        "zoom": 7,
        "districts": [
            {"code": "TG-HYD", "name": "Hyderabad (GHMC Command)", "lat": 17.3850, "lng": 78.4867, "zoom": 12},
            {"code": "TG-BDK", "name": "Bhadradri Kothagudem (Godavari Flood Zone)", "lat": 17.5500, "lng": 80.6167, "zoom": 11},
            {"code": "TG-WGL", "name": "Warangal", "lat": 17.9689, "lng": 79.5941, "zoom": 11},
        ],
    },
]

# Fast indexed lookups
_DISTRICT_INDEX: dict[str, dict[str, Any]] = {}
_STATE_INDEX: dict[str, dict[str, Any]] = {}

for s in INDIAN_JURISDICTIONS:
    _STATE_INDEX[s["code"].upper()] = s
    for d in s.get("districts", []):
        _DISTRICT_INDEX[d["code"].upper()] = {
            **d,
            "state_code": s["code"],
            "state_name": s["name"],
        }


def get_district_info(district_code: str) -> Optional[dict[str, Any]]:
    """Lookup district metadata, centroid, and parent state by ISO/custom district code."""
    return _DISTRICT_INDEX.get(district_code.strip().upper())


def get_state_info(state_code: str) -> Optional[dict[str, Any]]:
    """Lookup state metadata and centroid by state code."""
    return _STATE_INDEX.get(state_code.strip().upper())


def get_district_bounding_box(district_code: str, radius_km: float = 45.0) -> Optional[BoundingBox]:
    """Compute geographic WGS84 bounding box around district centroid.

    Uses spherical approximation (1 deg lat = 111 km, 1 deg lon = 111 * cos(lat) km).
    """
    info = get_district_info(district_code)
    if not info:
        return None

    lat = info["lat"]
    lng = info["lng"]

    d_lat = radius_km / 111.0
    cos_lat = max(0.2, math.cos(math.radians(lat)))
    d_lng = radius_km / (111.0 * cos_lat)

    return BoundingBox(
        min_latitude=max(-90.0, lat - d_lat),
        min_longitude=max(-180.0, lng - d_lng),
        max_latitude=min(90.0, lat + d_lat),
        max_longitude=min(180.0, lng + d_lng),
    )


def infer_district_from_coords(lat: float, lon: float) -> Optional[str]:
    """Find closest district code to given coordinates."""
    closest_code: Optional[str] = None
    min_dist_sq = float("inf")

    for code, d in _DISTRICT_INDEX.items():
        d_lat = lat - d["lat"]
        d_lon = lon - d["lng"]
        dist_sq = d_lat * d_lat + d_lon * d_lon
        if dist_sq < min_dist_sq:
            min_dist_sq = dist_sq
            closest_code = code

    return closest_code


def infer_district_from_text(text: str, state_hint: Optional[str] = None) -> Optional[str]:
    """Dynamically infer district code from natural language location mentions."""
    if not text:
        return None

    lower = text.lower()

    # If state hint provided, search that state's districts first
    search_districts = []
    if state_hint and state_hint.upper() in _STATE_INDEX:
        search_districts = [
            d for d in _DISTRICT_INDEX.values() if d["state_code"].upper() == state_hint.upper()
        ]
    else:
        search_districts = list(_DISTRICT_INDEX.values())

    # Check for exact district keywords
    for d in search_districts:
        name_clean = d["name"].lower()
        # Extract main tokens, e.g. "ernakulam", "kochi", "aluva", "chalakudy", "margao", "panaji"
        tokens = [t.strip("()/, ") for t in name_clean.split() if len(t.strip("()/, ")) > 3]
        if any(tok in lower for tok in tokens):
            return d["code"]

    # Malayalam specific tokens
    if "ആലുവ" in text or "എറണാകുളം" in text or "കൊച്ചി" in text:
        return "KL-EKM"
    if "ചാലക്കുടി" in text or "തൃശ്ശൂർ" in text or "പുത്തൻവേലിക്കര" in text:
        return "KL-TSR"
    if "കുട്ടനാട്" in text or "ആലപ്പുഴ" in text:
        return "KL-ALP"
    if "മൂന്നാർ" in text or "ഇടുക്കി" in text:
        return "KL-IDK"
    if "വയനാട്" in text or "മേപ്പാടി" in text or "ചൂരൽമല" in text:
        return "KL-WYD"
    if "റാന്നി" in text or "ചെങ്ങന്നൂർ" in text or "പത്തനംതിട്ട" in text:
        return "KL-PTA"

    # Goa specific tokens
    if "margao" in lower or "madgaon" in lower or "colva" in lower or "south goa" in lower:
        return "GA-MGO"
    if "panaji" in lower or "panjim" in lower or "mapusa" in lower or "north goa" in lower:
        return "GA-PNJ"

    return None


def ensure_jurisdiction_fleet(
    session: Session,
    disaster_id: uuid.UUID,
    district_code: str,
) -> list[ResourceModel]:
    """Dynamically provision standard emergency rescue fleet assets for any district if none exist.

    Ensures that every DEOC has immediate rescue assets (NDRF Boat, SDRF Rescue Unit,
    Medical Team, Relief Shelter) at realistic coordinates within its operational perimeter.
    """
    info = get_district_info(district_code)
    if not info:
        return []

    lat = info["lat"]
    lng = info["lng"]
    dist_name = info["name"].split("(")[0].strip()

    # Check if this district already has resources
    existing = session.scalars(
        select(ResourceModel).where(ResourceModel.disaster_id == disaster_id)
    ).all()

    # If resources already exist within 45km of this district center, return them
    local_existing = []
    for r in existing:
        if r.location:
            # Simple Euclidean approx in degrees (~0.4 deg ≈ 45km)
            d_sq = (r.location.latitude - lat) ** 2 + (r.location.longitude - lng) ** 2
            if d_sq <= 0.16:
                local_existing.append(r)

    if local_existing:
        return local_existing

    # Generate standard sector assets
    standard_units = [
        (f"NDRF Rescue Boat {dist_name}-01", ResourceType.BOAT, lat + 0.012, lng - 0.015, 15),
        (f"SDRF Tactical Unit {dist_name}", ResourceType.BOAT, lat - 0.018, lng + 0.020, 10),
        (f"Army Medical Team {dist_name}", ResourceType.MEDICAL_TEAM, lat + 0.005, lng + 0.008, 20),
        (f"Disaster Relief Camp {dist_name}", ResourceType.SHELTER, lat - 0.010, lng - 0.012, 300),
    ]

    new_models = []
    for name, rtype, rlat, rlon, cap in standard_units:
        rm = ResourceModel(
            id=uuid.uuid4(),
            disaster_id=disaster_id,
            resource_type=rtype.value,
            name=name,
            capacity=cap,
            availability_status=ResourceStatus.AVAILABLE.value,
            location=f"SRID=4326;POINT({rlon} {rlat})",
            created_at=datetime.now(timezone.utc),
        )
        session.add(rm)
        new_models.append(rm)

    session.flush()
    return new_models

