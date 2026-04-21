"""
tests/test_sea_area_hierarchy.py — W7-4 current_points の sea_area 階層化 unit test

設計準拠:
  - 指示書_W7-4_current_points_海域階層化_20260420.md §4-5
  - 指示書_W7-4_補足_司令塔5_更新版_20260421.md（パッチ 0 案I-light 確定）
  - 計画書_司令塔5_釣り場分類人機協調改革_20260420.md §3-5 (sea_area 階層)

W7-4 における classify() 海流マッチ拡張:
  - spot_station_map_path を与えた場合、canonical → sea_area lookup を構築
  - classify() の海流マッチ部で、sea_area hit した場合は該当海域の current_points
    のみにフィルタしてから最近傍を計算
  - sea_area lookup miss（従来データ）→ フラット最近傍（後方互換）
  - sea_area フィルタ後に該当 current_point が 0 件 → current_point=None

後方互換:
  - spot_station_map_path=None で __init__ → _canonical_to_sea_area={} → 全キー miss
    → すべて全 current_points フラット最近傍（W7-4 以前の挙動）

整合性:
  - stations_master.json.current_points[] の sea_area 値集合は
    rebuild_spot_map.SEA_AREA_BY_STATION の values に含まれるべき

実行（pytest が入っていれば）:
  python -m pytest tests/test_sea_area_hierarchy.py -v

pytest を使わずにスモークテストしたい場合:
  python -m tests.test_sea_area_hierarchy
"""

from __future__ import annotations

import json
from pathlib import Path

from engines.spot_classifier import (
    CURRENT_DISTANCE_THRESHOLD_KM,
    SpotClassifier,
)


# ------------------------------------------------------------
# 共通ヘルパ
# ------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_STATIONS = _REPO_ROOT / "data" / "b_mapping" / "stations_master.json"
_RULES = _REPO_ROOT / "data" / "b_mapping" / "spot_canonical_rules.json"
_SPOT_MAP = _REPO_ROOT / "data" / "b_mapping" / "spot_station_map.json"


def _make_clf_hier() -> SpotClassifier:
    """sea_area 階層ありの classifier（W7-4 本番想定）"""
    return SpotClassifier(
        str(_STATIONS),
        str(_RULES),
        spot_station_map_path=str(_SPOT_MAP),
    )


def _make_clf_flat() -> SpotClassifier:
    """spot_station_map なしの classifier（W7-4 以前の後方互換挙動）"""
    return SpotClassifier(str(_STATIONS), str(_RULES))


# ------------------------------------------------------------
# テストケース：既存 5 点に sea_area="室戸沖" が付与されていること
# ------------------------------------------------------------
def test_stations_master_current_points_have_sea_area():
    """stations_master.json.current_points[] 全 5 点に sea_area: '室戸沖' が付与されている."""
    with _STATIONS.open(encoding="utf-8") as f:
        doc = json.load(f)
    current_points = doc.get("current_points", [])
    assert len(current_points) == 5
    for p in current_points:
        assert p.get("sea_area") == "室戸沖", f"missing or wrong sea_area in {p}"


# ------------------------------------------------------------
# テストケース：案I-light の整合性保証
# current_points の sea_area 値集合 ⊆ SEA_AREA_BY_STATION.values()
# ------------------------------------------------------------
def test_sea_area_values_within_master_mapping():
    """current_points[].sea_area の値集合は SEA_AREA_BY_STATION.values() に含まれる."""
    import sys
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    from rebuild_spot_map import SEA_AREA_BY_STATION  # noqa: E402

    with _STATIONS.open(encoding="utf-8") as f:
        doc = json.load(f)
    current_sea_areas = {p.get("sea_area") for p in doc.get("current_points", [])}
    master_sea_areas = set(SEA_AREA_BY_STATION.values())
    assert current_sea_areas <= master_sea_areas, (
        f"current_points に master 未登録の sea_area がある: "
        f"{current_sea_areas - master_sea_areas}"
    )


# ------------------------------------------------------------
# テストケース：室戸沖 spot が sea_area 階層経由で 5 点内に収まる
# ------------------------------------------------------------
def test_muroto_spot_uses_muroto_sea_area():
    """室戸沖 spot（座標あり）→ current_point は室戸沖 5 点のどれかに収まる."""
    clf = _make_clf_hier()
    r = clf.classify("室戸沖", 33.29, 134.18)
    assert r.current_point in ("室戸沖", "北東", "北西", "西", "東"), (
        f"unexpected current_point: {r.current_point!r}"
    )
    assert r.current_distance_km is not None
    assert r.current_distance_km <= CURRENT_DISTANCE_THRESHOLD_KM


# ------------------------------------------------------------
# テストケース：spot_map なし → フラット最近傍（後方互換）
# ------------------------------------------------------------
def test_no_spot_map_fallback_to_flat():
    """spot_station_map_path=None → フラット最近傍（W7-4 以前の挙動）."""
    clf = _make_clf_flat()
    r = clf.classify("室戸沖", 33.29, 134.18)
    assert r.current_point in ("室戸沖", "北東", "北西", "西", "東")
    # 全 5 点とも sea_area="室戸沖" なので、結果は hierarchy 版と完全一致するはず
    clf_h = _make_clf_hier()
    r_h = clf_h.classify("室戸沖", 33.29, 134.18)
    assert r.current_point == r_h.current_point
    assert r.current_distance_km == r_h.current_distance_km


