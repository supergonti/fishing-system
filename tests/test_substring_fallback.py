"""
tests/test_substring_fallback.py — W7-2 substring fallback の unit test

設計準拠:
  - 指示書_W7-2_substring_fallback_20260420.md §4-4
  - 計画書_司令塔5_釣り場分類人機協調改革_20260420.md §3-2 (sentinel 3値仕様)
  - 司令塔5_事前確認レポート_W7全指示書整合性_20260420.md §W7-2

W7-2 における classify() 拡張仕様:
  - 座標欠落＋canonical に weather_stations.name が含まれる場合、その station 名を返す
    （長い station 名を優先、distance_km は None）
  - 座標欠落＋どの station 名にもヒットしない場合、UNKNOWN_SENTINEL='不明' を返す
  - 座標ありの場合は従来通り haversine が走り substring fallback には到達しない
  - 否定リスト negatives で誤マッチを抑制可能（初期は空、ここでは在野化テスト）

実行（pytest が入っていれば）:
  python -m pytest tests/test_substring_fallback.py -v

pytest を使わずにスモークテストしたい場合:
  python -m tests.test_substring_fallback
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
def test_substring_matches_muroto():
    """辞書に無い合成語、座標なし、『室戸』含有 → station '室戸' に寄る."""
    clf = _make_clf()
    r = clf.classify("室戸岬湾内の磯場", None, None)
    assert r.nearest_station == "室戸"
    # substring match では距離計算していない
    assert r.distance_km is None
    assert r.current_point is None
    assert r.current_distance_km is None


def test_substring_matches_matsuyama():
    """『松山市沖』→ '松山' に寄る（県名除去の影響を受けない地名）.

    注：指示書 §4-4 の例『高知市沖合』は県名 prefix '高知' が
    Step3 で剥離されるため canonical='市沖合' となり station を含まない。
    「県名除去されない県庁所在地名のみを含む合成語」でテストする。
    """
    clf = _make_clf()
    r = clf.classify("松山市沖", None, None)
    assert r.nearest_station == "松山"
    assert r.distance_km is None


def test_substring_matches_ashizuri():
    """『足摺岬近く』→ '足摺' に寄る."""
    clf = _make_clf()
    r = clf.classify("足摺岬近く", None, None)
    assert r.nearest_station == "足摺"
    assert r.distance_km is None


def test_substring_matches_anan():
    """『阿南沖磯』→ '阿南' に寄る."""
    clf = _make_clf()
    r = clf.classify("阿南沖磯", None, None)
    assert r.nearest_station == "阿南"


def test_substring_no_match_stays_unknown():
    """どの station 名も含まない合成語 → UNKNOWN_SENTINEL='不明'."""
    clf = _make_clf()
    r = clf.classify("どこでもない場所", None, None)
    assert r.nearest_station == UNKNOWN_SENTINEL
    assert r.distance_km is None


def test_substring_longest_wins():
    """『宇和島周辺』→ '宇和島'（3文字）が選ばれる（長さ降順優先）."""
    clf = _make_clf()
    r = clf.classify("宇和島周辺", None, None)
    assert r.nearest_station == "宇和島"


def test_coords_take_precedence_over_substring():
    """座標があれば haversine が優先、substring fallback は走らない."""
    clf = _make_clf()
    # raw_spot は station 名と無関係、座標は室戸（33.29, 134.18）
    r = clf.classify("不明な釣り場", 33.29, 134.18)
    assert r.nearest_station == "室戸"
    # 座標あり経路では distance_km が数値で入る（haversine 結果）
    assert r.distance_km is not None
    assert r.distance_km == 0.0  # 完全一致


def test_substring_does_not_break_empty_input():
    """空入力は早期 return：substring fallback も走らず None のまま."""
    clf = _make_clf()
    r = clf.classify("", None, None)
    assert r.nearest_station is None
    assert r.canonical_spot == ""


def test_substring_does_not_break_none_input():
    """None 入力も同様：substring fallback の影響を受けない."""
    clf = _make_clf()
    r = clf.classify(None, None, None)
    assert r.nearest_station is None
    assert r.canonical_spot == ""


def test_substring_existing_alias_still_wins():
    """既存 alias 辞書（『室戸沖磯』→『室戸沖』）は substring より先に発火する.

    『室戸沖磯』は alias で『室戸沖』に正規化される。
    座標なしで classify すると、canonical='室戸沖' に substring '室戸' が含まれるので
    結果として nearest_station='室戸' になるが、これは alias 経由の正規化を経た結果。
    """
    clf = _make_clf()
    r = clf.classify("室戸沖磯", None, None)
    assert r.canonical_spot == "室戸沖"  # alias 適用後
    assert r.nearest_station == "室戸"  # substring match


def test_substring_hiragana_does_not_match():
    """カタカナ・ひらがな表記の地名は substring に含まれない（NFKC 後も別文字列）.

    『ムロト』『コーチ』は station 名の漢字とは別文字列なので不明のまま。
    """
    clf = _make_clf()
    r = clf.classify("ムロト", None, None)
    assert r.nearest_station == UNKNOWN_SENTINEL
    r2 = clf.classify("コーチ", None, None)
    assert r2.nearest_station == UNKNOWN_SENTINEL


def test_substring_match_method_directly():
    """_substring_match() を単体で呼んでも一貫した結果を返す."""
    clf = _make_clf()
    # '室戸' を含む合成語 → '室戸' を返す
    assert clf._substring_match("室戸岬湾内磯場") == "室戸"
    # 県名除去後の '高知沖' は '高知' を含む → '高知' を返す
    assert clf._substring_match("高知沖") == "高知"
    # 含まれる station 名が無い → None
    assert clf._substring_match("どこでもない") is None
    # 空文字列 → None（どの station 名も含まない）
    assert clf._substring_match("") is None


def test_substring_negatives_block():
    """negatives に『大室戸』を入れると、それを含む canonical の '室戸' マッチがブロックされる."""
    clf = _make_clf()
    # 動的に negatives を差し込んで挙動確認（json は触らない）
    clf._negatives = [{"contains": "大室戸", "reason": "test"}]
    # canonical='大室戸の磯' は '室戸' を含むが、'大室戸' があるので '室戸' マッチはブロック
    assert clf._substring_match("大室戸の磯") is None


def test_known_spot_with_coords_unaffected():
    """W7-1 既存挙動：座標あり＋既知 spot → station 名（W7-2 で変化しない）."""
    clf = _make_clf()
    r = clf.classify("室戸沖", 33.29, 134.18)
    assert r.nearest_station == "室戸"
    assert r.distance_km is not None


def test_ogasawara_coords_stays_other():
    """W7-1 既存挙動：閾値 300km 超過 → 'その他'（W7-2 で変化しない）."""
    clf = _make_clf()
    r = clf.classify("小笠原", 27.09, 142.19)
    assert r.nearest_station == OTHER_SENTINEL


# ------------------------------------------------------------
# pytest を使わないスモーク実行（python -m tests.test_substring_fallback）
# ------------------------------------------------------------
if __name__ == "__main__":
    import sys

    tests = [
        test_substring_matches_muroto,
        test_substring_matches_matsuyama,
        test_substring_matches_ashizuri,
        test_substring_matches_anan,
        test_substring_no_match_stays_unknown,
        test_substring_longest_wins,
        test_coords_take_precedence_over_substring,
        test_substring_does_not_break_empty_input,
        test_substring_does_not_break_none_input,
        test_substring_existing_alias_still_wins,
        test_substring_hiragana_does_not_match,
        test_substring_match_method_directly,
        test_substring_negatives_block,
        test_known_spot_with_coords_unaffected,
        test_ogasawara_coords_stays_other,
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
    print()
    print(f"  Total: {len(tests)}  Failed: {fails}")
    sys.exit(1 if fails else 0)
