"""
tests/test_unknown_sentinel.py — W7-1 不明 sentinel 導入の unit test

設計準拠:
  - 指示書_W7-1_不明sentinel導入_20260420.md §4-5
  - 指示書_W7-1_補足_司令塔5_20260420.md
  - 計画書_司令塔5_釣り場分類人機協調改革_20260420.md §3-2 (sentinel 3値仕様)

W7-1 における nearest_station の 3 値仕様:
  1. None          … raw が空文字列 / None（空は空として扱う）
  2. "不明"        … raw あり＋座標欠落（W7-1 新規、人レビュー必要）
  3. "その他"      … raw あり＋座標あり＋閾値超過（分類として正解）
  4. station 名    … raw あり＋座標あり＋閾値以内

実行（pytest が入っていれば）:
  python -m pytest tests/test_unknown_sentinel.py -v

pytest を使わずにスモークテストしたい場合:
  python -m tests.test_unknown_sentinel
"""

from __future__ import annotations

from pathlib import Path

from engines.spot_classifier import (
    OTHER_SENTINEL,
    UNKNOWN_SENTINEL,
    SpotClassifier,
)


# ------------------------------------------------------------
# 共通ヘルパ：テスト用 classifier
# ------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_STATIONS = _REPO_ROOT / "data" / "b_mapping" / "stations_master.json"
_RULES = _REPO_ROOT / "data" / "b_mapping" / "spot_canonical_rules.json"


def _make_clf() -> SpotClassifier:
    return SpotClassifier(str(_STATIONS), str(_RULES))


# ------------------------------------------------------------
# テストケース（pytest が関数名で自動収集）
# ------------------------------------------------------------
def test_known_spot_with_coords():
    """raw あり＋座標あり＋閾値以内 → 対応 station 名（既存挙動維持）."""
    clf = _make_clf()
    r = clf.classify("室戸沖", 33.29, 134.18)
    assert r.nearest_station == "室戸"


def test_known_spot_without_coords_returns_unknown():
    """raw あり＋座標欠落 → UNKNOWN_SENTINEL='不明'（W7-1 新規挙動）."""
    clf = _make_clf()
    r = clf.classify("コーチ", None, None)
    assert r.nearest_station == UNKNOWN_SENTINEL
    assert r.canonical_spot != ""  # canonical は取れている
    assert r.distance_km is None
    assert r.current_point is None


def test_ogasawara_stays_other():
    """閾値（300km）超過 → OTHER_SENTINEL='その他'（既存挙動維持）."""
    clf = _make_clf()
    # 小笠原の大まかな座標。最寄りの室戸（33.29, 134.18）から 1000km 超
    r = clf.classify("小笠原", 27.09, 142.19)
    assert r.nearest_station == OTHER_SENTINEL


def test_empty_spot_returns_none():
    """raw が空 → None（空は空のまま、UNKNOWN にはしない）."""
    clf = _make_clf()
    r = clf.classify("", None, None)
    assert r.nearest_station is None
    assert r.canonical_spot == ""


def test_none_spot_returns_none():
    """raw が None → None（空は空のまま、UNKNOWN にはしない）."""
    clf = _make_clf()
    r = clf.classify(None, None, None)
    assert r.nearest_station is None
    assert r.canonical_spot == ""


def test_unknown_sentinel_constant_defined():
    """UNKNOWN_SENTINEL 定数が "不明" として定義されている."""
    assert UNKNOWN_SENTINEL == "不明"
    # OTHER と別値であること
    assert UNKNOWN_SENTINEL != OTHER_SENTINEL


# ------------------------------------------------------------
# pytest を使わないスモーク実行（python -m tests.test_unknown_sentinel）
# ------------------------------------------------------------
if __name__ == "__main__":
    import sys

    tests = [
        test_known_spot_with_coords,
        test_known_spot_without_coords_returns_unknown,
        test_ogasawara_stays_other,
        test_empty_spot_returns_none,
        test_none_spot_returns_none,
        test_unknown_sentinel_constant_defined,
    ]
    fails = 0
    for t in tests:
        try:
            t()
            print(f"  PASS: {t.__name__}")
        except AssertionError as e:
            fails += 1
            print(f"  FAIL: {t.__name__}: {e}")
        except Exception as e:
            fails += 1
            print(f"  ERROR: {t.__name__}: {type(e).__name__}: {e}")

    print(f"\n{len(tests) - fails}/{len(tests)} passed")
    sys.exit(0 if fails == 0 else 1)
