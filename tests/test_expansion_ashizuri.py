"""
tests/test_expansion_ashizuri.py — W7-5 拡張プルーフテスト（足摺沖ダミー4点追加）

目的:
  W7-4 で導入した sea_area 階層が、実際の海域拡張フェーズで正しく機能することを
  足摺沖 4 点のダミー追加シナリオで実証する。

設計準拠:
  - 指示書_W7-5_拡張プルーフテスト_20260420.md §4-2
  - 司令塔5 事前確認レポート §W7-5（fixture csv は utf-8-sig + CRLF + 末尾改行）
  - 計画書_司令塔5_釣り場分類人機協調改革_20260420.md §3-5 sea_area 階層

触らないファイル（3 不変条件＋W7-5 契約）:
  - data/b_mapping/stations_master.json（本物）
  - data/b_mapping/spot_station_map.json（本物）
  - data/master_catch.csv（本物、read-only 参照のみ）
  - production コード（engines/, scripts/, *.html）

実行:
  python -m pytest tests/test_expansion_ashizuri.py -v
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from engines.spot_classifier import (
    OTHER_SENTINEL,
    UNKNOWN_SENTINEL,
    SpotClassifier,
)

# ============================================================
# パス解決（pytest の cwd 非依存）
# ============================================================
_REPO_ROOT = Path(__file__).resolve().parent.parent
_FIX = _REPO_ROOT / "tests" / "fixtures"

# W7-5 fixture（本 PR で新規配置）
STATIONS_FIX = _FIX / "stations_master_with_ashizuri.json"
SSM_FIX = _FIX / "spot_station_map_with_ashizuri.json"
MASTER_SAMPLE = _FIX / "master_catch_ashizuri_sample.csv"

# 本物（read-only 参照）
RULES_REAL = _REPO_ROOT / "data" / "b_mapping" / "spot_canonical_rules.json"
STATIONS_REAL = _REPO_ROOT / "data" / "b_mapping" / "stations_master.json"
SSM_REAL = _REPO_ROOT / "data" / "b_mapping" / "spot_station_map.json"
MASTER_CATCH_REAL = _REPO_ROOT / "data" / "master_catch.csv"

# 海流地点の集合（期待値）
MUROTO_CP = {"北西", "西", "室戸沖", "東", "北東"}
ASHIZURI_CP = {"足摺北", "足摺南", "足摺東", "足摺西"}


# ============================================================
# fixture（pytest）
# ============================================================
@pytest.fixture(scope="module")
def clf_with_ashizuri() -> SpotClassifier:
    """W7-5 fixture: 足摺沖 4 点を追加した stations_master + 足摺岬 canonical を含む spot_station_map。"""
    return SpotClassifier(
        str(STATIONS_FIX),
        str(RULES_REAL),  # 別名辞書は本物流用（「高知」prefix 除去など標準挙動）
        spot_station_map_path=str(SSM_FIX),
    )


@pytest.fixture(scope="module")
def clf_real_hier() -> SpotClassifier:
    """本物 3 ファイルで構築した classifier（既存 regression の基準）"""
    return SpotClassifier(
        str(STATIONS_REAL),
        str(RULES_REAL),
        spot_station_map_path=str(SSM_REAL),
    )


# ============================================================
# 1) 足摺 spot は足摺 4 点に寄る（lookup hit 経路）
# ============================================================
def test_ashizuri_spot_routes_to_ashizuri_current_points(clf_with_ashizuri):
    """
    足摺岬 は canonical→sea_area lookup で '足摺沖' が hit し、
    filtered=4 足摺点のみから nearest を選ぶ。室戸 5 点には寄らない。
    """
    r = clf_with_ashizuri.classify("足摺岬", 32.72, 132.95)
    assert r.canonical_spot == "足摺岬"
    assert r.nearest_station == "足摺"
    assert r.current_point in ASHIZURI_CP, (
        f"expected one of {ASHIZURI_CP}, got {r.current_point}"
    )
    assert r.current_point not in MUROTO_CP
    # 足摺 spot 座標はどの足摺点とも < 50 km（閾値内）
    assert r.current_distance_km is not None and r.current_distance_km < 50.0


# ============================================================
# 2) 室戸 spot は室戸 5 点で完結、足摺に引き寄せられない
# ============================================================
def test_muroto_spot_stays_in_muroto_current_points(clf_with_ashizuri):
    """
    室戸沖 は sea_area='室戸沖' lookup hit で filtered=5 室戸点のみ、
    足摺 4 点には寄らない。
    """
    r = clf_with_ashizuri.classify("室戸沖", 33.29, 134.18)
    assert r.canonical_spot == "室戸沖"
    assert r.nearest_station == "室戸"
    assert r.current_point in MUROTO_CP, (
        f"expected one of {MUROTO_CP}, got {r.current_point}"
    )
    assert r.current_point not in ASHIZURI_CP
    assert r.current_distance_km is not None and r.current_distance_km < 50.0


# ============================================================
# 3) 足摺系 raw 揺れ（alias 未登録 / prefix 除去込み）でも足摺に収束
# ============================================================
def test_ashizuri_raw_variants_all_route_correctly(clf_with_ashizuri):
    """
    - '足摺岬沖'：canonical='足摺岬沖'（alias 未登録、lookup miss）
                   → flat fallback だが足摺 4 点が室戸 5 点より圧倒的近い（~3-5km vs ~128-143km）
                   → 足摺点に寄る
    - '高知足摺岬'：県名 prefix 除去後 canonical='足摺岬'（lookup hit）
                   → 足摺 4 点に寄る
    """
    variants = ["足摺岬沖", "高知足摺岬"]
    for raw in variants:
        r = clf_with_ashizuri.classify(raw, 32.72, 132.95)
        assert r.nearest_station == "足摺", f"{raw} → ns={r.nearest_station}"
        assert r.current_point in ASHIZURI_CP, (
            f"{raw} → cp={r.current_point} (expected in {ASHIZURI_CP})"
        )
        assert r.current_point not in MUROTO_CP


# ============================================================
# 4) 既存 857+ 件の nearest_station 不変（全件 regression）
# ============================================================
def test_existing_rows_nearest_station_regression(clf_real_hier):
    """
    本物の data/master_catch.csv の座標あり行を全て classify() に通し、
    csv に記録済みの nearest_station と完全一致することを確認。

    対象外:
      - 座標欠落行（spot_lat / spot_lng のどちらかが空 / 非数）
      - csv の nearest_station が空文字列（既存 collector 安定版経由の入力）
      - csv の nearest_station が '不明'（W7-1 以降の sentinel、W7-5 着手時点では存在しない想定）

    W7-4 完了時点：座標あり 857 行 / regression mismatch 0（W7-4 完了報告 §2）
    W7-5 着手時点：865 行（2026-04-21 時点）
    """
    if not MASTER_CATCH_REAL.exists():
        pytest.skip("master_catch.csv not present")
    with MASTER_CATCH_REAL.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    checked = 0
    mismatches: list[str] = []
    for r in rows:
        slat = (r.get("spot_lat") or "").strip()
        slng = (r.get("spot_lng") or "").strip()
        csv_ns = (r.get("nearest_station") or "").strip()
        if not slat or not slng:
            continue
        # 座標が非数値（防御的）
        try:
            lat = float(slat)
            lng = float(slng)
        except ValueError:
            continue
        # 旧データで nearest_station 空 or 不明なら比較しない
        if csv_ns == "" or csv_ns == UNKNOWN_SENTINEL:
            continue
        result = clf_real_hier.classify(r.get("spot", ""), lat, lng)
        if result.nearest_station != csv_ns:
            mismatches.append(
                f"record_id={r.get('record_id')} spot={r.get('spot')!r} "
                f"csv_ns={csv_ns!r} got={result.nearest_station!r}"
            )
        checked += 1

    assert checked > 0, "no sampled row checked (csv may be empty)"
    assert mismatches == [], (
        f"regression: {len(mismatches)} row(s) mismatch among {checked} checked:\n"
        + "\n".join(mismatches[:10])
    )


# ============================================================
# 5) fixture 健全性：encoding / 改行 / 列数
# ============================================================
def test_fixture_csv_is_utf8_bom_crlf():
    """master_catch_ashizuri_sample.csv が utf-8-sig + CRLF + 末尾改行 + 26 列。"""
    raw = MASTER_SAMPLE.read_bytes()
    assert raw[:3] == b"\xef\xbb\xbf", "BOM missing"
    assert raw.endswith(b"\r\n"), "trailing CRLF missing"
    # CRLF を含むが、ヘッダ+5 行で計 6 個の CRLF があるはず
    assert raw.count(b"\r\n") == 6, f"unexpected CRLF count: {raw.count(b'\r\n')}"

    with MASTER_SAMPLE.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert len(header) == 26
        data_rows = list(reader)
        assert len(data_rows) == 5
        for row in data_rows:
            assert len(row) == 26


# ============================================================
# 6) 本物のファイルが W7-5 作業中に一切変更されないことを assert（設計契約）
#     ※ このテストは「fixture mock 設計崩壊（緊急停止条件#8）」への保険
# ============================================================
def test_real_stations_master_is_unchanged_by_w7_5():
    """
    このテスト単体で『本物 stations_master.json に足摺4点を追加していない』ことを確認する。
    current_points の数 = 5、sea_area はすべて '室戸沖'。
    本物に足摺4点が混入すれば current_points.count > 5 になって FAIL する。
    """
    import json
    with STATIONS_REAL.open(encoding="utf-8") as f:
        real = json.load(f)
    cps = real.get("current_points", [])
    assert len(cps) == 5, (
        f"本物 stations_master.json の current_points が {len(cps)} 件："
        "W7-5 は fixture のみで検証する契約。本物への足摺4点追加は別タスク（運用開始時）"
    )
    assert {p.get("sea_area") for p in cps} == {"室戸沖"}, (
        "本物 current_points の sea_area は全て '室戸沖' のはず"
    )
