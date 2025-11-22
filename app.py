#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# app.py
from __future__ import annotations
from typing import Any, Dict
from pathlib import Path

from flask import Flask, request, jsonify, render_template

from geo import geocode_arcgis as gc
from geo import osm_get

from models import survival_predict

BASE_DIR = Path(__file__).resolve().parent

app = Flask(__name__)


@app.route("/")
def index():
    # 只負責回 HTML，資料用 JS 去打 /api/search
    return render_template("index.html")

@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json(silent=True) or {}

    # 前端傳來
    address = str(data.get("address", "")).strip()
    radius_str = str(data.get("radius_m", "500")).strip()
    total_asset = data.get("total_asset")
    industry_value = data.get("industry")
    model_year_raw = data.get("model_year", 5)
    if not address:
        return jsonify({"ok": False, "error": "請先輸入地址。"}), 400

    # 總資產檢查
    try:
        total_asset = float(total_asset)
        if total_asset < 0:
            raise ValueError
    except Exception:
        return jsonify({"ok": False, "error": "總資產格式不正確。"}), 400

    # 行業別檢查
    if not industry_value:
        return jsonify({"ok": False, "error": "請選擇行業別。"}), 400

    try:
        model_year = int(model_year_raw)
    except Exception:
        model_year = 5

    if model_year not in (3, 5, 7, 10, 15):
        model_year = 5

    # 半徑處理
    try:
        radius_m = float(radius_str)
        if radius_m <= 0:
            raise ValueError
    except Exception:
        radius_m = 500.0

    # 1) geocode 地址 → 座標 + 縣市 / 行政區
    g = gc.geocode(address)
    if not g:
        return jsonify({"ok": False, "error": "ArcGIS 找不到這個地址，請試試看調整地址格式。"}), 404

    lat = g["lat"]
    lng = g["lon"]
    city = g.get("city")          # 例如 "臺北市"
    district = g.get("district")  # 例如 "大安區"

    # 2) 查 OSM DB 附近 POI
    try:
        result = osm_get.survey_latlng(
            lat=lat,
            lng=lng,
            radius_m=radius_m,
            db_path=str("geo/osm_poi.sqlite3"),
            top_n_per_group=5,
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"查詢 OSM DB 時發生錯誤：{e}"}), 500

    summary = result["summary"]  # fuel / transit / school / parking / scenic / cinema

    # 3) 組合成模型需要的 new_shop dict
    #    這裡特別注意：
    #    - "推測縣市": 你訓練資料若是 "臺北市" 就寫 city；如果是 "推測縣市_臺北市" 就照下面這樣組
    #    - "industry": 前端就傳像 "industry_飲料店業"
    guessed_city_value = None
    if city:
        guessed_city_value = f"推測縣市_{city}"   # 跟你範例 new_shop 一致

    new_shop = {
        "總資產": total_asset,
        "加油站": summary.get("fuel", 0),
        "大眾運輸": summary.get("transit", 0),
        "校園": summary.get("school", 0),
        "停車場": summary.get("parking", 0),
        "景點": summary.get("scenic", 0),
        "電影院": summary.get("cinema", 0),
        "推測縣市": guessed_city_value,
        "行政區": district,
        "industry": industry_value,
    }

    # 4) 丟進生存模型做預測
    surv = survival_predict.predict_new_shop(new_shop, model_year=model_year)

    # 轉成給前端好懂的文字
    label = "✅ 建議投資 (存活)" if surv["prediction"] == 1 else "❌ 風險過高 (倒閉)"

    resp: Dict[str, Any] = {
        "ok": True,
        "address_input": address,
        "geocode": {
            "lat": lat,
            "lng": lng,
            "match_addr": g.get("match_addr"),
            "score": g.get("score"),
            "city": city,
            "district": district,
        },
        "radius_m": radius_m,
        "top_n_per_group": 5,
        "result": result,        # 原本的 POI 統計 + 詳細資料
        "survival": {            # 新增：生存預測結果
            "prob": surv["prob"],
            "threshold": surv["threshold"],
            "prediction": surv["prediction"],
            "label": label,
            "features_used": new_shop,  # 方便你 debug 看實際特徵值
        },
    }
    return jsonify(resp)




if __name__ == "__main__":
    # 開發環境用，正式上線可以換 gunicorn / waitress 等
    app.run(host="0.0.0.0", port=5000, debug=True)
