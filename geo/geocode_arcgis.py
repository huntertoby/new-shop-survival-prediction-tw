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

    city_found = None
    for city in TW_CITIES:
        if addr.startswith(city):
            city_found = city
            rest = addr[len(city):]  # 去掉縣市，剩下後面
            break

    if city_found is None:
        return {"city": None, "district": None}

    # 後半段找「○○市／○○區／○○鎮／○○鄉／○○村／○○里」之類
    m = re.match(r"(.+?(市|區|鎮|鄉|村|里))", rest)
    if not m:
        return {"city": city_found, "district": None}

    district = m.group(1)
    return {"city": city_found, "district": district}


def geocode(address: str, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
    """給定地址，回傳 {'lat','lon','match_addr','score','city','district'}；找不到回傳 None。"""
    if not address:
        return None

    params = {
        "SingleLine": address,
        "f": "json",
        "outSR": '{"wkid":4326}',
        # 把 City / Region / Subregion 都拿回來，比較有機會直接用官方欄位
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

        # 1) 先用 ArcGIS 提供的 City / Subregion
        city_attr = attrs.get("City")
        subregion_attr = attrs.get("Subregion")  # 有些國家會把「行政區」丟這
        # Region 通常是省份或較大區域，例如 "Taiwan" / "Taipei"
        region_attr = attrs.get("Region")

        # 2) 針對台灣，再用中文地址字串拆一次（match_addr 優先，其次原始輸入）
        guess = _guess_tw_city_district(match_addr or address)
        city_guess = guess["city"]
        district_guess = guess["district"]

        # 3) 最後決定 city / district：
        #    - city：ArcGIS 的 City 優先；沒有就用我們猜的 city_guess
        #    - district：ArcGIS 的 Subregion 優先；沒有就用 district_guess
        city_final = city_attr or city_guess
        district_final = subregion_attr or district_guess

        return {
            "lat": loc.get("y"),
            "lon": loc.get("x"),
            "match_addr": match_addr,
            "score": score,
            "city": city_final,
            "district": district_final,
            # 想 debug 的時候可以看這些原始欄位
            "raw_attrs": {
                "City": city_attr,
                "Subregion": subregion_attr,
                "Region": region_attr,
                "Country": attrs.get("Country"),
            },
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
