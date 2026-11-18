from __future__ import annotations

import json
import math
import os
import sqlite3
import time
import threading
from pathlib import Path
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "localhelp.db"

NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
USER_AGENT = os.getenv(
    "LOCALHELP_USER_AGENT",
    "LocalHelp/1.0 (educational community-resource finder)"
)
REQUEST_TIMEOUT = 35
_nominatim_lock = threading.Lock()
_nominatim_last_request = 0.0

app = FastAPI(
    title="LocalHelp API",
    description="API educativa para localizar lugares comunitarios registrados en OpenStreetMap.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, limitar al dominio real de LocalHelp.
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "frontend"), name="static")


class RequestRecord(BaseModel):
    alias: str = Field(min_length=2, max_length=40)
    need: str = Field(min_length=3, max_length=500)
    city: str = Field(min_length=2, max_length=120)


def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS geocode_cache (
                query TEXT PRIMARY KEY,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                display_name TEXT NOT NULL,
                saved_at INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias TEXT NOT NULL,
                need TEXT NOT NULL,
                city TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)


initialize_database()


CATEGORY_TAGS = {
    "food": [
        'node["amenity"="food_bank"]',
        'node["social_facility"="food_bank"]',
        'way["amenity"="food_bank"]',
        'way["social_facility"="food_bank"]',
        'relation["amenity"="food_bank"]',
        'relation["social_facility"="food_bank"]'
    ],
    "housing": [
        'node["amenity"="shelter"]',
        'node["social_facility"="shelter"]',
        'way["amenity"="shelter"]',
        'way["social_facility"="shelter"]',
        'relation["amenity"="shelter"]',
        'relation["social_facility"="shelter"]'
    ],
    "health": [
        'node["amenity"~"clinic|hospital|doctors|dentist"]',
        'way["amenity"~"clinic|hospital|doctors|dentist"]',
        'relation["amenity"~"clinic|hospital|doctors|dentist"]'
    ],
    "education": [
        'node["amenity"~"school|college|university|library"]',
        'way["amenity"~"school|college|university|library"]',
        'relation["amenity"~"school|college|university|library"]'
    ],
    "employment": [
        'node["office"="employment_agency"]',
        'way["office"="employment_agency"]',
        'relation["office"="employment_agency"]'
    ],
    "community": [
        'node["social_facility"]',
        'way["social_facility"]',
        'relation["social_facility"]',
        'node["amenity"="community_centre"]',
        'way["amenity"="community_centre"]',
        'relation["amenity"="community_centre"]'
    ],
}


def haversine_km(lat1, lon1, lat2, lon2):
    earth_radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * earth_radius * math.asin(math.sqrt(min(1, a)))


def geocode_location(location: str):
    normalized = " ".join(location.strip().split()).lower()
    if len(normalized) < 2:
        raise HTTPException(status_code=400, detail="Escribe una ciudad, estado o código postal.")

    with db() as conn:
        cached = conn.execute(
            "SELECT lat, lon, display_name FROM geocode_cache WHERE query = ?",
            (normalized,)
        ).fetchone()
    if cached:
        return {
            "lat": cached["lat"],
            "lon": cached["lon"],
            "display_name": cached["display_name"]
        }

    try:
        # Nominatim público: máximo de una solicitud por segundo por aplicación.
        global _nominatim_last_request
        with _nominatim_lock:
            wait = 1.05 - (time.monotonic() - _nominatim_last_request)
            if wait > 0:
                time.sleep(wait)
            response = requests.get(
                NOMINATIM_URL,
                params={"q": location, "format": "jsonv2", "limit": 1, "addressdetails": 1, "countrycodes": "us"},
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT
            )
            _nominatim_last_request = time.monotonic()
        response.raise_for_status()
        results = response.json()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo localizar la ciudad: {exc}")

    if not results:
        raise HTTPException(status_code=404, detail="No encontramos esa ubicación. Prueba con ciudad y estado, por ejemplo: Ogden, Utah.")

    place = results[0]
    result = {
        "lat": float(place["lat"]),
        "lon": float(place["lon"]),
        "display_name": place.get("display_name", location)
    }
    with db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO geocode_cache(query, lat, lon, display_name, saved_at) VALUES (?, ?, ?, ?, ?)",
            (normalized, result["lat"], result["lon"], result["display_name"], int(time.time()))
        )
    return result


