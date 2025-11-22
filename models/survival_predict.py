#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import joblib
from pathlib import Path
from typing import Dict, Any

# models 資料夾路徑
MODEL_DIR = Path(__file__).resolve().parent

# 簡單快取：同一個模型檔只載一次
_MODEL_CACHE: Dict[str, Any] = {}

# 年份對應到模型檔名
MODEL_FILE_MAP: Dict[int, str] = {
    3:  "survival_model_3years.pkl",
    5:  "survival_model_5years.pkl",
    7:  "survival_model_7years.pkl",
    10: "survival_model_10years.pkl",
    15: "survival_model_15years.pkl",
}


def _load_package_by_year(model_year: int):
    if model_year not in MODEL_FILE_MAP:
        raise ValueError(f"不支援的預測年限：{model_year} 年")

    filename = MODEL_FILE_MAP[model_year]
    full_path = MODEL_DIR / filename

    if filename not in _MODEL_CACHE:
        print(f"[DEBUG] loading model for {model_year} years from: {full_path}")
        _MODEL_CACHE[filename] = joblib.load(full_path)

    return _MODEL_CACHE[filename]


def predict_new_shop(new_data_dict: dict, model_year: int = 5) -> dict:

    package = _load_package_by_year(model_year)

    forest = package["model"]
    district_map = package["district_map"]
    global_mean = package["global_mean"]
    threshold = package["threshold"]
    train_features = package["features"]

    # 2. 新資料 → DataFrame
    df = pd.DataFrame([new_data_dict])

    # 3. One-Hot Encoding
    df_encoded = pd.get_dummies(df)

    # 4. 欄位對齊
    df_final = df_encoded.reindex(columns=train_features, fill_value=0)

    # 5. Target Encoding (行政區)
    district = new_data_dict.get("行政區")
    if district in district_map.index:
        survival_rate = district_map[district]
    else:
        survival_rate = global_mean

    df_final["District_Survival_Rate"] = survival_rate

    # 6. 預測機率
    prob = float(forest.predict_proba(df_final)[0, 1])
    prediction = int(prob >= float(threshold))

    return {
        "prob": prob,
        "threshold": float(threshold),
        "prediction": prediction,
        "year": int(model_year),
    }