# ------------------------------------------------------------
# テストケース：canonical → sea_area lookup miss → フラット最近傍
# ------------------------------------------------------------
def test_unknown_canonical_falls_back_to_flat():
    """spot_station_map に無い canonical は lookup miss → フラット最近傍."""
    clf = _make_clf_hier()
    # "知らない場所" は spot_station_map に無い canonical
    # 現状 stations_master の current_points が全部 "室戸沖" なので、結果は 5 点のどれか
    r = clf.classify("知らない場所", 33.29, 134.18)
    # lookup miss → filtered_current = 全 current_points → 既存挙動と一致
    r_flat = _make_clf_flat().classify("知らない場所", 33.29, 134.18)
    assert r.current_point == r_flat.current_point
    assert r.current_distance_km == r_flat.current_distance_km


# ------------------------------------------------------------
# テストケース：座標なし → current_point は None（W7-2 substring fallback 経路）
# ------------------------------------------------------------
def test_no_coords_gives_no_current_point():
    """座標欠落の場合、substring fallback 経路に入り current_point は None."""
    clf = _make_clf_hier()
    r = clf.classify("室戸沖", None, None)
    assert r.current_point is None
    assert r.current_distance_km is None


# ------------------------------------------------------------
# テストケース：室戸沖 sea_area spots は hier と flat が完全一致
# （stations_master の current_points が全点 sea_area="室戸沖" のため、
#  室戸沖 spot の filter subset は full set と等価）
# ------------------------------------------------------------
def test_hier_matches_flat_for_muroto_sea_area_spots():
    """sea_area='室戸沖' の spot は W7-4 前後で current_point 結果が完全一致."""
    clf_flat = _make_clf_flat()
    clf_hier = _make_clf_hier()
    # spot_station_map で sea_area='室戸沖' のエントリ（室戸沖・甲浦）
    cases = [
        ("室戸沖", 33.29, 134.18),
        ("甲浦", 33.57, 134.33),
    ]
    for spot, lat, lng in cases:
        r_flat = clf_flat.classify(spot, lat, lng)
        r_hier = clf_hier.classify(spot, lat, lng)
        assert r_flat.current_point == r_hier.current_point, (
            f"{spot}: flat={r_flat.current_point!r} hier={r_hier.current_point!r}"
        )
        assert r_flat.current_distance_km == r_hier.current_distance_km, (
            f"{spot}: flat_dist={r_flat.current_distance_km} "
            f"hier_dist={r_hier.current_distance_km}"
        )


# ------------------------------------------------------------
# テストケース：他海域（土佐湾/豊後水道/足摺沖）spot は hier で current_point=None
# （stations_master に該当海域の current_points が 0 件のため設計通り None）
# ------------------------------------------------------------
def test_other_sea_area_spots_return_none_in_hier():
    """sea_area='土佐湾'/'豊後水道'/'足摺沖' の spot は W7-4 で current_point=None.

    これは W7-4 案I-light の設計通りの挙動（sea_area 階層フィルタが、
    該当海域の current_points が 0 件の場合に None を返す）。

    既存 spot_station_map.spots[].current_point は confidence=verified/manual で
    rebuild_spot_map.py が保護するため、この classify() 結果の変化は
    spot_station_map.json の値には反映されない（regression ゼロ）。
    """
    clf_hier = _make_clf_hier()
    # sea_area='土佐湾' の安満地
    r1 = clf_hier.classify("安満地", 33.47, 133.88)
    assert r1.current_point is None
    assert r1.current_distance_km is None
    # sea_area='豊後水道' の宇和島
    r2 = clf_hier.classify("宇和島", 33.22, 132.56)
    assert r2.current_point is None
    # sea_area='足摺沖' の柏島
    r3 = clf_hier.classify("柏島", 32.77, 132.62)
    assert r3.current_point is None
    # ただし nearest_station は気象側（フラットのまま）、従来通り決定される
    assert r1.nearest_station == "高知"
    assert r2.nearest_station == "宇和島"
    assert r3.nearest_station == "足摺"


