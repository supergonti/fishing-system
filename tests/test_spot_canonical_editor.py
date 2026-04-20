"""
tests/test_spot_canonical_editor.py — W7-3 spot_canonical_editor の unit test

設計準拠:
  - 指示書_W7-3_collector_html_レビューUI_20260420.md §4-4
  - W7-3_設計案決裁_司令塔5_20260420.md Q2（editor 作成、ただし本 W7-3 では
    主フローからは呼ばれない。unit test で継続的に検証する）
  - 計画書_司令塔5_釣り場分類人機協調改革_20260420.md §3-3 §3-4

検証対象:
  - add_alias(): 冪等 append、衝突検出、自己マッピング skip、version bump
  - batch_add_aliases(): 複数ペアの順次追記、衝突時の送出

実行（pytest が入っていれば）:
  python -m pytest tests/test_spot_canonical_editor.py -v

pytest を使わずにスモークテストしたい場合:
  python -m tests.test_spot_canonical_editor
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engines.spot_canonical_editor import (
    ConflictError,
    add_alias,
    batch_add_aliases,
)


# ------------------------------------------------------------
# 共通 fixture：各テストに temp な rules.json を用意
# ------------------------------------------------------------
_INITIAL_DOC = {
    "notes": "test",
    "rules": [
        {
            "from": "室戸沖磯",
            "to": "室戸沖",
            "type": "alias",
            "reason": "初期",
        }
    ],
    "stopwords": {
        "brackets": ["(", ")", "（", "）"],
        "prefixes": ["高知県", "高知"],
        "whitespace": [" ", "　", "\t"],
    },
    "version": "1.0.0",
    "updated_at": "2026-04-20T00:00:00+09:00",
}


@pytest.fixture
def tmp_rules(tmp_path: Path) -> str:
    """各テストに clean な rules.json を用意（BOM なし + LF）."""
    p = tmp_path / "rules.json"
    with p.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(_INITIAL_DOC, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return str(p)


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------
# テストケース
# ------------------------------------------------------------
def test_add_new_alias(tmp_rules: str) -> None:
    """新規 alias が rules 配列に追加される."""
    r = add_alias(tmp_rules, "コーチ", "高知")
    assert r["status"] == "added"
    assert r["from"] == "コーチ"
    assert r["to"] == "高知"

    doc = _load(tmp_rules)
    matches = [
        rule for rule in doc["rules"] if rule["from"] == "コーチ" and rule["to"] == "高知"
    ]
    assert len(matches) == 1
    rule = matches[0]
    assert rule["type"] == "alias"
    assert rule["reason"]  # 何らか
    assert rule["added_at"]  # ISO8601 文字列が入る
    assert rule["added_by"] == "user_review"


def test_idempotent_skip_for_duplicate(tmp_rules: str) -> None:
    """同じ (from, to) を2回追加しても重複しない（冪等）."""
    add_alias(tmp_rules, "コーチ", "高知")
    r2 = add_alias(tmp_rules, "コーチ", "高知")
    assert r2["status"] == "skipped"
    assert r2["reason"] == "already_exists"

    doc = _load(tmp_rules)
    cnt = sum(1 for rule in doc["rules"] if rule["from"] == "コーチ")
    assert cnt == 1, "重複 rule が増えてはならない"


def test_conflict_raises(tmp_rules: str) -> None:
    """同じ from に異なる to を追加すると ConflictError."""
    add_alias(tmp_rules, "コーチ", "高知")
    with pytest.raises(ConflictError):
        add_alias(tmp_rules, "コーチ", "室戸")

    # 衝突検出されたら元の rule は変わっていない
    doc = _load(tmp_rules)
    matches = [rule for rule in doc["rules"] if rule["from"] == "コーチ"]
    assert len(matches) == 1
    assert matches[0]["to"] == "高知"


def test_self_mapping_skipped(tmp_rules: str) -> None:
    """from == to の自己マッピングは skip（ファイル書き換え無し）."""
    before = _load(tmp_rules)
    r = add_alias(tmp_rules, "室戸沖", "室戸沖")
    assert r["status"] == "skipped"
    assert r["reason"] == "self-mapping"

    after = _load(tmp_rules)
    assert before == after, "自己マッピング時にファイルが書き換わってはならない"


def test_version_bumps_on_new_add(tmp_rules: str) -> None:
    """新規 append 時に version の patch が 1 bump する."""
    before_doc = _load(tmp_rules)
    before_ver = before_doc["version"]
    add_alias(tmp_rules, "コーチ", "高知")
    after_doc = _load(tmp_rules)
    after_ver = after_doc["version"]

    assert before_ver != after_ver
    # 1.0.0 -> 1.0.1
    before_parts = before_ver.split(".")
    after_parts = after_ver.split(".")
    assert before_parts[0] == after_parts[0]
    assert before_parts[1] == after_parts[1]
    assert int(after_parts[2]) == int(before_parts[2]) + 1


def test_version_unchanged_on_skip(tmp_rules: str) -> None:
    """skip（重複・自己マッピング）時は version を変えない."""
    add_alias(tmp_rules, "コーチ", "高知")  # ここで 1.0.1 に bump
    mid_ver = _load(tmp_rules)["version"]

    add_alias(tmp_rules, "コーチ", "高知")  # already_exists
    after1 = _load(tmp_rules)["version"]
    assert after1 == mid_ver

    add_alias(tmp_rules, "室戸沖", "室戸沖")  # self-mapping
    after2 = _load(tmp_rules)["version"]
    assert after2 == mid_ver


def test_updated_at_refreshed_on_add(tmp_rules: str) -> None:
    """新規 append 時に updated_at が更新される."""
    before = _load(tmp_rules)["updated_at"]
    add_alias(tmp_rules, "コーチ", "高知")
    after = _load(tmp_rules)["updated_at"]
    assert before != after


def test_existing_rules_preserved(tmp_rules: str) -> None:
    """既存 rule の順序・内容は保持される（append-only）."""
    before = _load(tmp_rules)
    before_first = before["rules"][0]  # 室戸沖磯 → 室戸沖

    add_alias(tmp_rules, "コーチ", "高知")

    after = _load(tmp_rules)
    after_first = after["rules"][0]
    assert after_first == before_first, "先頭 rule が保護されない"
    # 新規は末尾に追加
    assert after["rules"][-1]["from"] == "コーチ"


def test_added_by_custom(tmp_rules: str) -> None:
    """added_by を指定すると反映される."""
    add_alias(tmp_rules, "コーチ", "高知", added_by="batch_import_2026_04")
    doc = _load(tmp_rules)
    last = doc["rules"][-1]
    assert last["added_by"] == "batch_import_2026_04"


def test_reason_custom(tmp_rules: str) -> None:
    """reason を指定すると反映される."""
    add_alias(
        tmp_rules,
        "コーチ",
        "高知",
        reason="user_review (record_id=abc-123)",
    )
    doc = _load(tmp_rules)
    last = doc["rules"][-1]
    assert "record_id=abc-123" in last["reason"]


def test_batch_add_aliases_success(tmp_rules: str) -> None:
    """batch 追記が全件成功する（衝突なし）."""
    pairs = [("コーチ", "高知"), ("松山港", "松山"), ("沖ノ島周辺", "足摺")]
    results = batch_add_aliases(tmp_rules, pairs)
    assert len(results) == 3
    assert all(r["status"] == "added" for r in results)

    doc = _load(tmp_rules)
    added_froms = {r["from"] for r in doc["rules"] if r["from"] in {"コーチ", "松山港", "沖ノ島周辺"}}
    assert added_froms == {"コーチ", "松山港", "沖ノ島周辺"}


def test_batch_add_aliases_stops_on_conflict(tmp_rules: str) -> None:
    """batch 途中で衝突が出たら raise、それまでの分は書き込まれる."""
    add_alias(tmp_rules, "コーチ", "高知")
    # 2件目で衝突
    pairs = [("松山港", "松山"), ("コーチ", "室戸"), ("沖ノ島周辺", "足摺")]
    with pytest.raises(ConflictError):
        batch_add_aliases(tmp_rules, pairs)

    doc = _load(tmp_rules)
    froms = {r["from"] for r in doc["rules"]}
    assert "松山港" in froms, "衝突前の件は書き込まれていること"
    assert "沖ノ島周辺" not in froms, "衝突後の件は書き込まれないこと"


def test_file_format_bom_free_lf(tmp_rules: str) -> None:
    """保存後のファイルが BOM なし + LF 改行 + 末尾改行である."""
    add_alias(tmp_rules, "コーチ", "高知")

    raw = Path(tmp_rules).read_bytes()
    # BOM 無し
    assert not raw.startswith(b"\xef\xbb\xbf"), "BOM が付与されてはならない"
    # CRLF 無し
    assert b"\r\n" not in raw, "CRLF 改行が混入してはならない"
    # 末尾改行
    assert raw.endswith(b"\n"), "末尾改行が必要"


# ------------------------------------------------------------
# pytest を使わずにスモークテストしたい場合の entry
# ------------------------------------------------------------
if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