def build_overpass_query(lat: float, lon: float, radius: int, category: str):
    selectors = CATEGORY_TAGS[category]
    clauses = "\n".join(f"  {selector}(around:{radius},{lat},{lon});" for selector in selectors)
    return f"""
    [out:json][timeout:30];
    (
    {clauses}
    );
    out center tags;
    """


def clean_element(element, origin_lat, origin_lon):
    tags = element.get("tags", {})
    lat = element.get("lat")
    lon = element.get("lon")
    if lat is None or lon is None:
        center = element.get("center", {})
        lat, lon = center.get("lat"), center.get("lon")
    if lat is None or lon is None:
        return None

    name = tags.get("name") or tags.get("operator") or tags.get("brand") or "Lugar comunitario sin nombre"
    address_parts = [
        tags.get("addr:housenumber"),
        tags.get("addr:street"),
        tags.get("addr:city"),
        tags.get("addr:state"),
        tags.get("addr:postcode")
    ]
    address = " ".join(str(x) for x in address_parts if x) or "Dirección no registrada"
    website = tags.get("website") or tags.get("contact:website")
    phone = tags.get("phone") or tags.get("contact:phone")
    distance = haversine_km(origin_lat, origin_lon, float(lat), float(lon))

    return {
        "id": f'{element.get("type")}/{element.get("id")}',
        "name": name,
        "lat": float(lat),
        "lon": float(lon),
        "address": address,
        "phone": phone,
        "website": website,
        "distance_km": round(distance, 2),
        "category_detail": tags.get("social_facility") or tags.get("amenity") or tags.get("office") or "community",
        "osm_url": f'https://www.openstreetmap.org/{element.get("type")}/{element.get("id")}'
    }


@app.get("/")
def home():
    return FileResponse(BASE_DIR / "frontend" / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "LocalHelp", "version": "1.0.0"}


@app.get("/api/search")
def search_resources(
    location: str = Query(..., min_length=2, max_length=160),
    category: str = Query("food"),
    radius_km: int = Query(10, ge=1, le=50)
):
    if category not in CATEGORY_TAGS:
        raise HTTPException(status_code=400, detail="Categoría no válida.")

    place = geocode_location(location)
    radius_m = radius_km * 1000
    query = build_overpass_query(place["lat"], place["lon"], radius_m, category)

    try:
        response = requests.post(
            OVERPASS_URL,
            data={"data": query},
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail="El servicio de mapas está ocupado o no responde. Intenta nuevamente en unos minutos."
        ) from exc
    except ValueError:
        raise HTTPException(status_code=502, detail="El servicio de mapas devolvió una respuesta no válida.")

    found = []
    seen = set()
    for element in payload.get("elements", []):
        item = clean_element(element, place["lat"], place["lon"])
        if item and item["id"] not in seen:
            seen.add(item["id"])
            found.append(item)

    found.sort(key=lambda item: item["distance_km"])
    return {
        "location": place["display_name"],
        "coordinates": {"lat": place["lat"], "lon": place["lon"]},
        "category": category,
        "radius_km": radius_km,
        "count": len(found),
        "results": found,
        "source": "OpenStreetMap / Overpass API",
        "notice": "Los datos provienen de OpenStreetMap. Confirma directamente con cada organización sus servicios, horarios y disponibilidad."
    }


@app.post("/api/requests", status_code=201)
def register_request(record: RequestRecord):
    # Demo educativa: no se solicitan nombres legales ni datos sensibles.
    with db() as conn:
        cursor = conn.execute(
            "INSERT INTO requests(alias, need, city) VALUES (?, ?, ?)",
            (record.alias.strip(), record.need.strip(), record.city.strip())
        )
        request_id = cursor.lastrowid
    return {"message": "Solicitud guardada en la base de datos local.", "id": request_id}


@app.get("/api/categories")
def categories():
    return [
        {"id": "food", "name": "Alimentación"},
        {"id": "housing", "name": "Vivienda y refugios"},
        {"id": "health", "name": "Salud"},
        {"id": "education", "name": "Educación"},
        {"id": "employment", "name": "Empleo"},
        {"id": "community", "name": "Ayuda comunitaria"}
    ]
