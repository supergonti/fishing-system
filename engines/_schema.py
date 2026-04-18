"""
engines/_schema.py — Aマスター 26列スキーマの定義

設計準拠: 設計_W2-1_Aグループ_20260417.md §2.1

このモジュールは正規化レイヤー / quality_check / emit_* で共通利用する
列定義・値域・必須項目の真の所在地（single source of truth）。
"""

# 26列のマスタースキーマ列順（必ずこの順で master_catch.csv に書く）
MASTER_COLUMNS = [
    "record_id",        # 1  UUID v4 (必須)
    "date",             # 2  必須 YYYY-MM-DD
    "time",             # 3  HH:MM / 空
    "species",          # 4  必須
    "size_cm",          # 5  数値文字列 / 空
    "weight_kg",        # 6  数値文字列 / 空
    "count",            # 7  整数文字列 / 空
    "bait",             # 8
    "method",           # 9
    "spot",             # 10 必須 (生値)
    "spot_lat",         # 11
    "spot_lng",         # 12
    "nearest_station",  # 13
    "tide",             # 14
    "weather",          # 15
    "temp",             # 16 廃止候補（マスター上は空固定が原則）
    "water_temp",       # 17
    "wind",             # 18 廃止候補（マスター上は空固定が原則）
    "memo",             # 19
    "source",           # 20 必須 (小文字体系: instagram/manual/blog:.../...)
    "canonical_spot",   # 21 B側で埋める（予約）
    "sea_area",         # 22 B側で埋める（予約）
    "entered_at",       # 23 必須 ISO8601 JST
    "source_detail",    # 24
    "prompt_version",   # 25
    "confidence",       # 26
]

# 既存アプリ互換 fishing_data.csv の19列順
FISHING_DATA_COLUMNS = [
    "date", "time", "species", "size_cm", "weight_kg", "count",
    "bait", "method", "spot", "spot_lat", "spot_lng", "nearest_station",
    "tide", "weather", "temp", "water_temp", "wind", "memo", "source",
]

# 必須6列
REQUIRED_COLUMNS = [
    "record_id", "date", "species", "spot", "source", "entered_at",
]

# tide / weather の値域（W2-1 §2.1）
TIDE_VALUES = {"大潮", "中潮", "小潮", "長潮", "若潮"}
WEATHER_VALUES = {"晴れ", "曇り", "雨", "雪"}

# source の正規化マップ: 旧表記 → 内部小文字
SOURCE_INTERNAL_MAP = {
    "Instagram": "instagram",
    "instagram": "instagram",
    "Manual": "manual",
    "manual": "manual",
    "Other": "other",
    "other": "other",
}

# source の出力時大文字復元マップ (W3-3 §3.1.4)
SOURCE_OUTPUT_MAP = {
    "instagram": "Instagram",
    "manual": "Manual",
    "other": "Other",
}


def restore_source_case(internal_value: str) -> str:
    """内部小文字 → 出力大文字（既存アプリ互換）。

    `blog:<name>` / `import:csv_v5.5` / `ocr:<kind>` はプレフィックスで
    判定し、先頭を大文字化する（将来用）。
    """
    if not internal_value:
        return ""
    if internal_value in SOURCE_OUTPUT_MAP:
        return SOURCE_OUTPUT_MAP[internal_value]
    # プレフィックス系
    for prefix in ("blog:", "import:", "ocr:"):
        if internal_value.startswith(prefix):
            return prefix.capitalize() + internal_value[len(prefix):]
    # 未知値はそのまま返す（quality_check が検出する想定）
    return internal_value


def empty_master_record() -> dict:
    """26列すべて空文字で初期化した dict を返す。"""
    return {col: "" for col in MASTER_COLUMNS}
