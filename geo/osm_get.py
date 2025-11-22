#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
osm_get.py

- 從本機 SQLite（osm_poi.sqlite3）查附近 POI
- 對應 build_osm_poi_db.py 產生的 pois 表
- 分成 6 大類：
    fuel     → 加油站
    transit  → 公車站（其實是大眾運輸節點，含捷運/火車/客運/渡輪…）
    school   → 校園
    parking  → 停車場
    scenic   → 景點（公園 / 觀光點 / 自然 / 歷史…）
    cinema   → 電影院 / 影視文化場館
"""

from __future__ import annotations
import sqlite3
import json
from math import radians, sin, cos, asin, sqrt
from typing import Dict, List, Tuple, Optional

# =====================================================
#   分類規則（要跟 build_osm_poi_db 的 *_KEEP 系列對齊）
# =====================================================

AMENITY_PARKING = {
    "parking",
    "parking_entrance",
    "parking_space",
    "bicycle_parking",
    "motorcycle_parking",
}

AMENITY_SCHOOL = {
    "kindergarten",
    "school",
    "college",
    "university",
    "language_school",
    "music_school",
    "driving_school",
}

AMENITY_CINEMA = {
    "cinema",
    "theatre",
    "arts_centre",
    "planetarium",
}

AMENITY_TRANSIT = {
    "bus_station",
    "ferry_terminal",
    "taxi",
}

AMENITY_FUEL = {"fuel"}

LEISURE_SCENIC = {
    "park",
    "garden",
    "playground",
    "pitch",
    "stadium",
    "sports_centre",
    "swimming_pool",
    "water_park",
    "nature_reserve",
    "golf_course",
    "marina",
    "beach_resort",
    "recreation_ground",
}

TOURISM_SCENIC = {
    "attraction",
    "viewpoint",
    "museum",
    "gallery",
    "theme_park",
    "zoo",
    "aquarium",
    "artwork",
    "picnic_site",
    "information",
    "camp_site",
    "caravan_site",
    "alpine_hut",
    "wilderness_hut",
    "chalet",
    "hotel",
    "motel",
    "guest_house",
    "hostel",
    "resort",
}

NATURAL_SCENIC = {
    "peak",
    "volcano",
    "spring",
    "hot_spring",
    "cave_entrance",
    "waterfall",
    "cliff",
    "bay",
    "beach",
    "cape",
    "dune",
    "wood",
    "forest",
}

HISTORIC_SCENIC = {
    "castle",
    "fort",
    "ruins",
    "archaeological_site",
    "monument",
    "memorial",
    "battlefield",
    "wayside_cross",
    "wayside_shrine",
    "heritage",
}

HIGHWAY_TRANSIT = {"bus_stop"}

RAILWAY_TRANSIT = {
    "station",
    "halt",
    "tram_stop",
    "subway_entrance",
    "light_rail",
    "stop",
    "platform",
}

PUBLIC_TRANSPORT_TRANSIT = {
    "stop_position",
    "platform",
    "station",
    "stop_area",
    "stop_area_group",
}

AEROWAY_TRANSIT = {
    "aerodrome",
    "terminal",
    "helipad",
}

WATERWAY_SCENIC = {
    "dam",
    "waterfall",
    "lock_gate",
    "weir",
}

MAN_MADE_SCENIC = {
    "pier",
    "lighthouse",
    "tower",
    "water_tower",
    "windmill",
    "watermill",
}

AERIALWAY_TRANSIT = {"station"}


# =====================================================
#   SQLite 連線共用（減少重複開關檔案）
# =====================================================

_CONN: Optional[sqlite3.Connection] = None
_CONN_PATH: Optional[str] = None


def _get_conn(db_path: str) -> sqlite3.Connection:
    global _CONN, _CONN_PATH
    if _CONN is None or _CONN_PATH != db_path:
        if _CONN is not None:
            _CONN.close()
        _CONN = sqlite3.connect(db_path)
        _CONN.row_factory = sqlite3.Row
        _CONN_PATH = db_path
    return _CONN


# =====================================================
#   工具：距離 / 邊界盒
# =====================================================

def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """回傳兩點間距離（公尺）"""
    R = 6371000.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lng2 - lng1)

    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    c = 2 * asin(min(1.0, sqrt(a)))
    return R * c


def _bounding_box(lat: float, lng: float, radius_m: float) -> Tuple[float, float, float, float]:
    """
    粗略抓一個經緯度 bbox：
    - 緯度約 1° ≈ 111 km
    - 經度的 1° 要乘上 cos(lat)
    """
    dlat = radius_m / 111_000.0
    dlng = radius_m / (111_000.0 * cos(radians(lat)) if cos(radians(lat)) != 0 else 1e-6)
    return lat - dlat, lat + dlat, lng - dlng, lng + dlng


# =====================================================
#   分群邏輯：決定一個 POI 落在哪些 group
# =====================================================

def _groups_for_tags(tags: Dict[str, str]) -> List[str]:
    """
    根據 tags 決定此 POI 屬於哪些類別：
    fuel / parking / school / cinema / scenic / transit
    可能同時落在多個類別（例如：有些景點又是歷史建物）
    """
    groups = []

    amenity = tags.get("amenity")
    leisure = tags.get("leisure")
    tourism = tags.get("tourism")
    natural = tags.get("natural")
    historic = tags.get("historic")
    highway = tags.get("highway")
    railway = tags.get("railway")
    public_transport = tags.get("public_transport")
    aeroway = tags.get("aeroway")
    waterway = tags.get("waterway")
    man_made = tags.get("man_made")
    aerialway = tags.get("aerialway")

    # 1) fuel
    if amenity in AMENITY_FUEL:
        groups.append("fuel")

    # 2) parking
    if amenity in AMENITY_PARKING:
        groups.append("parking")

    # 3) school
    if amenity in AMENITY_SCHOOL:
        groups.append("school")

    # 4) cinema
    if amenity in AMENITY_CINEMA:
        groups.append("cinema")

    # 5) scenic：leisure / tourism / natural / historic / 部分 waterway / man_made
    if (
        leisure in LEISURE_SCENIC
        or tourism in TOURISM_SCENIC
        or natural in NATURAL_SCENIC
        or historic in HISTORIC_SCENIC
        or waterway in WATERWAY_SCENIC
        or man_made in MAN_MADE_SCENIC
    ):
        groups.append("scenic")

    # 6) transit：公車站 / 車站 / 捷運 / 公車月台 / 機場 / 渡輪…
    if (
        amenity in AMENITY_TRANSIT
        or highway in HIGHWAY_TRANSIT
        or railway in RAILWAY_TRANSIT
        or public_transport in PUBLIC_TRANSPORT_TRANSIT
        or aeroway in AEROWAY_TRANSIT
        or aerialway in AERIALWAY_TRANSIT
    ):
        groups.append("transit")

    return groups


# =====================================================
#   主函式：survey_latlng
# =====================================================

def survey_latlng(
    lat: float,
    lng: float,
    radius_m: float = 500.0,
    db_path: str = "osm_poi.sqlite3",
    top_n_per_group: int = 5,
) -> dict:
    """
    - 在本機 SQLite DB 裡查 radius_m 公尺內的 POI
    - 回傳 summary + 各 group 的詳細資料（含距離）

    回傳格式：
    {
        "location": {"lat": ..., "lng": ...},
        "radius_m": ...,
        "summary": {
            "fuel": 3,
            "transit": 10,
            "school": 1,
            "parking": 5,
            "scenic": 7,
            "cinema": 0,
        },
        "details": {
            "fuel":   [ {...}, ... ],
            "transit":[ {...}, ... ],
            ...
        }
    }
    """
    conn = _get_conn(db_path)
    cur = conn.cursor()

    lat_min, lat_max, lng_min, lng_max = _bounding_box(lat, lng, radius_m)

    # 先用 bbox 粗抓，後面再用 haversine 精確篩距離
    cur.execute(
        """
        SELECT id_str, osm_type, osm_id, lat, lng, tags_json
        FROM pois
        WHERE lat BETWEEN ? AND ?
          AND lng BETWEEN ? AND ?
        """,
        (lat_min, lat_max, lng_min, lng_max),
    )
    rows = cur.fetchall()

    # 初始化容器
    details: Dict[str, List[dict]] = {
        "fuel": [],
        "transit": [],
        "school": [],
        "parking": [],
        "scenic": [],
        "cinema": [],
    }

    # 遍歷結果，計算距離 + 分群
    for r in rows:
        r_lat = r["lat"]
        r_lng = r["lng"]
        dist = _haversine_m(lat, lng, r_lat, r_lng)

        if dist > radius_m:
            continue  # 超出半徑

        try:
            tags = json.loads(r["tags_json"]) if r["tags_json"] else {}
        except Exception:
            tags = {}

        item = {
            "id": r["id_str"],
            "osm_type": r["osm_type"],
            "osm_id": r["osm_id"],
            "lat": r_lat,
            "lng": r_lng,
            "distance_m": round(dist, 1),
            "name": tags.get("name:zh") or tags.get("name") or tags.get("name:en"),
            "tags": tags,
        }

        groups = _groups_for_tags(tags)
        for g in groups:
            details[g].append(item)

    # 各 group 依距離排序
    for g in details:
        details[g].sort(key=lambda x: x["distance_m"])

    # summary：各類別數量
    summary = {g: len(details[g]) for g in details}

    # 可以順便裁個 top_n 給 debug 用（不影響 CSV，CSV 只用 summary）
    truncated_details = {
        g: items[:top_n_per_group] for g, items in details.items()
    }

    return {
        "location": {"lat": lat, "lng": lng},
        "radius_m": radius_m,
        "summary": summary,
        "details": truncated_details,
    }


if __name__ == "__main__":
    # 小測試：台北車站附近
    lat, lng = 25.047923, 121.517081
    result = survey_latlng(lat, lng, radius_m=500.0, db_path="osm_poi.sqlite3")
    print("summary =", result["summary"])
