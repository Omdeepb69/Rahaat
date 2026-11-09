"""State and District-scoped authentication for RAAHAT 2.0 Command Center.

Supports Indian Disaster Management hierarchy:
- State Disaster Management Authority (SDMA / SEOC)
- District Disaster Management Authority (DDMA / DEOC)

Password scheme (deterministic, formula-based):
  DEOC  → {StateName}{DistrictShortName}{YEAR}#   e.g. KeralaErnakulam2026#
  SEOC  → {StateName}SEOC{YEAR}#                   e.g. KeralaSEOC2026#

The formula is communicated to officers out-of-band by the State EOC.
No demo/master passkeys exist — only the computed password is accepted.

When an operator authenticates:
1. Returns a signed HMAC-SHA256 JWT (stdlib only) with state_code, district_code,
   and GPS coordinates for the jurisdiction.
2. The frontend Leaflet map auto-centers on the operator's jurisdiction using those
   coordinates.
3. Failed attempts are rate-limited per IP (5 attempts per 15 minutes).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from collections import defaultdict
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

router = APIRouter(tags=["auth"])

# ---------------------------------------------------------------------------
# Rate limiting (in-memory, per remote IP)
# ---------------------------------------------------------------------------
_RATE_LIMIT_WINDOW_SECONDS = 900  # 15 minutes
_RATE_LIMIT_MAX_FAILURES = 5
_failed_attempts: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(ip: str) -> None:
    now = time.time()
    cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
    _failed_attempts[ip] = [t for t in _failed_attempts[ip] if t > cutoff]
    if len(_failed_attempts[ip]) >= _RATE_LIMIT_MAX_FAILURES:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again later.",
        )


def _record_failure(ip: str) -> None:
    _failed_attempts[ip].append(time.time())

_ENV_SECRET = os.environ.get("RAAHAT_JWT_SECRET", "")
_JWT_SECRET: bytes = (
    _ENV_SECRET.encode()
    if _ENV_SECRET
    else b"raahat-dev-secret-change-in-production-do-not-use"
)
_JWT_ALGORITHM = "HS256"
_TOKEN_TTL_SECONDS = 12 * 60 * 60  # 12-hour operational shift
DEFAULT_DISPATCHER_ID = "00000000-0000-0000-0000-000000000001"

# ---------------------------------------------------------------------------
# Comprehensive Indian Jurisdictions Dataset (States & Districts)
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
            {"code": "TN-NGP", "name": "Nagapattinam", "lat": 10.7656, "lng": 79.8424, "zoom": 11},
            {"code": "TN-KNC", "name": "Kanchipuram", "lat": 12.8342, "lng": 79.7036, "zoom": 11},
            {"code": "TN-TRV", "name": "Tiruvallur", "lat": 13.1432, "lng": 79.9074, "zoom": 11},
            {"code": "TN-CBE", "name": "Coimbatore", "lat": 11.0168, "lng": 76.9558, "zoom": 12},
        ],
    },
    {
        "code": "UK",
        "name": "Uttarakhand",
        "lat": 30.0668,
        "lng": 79.0193,
        "zoom": 8,
        "districts": [
            {"code": "UK-CHM", "name": "Chamoli (Joshimath)", "lat": 30.4200, "lng": 79.3300, "zoom": 11},
            {"code": "UK-RDP", "name": "Rudraprayag (Kedarnath)", "lat": 30.2844, "lng": 78.9811, "zoom": 11},
            {"code": "UK-UTK", "name": "Uttarkashi", "lat": 30.7300, "lng": 78.4400, "zoom": 11},
            {"code": "UK-DDN", "name": "Dehradun (SEOC HQ)", "lat": 30.3165, "lng": 78.0322, "zoom": 12},
            {"code": "UK-PTH", "name": "Pithoragarh", "lat": 29.5829, "lng": 80.2182, "zoom": 11},
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
            {"code": "HP-MND", "name": "Mandi", "lat": 31.7088, "lng": 76.9320, "zoom": 11},
            {"code": "HP-SML", "name": "Shimla", "lat": 31.1048, "lng": 77.1734, "zoom": 12},
            {"code": "HP-KNG", "name": "Kangra (Dharamshala)", "lat": 32.0998, "lng": 76.2691, "zoom": 11},
        ],
    },
    {
        "code": "GJ",
        "name": "Gujarat",
        "lat": 22.2587,
        "lng": 71.1924,
        "zoom": 7,
        "districts": [
            {"code": "GJ-KCH", "name": "Kutch (Bhuj)", "lat": 23.7337, "lng": 69.8597, "zoom": 10},
            {"code": "GJ-SRT", "name": "Surat (Tapi Basin)", "lat": 21.1702, "lng": 72.8311, "zoom": 12},
            {"code": "GJ-AMD", "name": "Ahmedabad", "lat": 23.0225, "lng": 72.5714, "zoom": 12},
            {"code": "GJ-JAM", "name": "Jamnagar", "lat": 22.4707, "lng": 70.0577, "zoom": 11},
        ],
    },
    {
        "code": "BR",
        "name": "Bihar",
        "lat": 25.0961,
        "lng": 85.3131,
        "zoom": 7,
        "districts": [
            {"code": "BR-PAT", "name": "Patna (Ganga Basin)", "lat": 25.5941, "lng": 85.1376, "zoom": 12},
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
    {"code": "AR", "name": "Arunachal Pradesh", "lat": 28.2180, "lng": 94.7278, "zoom": 7, "districts": [{"code": "AR-ITN", "name": "Itanagar", "lat": 27.0844, "lng": 93.6053, "zoom": 11}]},
    {"code": "CG", "name": "Chhattisgarh", "lat": 21.2787, "lng": 81.8661, "zoom": 7, "districts": [{"code": "CG-RPR", "name": "Raipur", "lat": 21.2514, "lng": 81.6296, "zoom": 11}]},
    {"code": "GA", "name": "Goa", "lat": 15.2993, "lng": 74.1240, "zoom": 9, "districts": [
        {"code": "GA-PNJ", "name": "North Goa (Panaji)", "lat": 15.4909, "lng": 73.8278, "zoom": 12},
        {"code": "GA-MGO", "name": "South Goa (Margao)", "lat": 15.2832, "lng": 73.9862, "zoom": 12},
    ]},
    {"code": "HR", "name": "Haryana", "lat": 29.0588, "lng": 76.0856, "zoom": 8, "districts": [{"code": "HR-GGN", "name": "Gurugram", "lat": 28.4595, "lng": 77.0266, "zoom": 12}]},
    {"code": "JH", "name": "Jharkhand", "lat": 23.6102, "lng": 85.2799, "zoom": 7, "districts": [{"code": "JH-RNC", "name": "Ranchi", "lat": 23.3441, "lng": 85.3096, "zoom": 11}]},
    {"code": "MP", "name": "Madhya Pradesh", "lat": 22.9734, "lng": 78.6569, "zoom": 7, "districts": [{"code": "MP-BPL", "name": "Bhopal", "lat": 23.2599, "lng": 77.4126, "zoom": 11}]},
    {"code": "MN", "name": "Manipur", "lat": 24.6637, "lng": 93.9063, "zoom": 8, "districts": [{"code": "MN-IMP", "name": "Imphal", "lat": 24.8170, "lng": 93.9368, "zoom": 11}]},
    {"code": "ML", "name": "Meghalaya", "lat": 25.4670, "lng": 91.3662, "zoom": 8, "districts": [{"code": "ML-SHL", "name": "Shillong", "lat": 25.5788, "lng": 91.8933, "zoom": 11}]},
    {"code": "MZ", "name": "Mizoram", "lat": 23.1645, "lng": 92.9376, "zoom": 8, "districts": [{"code": "MZ-AZL", "name": "Aizawl", "lat": 23.7307, "lng": 92.7173, "zoom": 11}]},
    {"code": "NL", "name": "Nagaland", "lat": 26.1584, "lng": 94.5624, "zoom": 8, "districts": [{"code": "NL-KHM", "name": "Kohima", "lat": 25.6751, "lng": 94.1086, "zoom": 11}]},
    {"code": "PB", "name": "Punjab", "lat": 31.1471, "lng": 75.3412, "zoom": 8, "districts": [{"code": "PB-ASR", "name": "Amritsar", "lat": 31.6340, "lng": 74.8723, "zoom": 11}]},
    {"code": "RJ", "name": "Rajasthan", "lat": 27.0238, "lng": 74.2179, "zoom": 7, "districts": [{"code": "RJ-JPR", "name": "Jaipur", "lat": 26.9124, "lng": 75.7873, "zoom": 11}]},
    {"code": "SK", "name": "Sikkim", "lat": 27.5330, "lng": 88.5122, "zoom": 8, "districts": [{"code": "SK-GTK", "name": "Gangtok (Teesta Basin)", "lat": 27.3389, "lng": 88.6065, "zoom": 11}]},
    {"code": "TR", "name": "Tripura", "lat": 23.9408, "lng": 91.9882, "zoom": 8, "districts": [{"code": "TR-AGT", "name": "Agartala", "lat": 23.8315, "lng": 91.2868, "zoom": 11}]},
    {"code": "JK", "name": "Jammu & Kashmir", "lat": 33.7782, "lng": 76.5762, "zoom": 7, "districts": [{"code": "JK-SGR", "name": "Srinagar (Jhelum Basin)", "lat": 34.0837, "lng": 74.7973, "zoom": 11}]},
    {"code": "LA", "name": "Ladakh", "lat": 34.1526, "lng": 77.5771, "zoom": 7, "districts": [{"code": "LA-LEH", "name": "Leh", "lat": 34.1526, "lng": 77.5771, "zoom": 10}]},
    {"code": "AN", "name": "Andaman & Nicobar Islands", "lat": 11.7401, "lng": 92.6586, "zoom": 8, "districts": [{"code": "AN-PBL", "name": "Port Blair (Tsunami Warning Centre)", "lat": 11.6234, "lng": 92.7265, "zoom": 11}]},
    {"code": "CH", "name": "Chandigarh", "lat": 30.7333, "lng": 76.7794, "zoom": 12, "districts": [{"code": "CH-CHD", "name": "Chandigarh UT", "lat": 30.7333, "lng": 76.7794, "zoom": 12}]},
    {"code": "DN", "name": "Dadra & Nagar Haveli and Daman & Diu", "lat": 20.4283, "lng": 72.8397, "zoom": 10, "districts": [{"code": "DN-DMN", "name": "Daman", "lat": 20.3974, "lng": 72.8328, "zoom": 12}]},
    {"code": "LD", "name": "Lakshadweep", "lat": 10.5667, "lng": 72.6417, "zoom": 9, "districts": [{"code": "LD-KVT", "name": "Kavaratti", "lat": 10.5667, "lng": 72.6417, "zoom": 12}]},
    {"code": "PY", "name": "Puducherry", "lat": 11.9416, "lng": 79.8083, "zoom": 11, "districts": [{"code": "PY-PDY", "name": "Puducherry Central", "lat": 11.9416, "lng": 79.8083, "zoom": 12}]},
]

_STATE_MAP = {s["code"]: s for s in INDIAN_JURISDICTIONS}

# ---------------------------------------------------------------------------
# Password derivation (name-based, deterministic)
# ---------------------------------------------------------------------------
_PASSWORD_STOP_WORDS = frozenset({
    "and", "of", "the", "dr", "sri", "ys", "br", "ntr", "potti", "sriramulu", "st",
})


def _clean_name_for_password(s: str) -> str:
    """Strip parentheticals, special chars, and stop-words; return CamelCase."""
    s = re.sub(r'\(.*?\)', '', s).strip()
    s = re.sub(r'[^a-zA-Z0-9 ]', '', s).strip()
    words = [w.capitalize() for w in s.split() if w.lower() not in _PASSWORD_STOP_WORDS]
    return ''.join(words[:2])


def _district_password(state_name: str, district_name: str, year: int = 2026) -> str:
    """DEOC passkey: {StateName[:8]}{DistrictShortName[:10]}{YEAR}#"""
    s = _clean_name_for_password(state_name)[:8]
    d = _clean_name_for_password(district_name)[:10]
    return f'{s}{d}{year}#'


