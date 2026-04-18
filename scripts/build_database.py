#!/usr/bin/env python3
"""
室戸沖釣果データ収集ソフト V2.0 — 統合ビルドスクリプト
====================================================

3つのデータソースを結合し、CSV と JSデータファイルを生成する。
PC上でもGitHub Actions上でも同じスクリプトで動作する。

【入力ファイル】（data/ フォルダ内）
  1. fishing_data.csv        ← 釣果データ（手動更新）
  2. fishing_condition_db.csv ← 環境条件データ（v6.0 自動更新）
  3. muroto_offshore_current_all.csv ← 潮流データ（v2.0 自動更新）

【出力ファイル】（ルート直下 — GitHub Pages公開対象）
  1. fishing_muroto_v1.csv      ← 統合CSVデータ
  2. fishing_muroto_v1_data.js  ← HTMLが読み込むJSデータ

【使い方】
  python scripts/build_database.py          # 通常実行
  python scripts/build_database.py --quiet  # ログ抑制（CI用）
"""

import csv
import os
import sys
from pathlib import Path
from datetime import datetime

# =============================================================================
# パス設定（スクリプト位置からの相対パス — PC/CI両対応）
# =============================================================================
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

# 入力
DATA_DIR = PROJECT_ROOT / "data"
FISHING_CSV   = DATA_DIR / "fishing_data.csv"
CONDITION_CSV = DATA_DIR / "fishing_condition_db.csv"
CURRENT_CSV   = DATA_DIR / "muroto_offshore_current_all.csv"

# 出力（ルート直下 = GitHub Pages公開対象）
OUTPUT_CSV = PROJECT_ROOT / "data" / "fishing_muroto_v1.csv"
OUTPUT_JS  = PROJECT_ROOT / "data" / "js" / "fishing_muroto_v1_data.js"

# =============================================================================
# オプション
# =============================================================================
QUIET = "--quiet" in sys.argv

def log(msg):
    if not QUIET:
        print(msg)

# =============================================================================
# 出力カラム定義
# =============================================================================
FISHING_BASE_COLS = [
    "date", "time", "species", "size_cm", "weight_kg", "count",
    "bait", "method", "spot", "spot_lat", "spot_lng", "nearest_station",
    "tide", "weather", "temp", "water_temp", "wind", "memo", "source"
]

TIDAL_MOON_COLS = ["潮汐", "月齢", "月相"]

CURRENT_ADD_COLS = [
    "室戸沖_流速kn", "室戸沖_流向", "室戸沖_水温", "室戸沖_塩分",
    "北西_流速kn", "北西_流向", "北西_水温", "北西_塩分"
]

# V2.0追加: 気象データ12列（fishing_condition_db.csv より）
WEATHER_ADD_COLS = [
    "気温_平均", "気温_最高", "気温_最低",
    "風速_最大", "風向", "降水量",
    "天気コード", "天気", "水温(Open-Meteo)",
    "最大波高", "波向", "波周期"
]

OUTPUT_COLS = FISHING_BASE_COLS + TIDAL_MOON_COLS + CURRENT_ADD_COLS + WEATHER_ADD_COLS

