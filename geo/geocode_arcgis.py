#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from typing import Dict, Optional, Any
import requests
import re

ARCGIS_URL = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"

# 常見台灣縣市（可以再補你需要的）
TW_CITIES = [
    "臺北市", "台北市",
    "新北市",
    "基隆市",
    "桃園市",
    "新竹市", "新竹縣",
    "苗栗縣",
    "臺中市", "台中市",
    "彰化縣",
    "南投縣",
    "雲林縣",
    "嘉義市", "嘉義縣",
    "臺南市", "台南市",
    "高雄市",
    "屏東縣",
    "宜蘭縣",
    "花蓮縣",
    "臺東縣", "台東縣",
    "澎湖縣",
    "金門縣",
    "連江縣",
]


def _guess_tw_city_district(addr: str) -> Dict[str, Optional[str]]:
    if not addr:
        return {"city": None, "district": None}

    addr = addr.strip()
    # 把開頭的 3~5 位數郵遞區號拿掉，例如「100臺北市…」→「臺北市…」
    addr = re.sub(r"^\s*\d{3,5}", "", addr)

    city_found = None
    rest = addr
    for city in TW_CITIES:
        if addr.startswith(city):
            city_found = city
            rest = addr[len(city):]  # 去掉縣市，剩後面
            break

    if city_found is None:
        return {"city": None, "district": None}

    # 後半段找「○○市／○○區／○○鎮／○○鄉／○○村／○○里」
    m = re.match(r"(.+?(市|區|鎮|鄉|村|里))", rest)
    if not m:
        return {"city": city_found, "district": None}

    district = m.group(1)
    return {"city": city_found, "district": district}

def geocode(address: str, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
    if not address:
        return None

    params = {
        "SingleLine": address,
        "f": "json",
        "outSR": '{"wkid":4326}',
        "outFields": "Addr_type,Match_addr,StAddr,City,Region,Subregion,Country",
        "maxLocations": 6,
    }

    try:
        r = requests.get(ARCGIS_URL, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        cands = data.get("candidates", [])
        if not cands:
            return None

        best = max(cands, key=lambda c: c.get("score", 0))
        loc = best.get("location", {})
        attrs = best.get("attributes", {}) or {}

        match_addr = (
            best.get("matchAddress")
            or best.get("address")
            or best.get("Match_addr")
        )
        score = best.get("score", 0)

        # 只會有台灣地址 → 一律用中文地址來拆縣市／行政區
        guess = _guess_tw_city_district(match_addr or address)
        city_final = guess["city"]      # 例如「臺北市」
        district_final = guess["district"]  # 例如「中正區」

        return {
            "lat": loc.get("y"),
            "lon": loc.get("x"),
            "match_addr": match_addr,
            "score": score,
            "city": city_final,
            "district": district_final,
            "raw_attrs": attrs,  # 若要 debug 還是留著
        }
    except Exception as e:
        sys.stderr.write(f"[ERROR] geocode failed for '{address}': {e}\n")
        return None




def main() -> int:
    res = geocode("臺北市大安區新生南路三段1號")
    print(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