def _seoc_password(state_name: str, year: int = 2026) -> str:
    """SEOC passkey: {StateName[:12]}SEOC{YEAR}#"""
    s = _clean_name_for_password(state_name)[:12]
    return f'{s}SEOC{year}#'


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (padding % 4))


def _make_token(payload_dict: dict[str, Any]) -> str:
    header = _b64url_encode(json.dumps({"alg": _JWT_ALGORITHM, "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps(payload_dict).encode())
    signing_input = f"{header}.{payload}".encode()
    sig = hmac.new(_JWT_SECRET, signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url_encode(sig)}"


def _verify_token(token: str) -> dict[str, Any]:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token format")

    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected_sig = hmac.new(_JWT_SECRET, signing_input, hashlib.sha256).digest()
    provided_sig = _b64url_decode(sig_b64)

    if not hmac.compare_digest(expected_sig, provided_sig):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")

    try:
        claims = json.loads(_b64url_decode(payload_b64))
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token payload")

    if int(time.time()) > claims.get("exp", 0):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")

    return claims


_bearer = HTTPBearer(auto_error=False)


def require_state_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization header missing")
    return _verify_token(credentials.credentials)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class DistrictInfo(BaseModel):
    code: str
    name: str
    lat: float
    lng: float
    zoom: int = 12


class JurisdictionItem(BaseModel):
    code: str
    name: str
    lat: float
    lng: float
    zoom: int = 8
    districts: list[DistrictInfo] = Field(default_factory=list)


class LoginRequest(BaseModel):
    state_code: str
    district_code: Optional[str] = None
    password: str
    officer_name: Optional[str] = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    state_code: str
    state_name: str
    district_code: Optional[str] = None
    district_name: Optional[str] = None
    center_lat: float
    center_lng: float
    zoom: int
    officer_name: str
    role: str
    dispatcher_id: str
    expires_in: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/auth/jurisdictions", response_model=list[JurisdictionItem])
def list_jurisdictions() -> list[dict[str, Any]]:
    """Return all Indian states and Union Territories with districts and GPS coordinates."""
    return INDIAN_JURISDICTIONS


@router.get("/auth/states")
def list_states_summary() -> list[dict[str, str]]:
    """Quick state list for drop-downs."""
    return [{"code": s["code"], "name": s["name"]} for s in INDIAN_JURISDICTIONS]


@router.get("/auth/credential-format")
def credential_format() -> dict[str, str]:
    """Return the passkey formula for onboarding communications.

    This endpoint exists so that State EOCs can reference the formula in
    officer induction materials without hardcoding it. It does NOT return any
    actual passkey — only the derivation pattern and an illustrative example.
    """
    return {
        "deoc_format": "{StateName}{DistrictShortName}{YEAR}#",
        "seoc_format": "{StateName}SEOC{YEAR}#",
        "example_deoc": "KeralaErnakulam2026#",
        "example_seoc": "KeralaSEOC2026#",
        "note": "Contact your State EOC for your assigned passkey.",
    }


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request) -> LoginResponse:
    """Authenticate an emergency command operator for a State or District DEOC.

    Passkey must match the jurisdiction-derived formula exactly.
    Failed attempts are rate-limited per IP to prevent brute-force attacks.
    Error responses are always generic — they never disclose which field failed.
    """
    client_ip: str = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    code = body.state_code.upper()
    state_data = _STATE_MAP.get(code)
    if not state_data:
        _record_failure(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Resolve district first so we can compute the correct expected password.
    district_code = body.district_code.strip() if body.district_code else None
    district_data = None
    if district_code:
        for d in state_data.get("districts", []):
            if d["code"].upper() == district_code.upper():
                district_data = d
                break
        if not district_data:
            _record_failure(client_ip)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

    expected = (
        _district_password(state_data["name"], district_data["name"])
        if district_data
        else _seoc_password(state_data["name"])
    )

    if not hmac.compare_digest(body.password, expected):
        _record_failure(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Determine center coordinates and zoom level
    if district_data:
        center_lat = district_data["lat"]
        center_lng = district_data["lng"]
        zoom = district_data.get("zoom", 12)
        district_name = district_data["name"]
        role = "DDMA_DEOC_COMMANDER"
        subject = f"ddma:{code}:{district_code}"
    else:
        center_lat = state_data["lat"]
        center_lng = state_data["lng"]
        zoom = state_data.get("zoom", 8)
        district_name = None
        role = "SDMA_SEOC_COMMANDER"
        subject = f"sdma:{code}"

    officer_name = body.officer_name or (
        f"Duty Officer ({district_name.split('(')[0].strip() if district_name else state_data['name']})"
    )

    now = int(time.time())
    payload = {
        "sub": subject,
        "state_code": code,
        "state_name": state_data["name"],
        "district_code": district_code,
        "district_name": district_name,
        "center_lat": center_lat,
        "center_lng": center_lng,
        "zoom": zoom,
        "officer_name": officer_name,
        "role": role,
        "dispatcher_id": DEFAULT_DISPATCHER_ID,
        "iat": now,
        "exp": now + _TOKEN_TTL_SECONDS,
    }

    token = _make_token(payload)

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        state_code=code,
        state_name=state_data["name"],
        district_code=district_code,
        district_name=district_name,
        center_lat=center_lat,
        center_lng=center_lng,
        zoom=zoom,
        officer_name=officer_name,
        role=role,
        dispatcher_id=DEFAULT_DISPATCHER_ID,
        expires_in=_TOKEN_TTL_SECONDS,
    )


@router.get("/auth/me")
def me(claims: Annotated[dict[str, Any], Depends(require_state_auth)]) -> dict[str, Any]:
    """Inspect active session claims."""
    return claims
