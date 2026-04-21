"""
rebuild_spot_map.py — 対応表の再計算バッチ

役割:
  spot_station_map.json の全行について、現在の stations_master.json をもとに
  nearest_station / distance_km / current_point / current_distance_km / sea_area
  を再計算する。

保護ロジック（W2-2 §8.3 / §7.4）:
  - confidence != "auto" の行は分類結果で上書きしない
  - ただし distance_km 等の「座標変更に追随すべき数値」は confidence によらず更新する
    （座標が同じなら結果も同じなので実害ゼロ、座標が変わった場合のみ意味を持つ）
  - 名前系（nearest_station / current_point / sea_area）は confidence=auto の行のみ上書きする

使い方:
  python rebuild_spot_map.py                       # 既定パス
  python rebuild_spot_map.py --dry-run             # 書き換え差分だけ表示
  python rebuild_spot_map.py --map PATH --stations PATH --rules PATH
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent  # fishing-collector/
sys.path.insert(0, str(REPO_ROOT))

from engines.spot_classifier import SpotClassifier, OTHER_SENTINEL  # noqa: E402


DEFAULT_MAP = REPO_ROOT / "data" / "b_mapping" / "spot_station_map.json"
DEFAULT_STATIONS = REPO_ROOT / "data" / "b_mapping" / "stations_master.json"
DEFAULT_RULES = REPO_ROOT / "data" / "b_mapping" / "spot_canonical_rules.json"

JST = timezone(timedelta(hours=9))

SEA_AREA_BY_STATION = {
    "室戸": "室戸沖",
    "高知": "土佐湾",
    "足摺": "足摺沖",
    "宇和島": "豊後水道",
    "松山": "瀬戸内中予",
    "来島": "燧灘",
    "高松": "讃岐瀬戸",
    "阿南": "紀伊水道",
}


def decide_sea_area(canonical: str, nearest_station: str | None) -> str:
    if nearest_station == OTHER_SENTINEL:
        if canonical == "小笠原":
            return "小笠原"
        return "その他海域"
    if nearest_station is None:
        return "その他海域"
    return SEA_AREA_BY_STATION.get(nearest_station, "その他海域")


def rebuild(
    map_path: Path,
    stations_path: Path,
    rules_path: Path,
    dry_run: bool = False,
) -> int:
    with map_path.open(encoding="utf-8") as f:
        doc = json.load(f)

    # W7-4: spot_station_map を classifier に渡すことで、海流マッチが sea_area 階層化される。
    # decide_sea_area() / SEA_AREA_BY_STATION は nearest_station（weather）起点のため不変。
    # 案I-light: 既存 spots[].sea_area は rebuild 時に decide_sea_area() が再計算する
    # 従来挙動を維持（classifier への入力としてのみ利用される）。
    clf = SpotClassifier(stations_path, rules_path, spot_station_map_path=map_path)

    now_iso = datetime.now(JST).replace(microsecond=0).isoformat()
    diffs: list[str] = []

    for entry in doc.get("spots", []):
        canonical = entry.get("canonical_spot", "")
        lat = entry.get("spot_lat")
        lng = entry.get("spot_lng")
        confidence = entry.get("confidence", "auto")

        if lat is None or lng is None:
            continue

        result = clf.classify(canonical, lat, lng)

        def r6(x):
            return round(x, 6) if x is not None else None

        new_distance_km = r6(result.distance_km)
        new_current_distance_km = r6(result.current_distance_km)

        # 距離数値は常に更新（座標が変わった場合の追随）
        changed = False
        if entry.get("distance_km") != new_distance_km:
            diffs.append(
                f"{canonical}: distance_km "
                f"{entry.get('distance_km')} → {new_distance_km}"
            )
            entry["distance_km"] = new_distance_km
            changed = True
        if entry.get("current_distance_km") != new_current_distance_km:
            diffs.append(
                f"{canonical}: current_distance_km "
                f"{entry.get('current_distance_km')} → {new_current_distance_km}"
            )
            entry["current_distance_km"] = new_current_distance_km
            changed = True

        # 名前系は confidence=auto の行のみ上書き
        if confidence == "auto":
            new_sea_area = decide_sea_area(canonical, result.nearest_station)
            for key, new_val in (
                ("nearest_station", result.nearest_station),
                ("current_point", result.current_point),
                ("sea_area", new_sea_area),
            ):
                if entry.get(key) != new_val:
                    diffs.append(
                        f"{canonical}: {key} "
                        f"{entry.get(key)!r} → {new_val!r}"
                    )
                    entry[key] = new_val
                    changed = True
        else:
            # verified/manual は名前系を保護するが、ログは出す
            new_sea_area = decide_sea_area(canonical, result.nearest_station)
            for key, new_val in (
                ("nearest_station", result.nearest_station),
                ("current_point", result.current_point),
                ("sea_area", new_sea_area),
            ):
                if entry.get(key) != new_val:
                    diffs.append(
                        f"[PROTECTED by confidence={confidence}] "
                        f"{canonical}: {key} {entry.get(key)!r} "
                        f"would become {new_val!r}"
                    )

        if changed:
            entry["updated_at"] = now_iso

    doc["updated_at"] = now_iso

    if dry_run:
        print("=== DRY RUN ===")
        for d in diffs:
            print(d)
        print(f"\n{len(diffs)} differences detected")
        return 0

    if diffs:
        with map_path.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        print(f"[OK] rewrote {map_path}")
        for d in diffs:
            print(d)
        print(f"\n{len(diffs)} differences applied")
    else:
        print("[OK] no changes")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="spot_station_map.json を再計算する")
    p.add_argument("--map", default=str(DEFAULT_MAP))
    p.add_argument("--stations", default=str(DEFAULT_STATIONS))
    p.add_argument("--rules", default=str(DEFAULT_RULES))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    sys.exit(
        rebuild(Path(args.map), Path(args.stations), Path(args.rules), args.dry_run)
    )


if __name__ == "__main__":
    main()