# =============================================================================
# メイン処理
# =============================================================================
def main():
    log("=" * 60)
    log("室戸沖釣果データ収集ソフト V2.0 — 統合ビルド")
    log(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)

    # --- 入力ファイル存在チェック ---
    missing = []
    for f in [FISHING_CSV, CONDITION_CSV, CURRENT_CSV]:
        if not f.exists():
            missing.append(str(f))
    if missing:
        print(f"❌ 入力ファイルが見つかりません:")
        for m in missing:
            print(f"   {m}")
        sys.exit(1)

    # --- Step 1: 釣果データ読み込み ---
    log("\n[Step 1] 釣果データ読み込み")
    with open(FISHING_CSV, "r", encoding="utf-8-sig") as f:
        fishing_rows = list(csv.DictReader(f))
    log(f"  レコード数: {len(fishing_rows)}")

    # --- Step 2: 条件DB → 潮汐・月齢・気象データの辞書構築 ---
    log("\n[Step 2] 条件DB読み込み（潮汐・月齢・気象12列）")
    condition_map = {}
    with open(CONDITION_CSV, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row["日付"], row["地点名"])
            condition_map[key] = {
                # 潮汐・月齢
                "潮汐": row.get("潮汐", ""),
                "月齢": row.get("月齢", ""),
                "月相": row.get("月相", ""),
                # 気象データ（V2.0追加）
                "気温_平均":        row.get("気温_平均", ""),
                "気温_最高":        row.get("気温_最高", ""),
                "気温_最低":        row.get("気温_最低", ""),
                "風速_最大":        row.get("風速_最大", ""),
                "風向":             row.get("風向", ""),
                "降水量":           row.get("降水量", ""),
                "天気コード":       row.get("天気コード", ""),
                "天気":             row.get("天気", ""),
                "水温(Open-Meteo)": row.get("水温", ""),  # 半角カッコでリネーム
                "最大波高":         row.get("最大波高", ""),
                "波向":             row.get("波向", ""),
                "波周期":           row.get("波周期", ""),
            }
    log(f"  条件データ数: {len(condition_map)} (日付×地点)")

    # --- Step 3: 潮流データ → 室戸沖・北西を抽出・ピボット ---
    log("\n[Step 3] 潮流データ読み込み（室戸沖・北西）")
    TARGET_POINTS = ["室戸沖", "北西"]
    current_data = {}
    with open(CURRENT_CSV, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["point"] not in TARGET_POINTS:
                continue
            dt = row["date"]
            if dt not in current_data:
                current_data[dt] = {}
            current_data[dt][row["point"]] = {
                "speed_kn": row["speed_kn"],
                "direction": row["direction"],
                "temp_c": row["temp_c"],
                "salinity": row["salinity"],
            }
    log(f"  潮流データ日数: {len(current_data)}")

    # --- Step 4: 3データソースを結合 ---
    log("\n[Step 4] 結合処理")
    output_rows = []
    stats = {"tide_ok": 0, "tide_miss": 0, "cur_ok": 0, "cur_skip": 0, "cur_miss": 0}

    for row in fishing_rows:
        out = {}

        # (a) 釣果基本データ
        for col in FISHING_BASE_COLS:
            out[col] = row.get(col, "")

        # (b) 潮汐・月齢・気象データ (condition_db から)
        dt = row.get("date", "")
        station = row.get("nearest_station", "").strip()
        cond = condition_map.get((dt, station))
        if cond:
            out["潮汐"] = cond["潮汐"]
            out["月齢"] = cond["月齢"]
            out["月相"] = cond["月相"]
            # 気象データ12列
            for col in WEATHER_ADD_COLS:
                out[col] = cond.get(col, "")
            stats["tide_ok"] += 1
        else:
            out["潮汐"] = out["月齢"] = out["月相"] = ""
            for col in WEATHER_ADD_COLS:
                out[col] = ""
            stats["tide_miss"] += 1

        # (c) 潮流データ (spotに「室戸」を含むレコードのみ)
        for col in CURRENT_ADD_COLS:
            out[col] = ""

        spot = row.get("spot", "")
        if "室戸" in spot:
            cd = current_data.get(dt)
            if cd:
                for pt_name, prefix in [("室戸沖", "室戸沖"), ("北西", "北西")]:
                    if pt_name in cd:
                        out[f"{prefix}_流速kn"] = cd[pt_name]["speed_kn"]
                        out[f"{prefix}_流向"]   = cd[pt_name]["direction"]
                        out[f"{prefix}_水温"]   = cd[pt_name]["temp_c"]
                        out[f"{prefix}_塩分"]   = cd[pt_name]["salinity"]
                stats["cur_ok"] += 1
            else:
                stats["cur_miss"] += 1
        else:
            stats["cur_skip"] += 1

        output_rows.append(out)

    log(f"  全レコード: {len(output_rows)}")
    log(f"  潮汐結合成功: {stats['tide_ok']}, 失敗: {stats['tide_miss']}")
    log(f"  潮流結合成功: {stats['cur_ok']}, 室戸以外: {stats['cur_skip']}, 日付外: {stats['cur_miss']}")

    # --- Step 5: CSV出力 ---
    log("\n[Step 5] CSV出力")
    with open(OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLS)
        writer.writeheader()
        writer.writerows(output_rows)

    csv_size = OUTPUT_CSV.stat().st_size
    log(f"  {OUTPUT_CSV.name}: {csv_size:,} bytes")

    # --- Step 6: JSデータファイル生成 ---
    log("\n[Step 6] JSデータファイル生成")
    with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
        csv_text = f.read()

    escaped = csv_text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    js_content = (
        "// 自動生成ファイル — scripts/build_database.py により作成\n"
        "// 室戸沖釣果データ収集ソフト V2.0\n"
        "// このファイルを直接編集しないでください\n"
        f"// 生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"window.MUROTO_FISHING_CSV_TEXT = `{escaped}`;\n"
    )

    with open(OUTPUT_JS, "w", encoding="utf-8") as f:
        f.write(js_content)

    js_size = OUTPUT_JS.stat().st_size
    log(f"  {OUTPUT_JS.name}: {js_size:,} bytes")

    # --- 完了 ---
    log("\n" + "=" * 60)
    log(f"✅ ビルド完了 — {len(output_rows)}件 / 潮汐{stats['tide_ok']}件 / 潮流{stats['cur_ok']}件")
    log("=" * 60)

    # 常にサマリーを1行出力（CI向け）
    print(f"BUILD OK: {len(output_rows)} records, tide={stats['tide_ok']}, current={stats['cur_ok']}")

if __name__ == "__main__":
    main()