# ------------------------------------------------------------
# テストケース：ダミー足摺沖 4 点拡張 — 足摺 spot は足摺沖 4 点に絞って割当
# ------------------------------------------------------------
def test_dummy_ashizuri_area_expansion(tmp_path):
    """sea_area='足摺沖' の仮 current_points 4 点を追加した stations_master に対し、
    足摺沖 spot が足摺沖 4 点のどれかに寄り、既存の室戸沖 5 点には寄らない."""
    with _STATIONS.open(encoding="utf-8") as f:
        real_stations = json.load(f)

    # 足摺沖 4 点ダミーを追加
    extended = {
        "weather_stations": real_stations["weather_stations"],
        "current_points": [
            *real_stations["current_points"],
            {"name": "足摺北", "lat": 32.75, "lng": 132.95, "sea_area": "足摺沖",
             "updated_on": "2026-04-21"},
            {"name": "足摺南", "lat": 32.68, "lng": 132.95, "sea_area": "足摺沖",
             "updated_on": "2026-04-21"},
            {"name": "足摺東", "lat": 32.72, "lng": 133.00, "sea_area": "足摺沖",
             "updated_on": "2026-04-21"},
            {"name": "足摺西", "lat": 32.72, "lng": 132.90, "sea_area": "足摺沖",
             "updated_on": "2026-04-21"},
        ],
        "version": "2.1.1-test",
        "updated_at": "2026-04-21T00:00:00+09:00",
    }
    stations_tmp = tmp_path / "stations_extended.json"
    stations_tmp.write_text(
        json.dumps(extended, ensure_ascii=False), encoding="utf-8"
    )

    # 足摺岬 spot を含む仮 spot_station_map（sea_area='足摺沖'）
    ssm_tmp = tmp_path / "spot_station_map_extended.json"
    ssm_doc = {
        "spots": [
            {
                "canonical_spot": "足摺岬",
                "sea_area": "足摺沖",
                "spot_lat": 32.72,
                "spot_lng": 132.95,
                "confidence": "manual",
            }
        ],
        "version": "1.0.0-test",
    }
    ssm_tmp.write_text(
        json.dumps(ssm_doc, ensure_ascii=False), encoding="utf-8"
    )

    clf = SpotClassifier(
        str(stations_tmp),
        str(_RULES),
        spot_station_map_path=str(ssm_tmp),
    )
    r = clf.classify("足摺岬", 32.72, 132.95)

    # 足摺沖 4 点のどれかに引き当たるべき
    assert r.current_point in ("足摺北", "足摺南", "足摺東", "足摺西"), (
        f"expected 足摺沖 4 点のどれかだが current_point={r.current_point!r}"
    )
    # 室戸沖 5 点には寄らない
    assert r.current_point not in ("室戸沖", "北東", "北西", "西", "東")


# ------------------------------------------------------------
# テストケース：sea_area フィルタ後に該当 current_point が 0 件 → None
# ------------------------------------------------------------
def test_empty_sea_area_subset_returns_none(tmp_path):
    """sea_area='足摺沖' lookup hit だが stations_master に該当 current_point が 0 件 → None."""
    # 室戸沖 5 点のみの stations_master（そのまま本番）
    # 足摺沖 spot の spot_station_map（sea_area='足摺沖'）
    ssm_tmp = tmp_path / "ssm.json"
    ssm_doc = {
        "spots": [
            {
                "canonical_spot": "未登録海域spot",
                "sea_area": "足摺沖",
                "spot_lat": 32.72,
                "spot_lng": 132.95,
                "confidence": "manual",
            }
        ],
        "version": "1.0.0-test",
    }
    ssm_tmp.write_text(
        json.dumps(ssm_doc, ensure_ascii=False), encoding="utf-8"
    )
    clf = SpotClassifier(
        str(_STATIONS),
        str(_RULES),
        spot_station_map_path=str(ssm_tmp),
    )
    r = clf.classify("未登録海域spot", 32.72, 132.95)
    # sea_area='足摺沖' lookup hit だが stations_master には足摺沖 current_point が無い
    # → filtered_current=[] → current_point=None
    assert r.current_point is None
    assert r.current_distance_km is None


# ------------------------------------------------------------
# pytest を使わないスモーク実行（python -m tests.test_sea_area_hierarchy）
# ------------------------------------------------------------
if __name__ == "__main__":
    import sys
    import tempfile

    tests_nofixture = [
        test_stations_master_current_points_have_sea_area,
        test_sea_area_values_within_master_mapping,
        test_muroto_spot_uses_muroto_sea_area,
        test_no_spot_map_fallback_to_flat,
        test_unknown_canonical_falls_back_to_flat,
        test_no_coords_gives_no_current_point,
        test_hier_matches_flat_for_muroto_sea_area_spots,
        test_other_sea_area_spots_return_none_in_hier,
    ]
    tests_fixture = [
        test_dummy_ashizuri_area_expansion,
        test_empty_sea_area_subset_returns_none,
    ]
    fails = 0
    for t in tests_nofixture:
        try:
            t()
            print(f"  PASS: {t.__name__}")
        except AssertionError as e:
            fails += 1
            print(f"  FAIL: {t.__name__}: {e}")
        except Exception as e:
            fails += 1
            print(f"  ERROR: {t.__name__}: {type(e).__name__}: {e}")
    for t in tests_fixture:
        try:
            with tempfile.TemporaryDirectory() as td:
                t(Path(td))
            print(f"  PASS: {t.__name__}")
        except AssertionError as e:
            fails += 1
            print(f"  FAIL: {t.__name__}: {e}")
        except Exception as e:
            fails += 1
            print(f"  ERROR: {t.__name__}: {type(e).__name__}: {e}")
    total = len(tests_nofixture) + len(tests_fixture)
    print()
    print(f"  Total: {total}  Failed: {fails}")
    sys.exit(1 if fails else 0)
