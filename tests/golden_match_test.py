"""
tests/golden_match_test.py — ゴールデン比較テスト

設計準拠: 設計_W3-3_出力変換仕様_20260418.md §6.2.1

仕様:
  - ゴールデンのバイト数分を新アーキ出力と先頭バイト比較
  - 既存行は1バイト不変、末尾追加のみ許容（ゴールデンの行数以降は自由）

W4-1 の暫定運用（指示書 §6.9）:
  ゴールデン（tests/golden/*.csv）が未整備のため、既存 V6.0 リポ直下の
  `fishing_data.csv` / `fishing_integrated.csv` を暫定ゴールデン扱い。
  `fishing_muroto_v1.csv` は室戸沖釣果リポに実在する `fishing_muroto_v1.csv`
  を暫定ゴールデンとする。正式採取は W5-1。

実行:
  python3 -m tests.golden_match_test
  or
  python3 -m unittest tests.golden_match_test
"""

import os
import sys
import tempfile
import unittest

# --- パッケージ import 準備 -------------------------------------------------
# tests/ から上位の engines/ を読み込めるように cwd を追加
_THIS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_THIS)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from engines import (  # noqa: E402
    emit_fishing_data, emit_fishing_muroto_v1, emit_fishing_integrated,
)


# --- デフォルトパス（統合リポ基準） -----------------------------------------
# 全マスターデータは data/ 配下に集約されている（W5-2 統合リポ構築）。
# W5-3 改善: PROJECT_ROOT 相対 + 環境変数で上書き可能（W5-1 申し送り解消）
#   FISHING_MASTER_PATH / FISHING_C3_PATH / FISHING_C4_PATH
DEFAULT_MASTER = os.environ.get(
    "FISHING_MASTER_PATH",
    os.path.join(_ROOT, "data", "master_catch.csv"),
)
DEFAULT_C3 = os.environ.get(
    "FISHING_C3_PATH",
    os.path.join(_ROOT, "data", "fishing_condition_db.csv"),
)
DEFAULT_C4 = os.environ.get(
    "FISHING_C4_PATH",
    os.path.join(_ROOT, "data", "muroto_offshore_current_all.csv"),
)

# ゴールデン（W5-1 採取済、tests/golden/ 配下）
GOLDEN_DIR = os.path.join(_ROOT, "tests", "golden")
GOLDEN_DATA = os.path.join(GOLDEN_DIR, "fishing_data.csv")
GOLDEN_INTEGRATED = os.path.join(GOLDEN_DIR, "fishing_integrated.csv")
GOLDEN_MUROTO_V1 = os.path.join(GOLDEN_DIR, "fishing_muroto_v1.csv")


def _assert_prefix_match(golden_path: str, out_path: str) -> None:
    """ゴールデンのバイト数分、新出力と先頭バイト一致を検証。"""
    with open(golden_path, "rb") as f:
        gb = f.read()
    with open(out_path, "rb") as f:
        nb = f.read()
    if nb[:len(gb)] != gb:
        # 差分位置を特定して失敗詳細を出力
        ml = min(len(gb), len(nb))
        for i in range(ml):
            if gb[i] != nb[i]:
                raise AssertionError(
                    f"golden mismatch at byte {i} in {out_path}\n"
                    f"  golden bytes: {gb[max(0,i-20):i+40]!r}\n"
                    f"  new    bytes: {nb[max(0,i-20):i+40]!r}"
                )
        raise AssertionError(
            f"length mismatch (golden={len(gb)}, new={len(nb)})"
        )


class GoldenMatchTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="golden_emit_")

    def test_fishing_data_csv_byte_equal(self):
        """emit_fishing_data.emit 結果が既存 fishing_data.csv と完全バイト一致"""
        out = os.path.join(self.tmpdir, "fishing_data.csv")
        emit_fishing_data.emit(DEFAULT_MASTER, out, sort_by_design=False)
        _assert_prefix_match(GOLDEN_DATA, out)
        # さらに完全一致まで確認
        with open(GOLDEN_DATA, "rb") as f:
            gb = f.read()
        with open(out, "rb") as f:
            nb = f.read()
        self.assertEqual(gb, nb, "byte-for-byte equal required")

    def test_fishing_integrated_csv_byte_equal(self):
        """emit_fishing_integrated.emit 結果が既存 fishing_integrated.csv と完全バイト一致"""
        out = os.path.join(self.tmpdir, "fishing_integrated.csv")
        emit_fishing_integrated.emit(DEFAULT_MASTER, DEFAULT_C3, out)
        with open(GOLDEN_INTEGRATED, "rb") as f:
            gb = f.read()
        with open(out, "rb") as f:
            nb = f.read()
        self.assertEqual(gb, nb, "byte-for-byte equal required")

    def test_fishing_muroto_v1_schema(self):
        """
        emit_fishing_muroto_v1.emit の出力が 42列・858行で、結合ロジックが
        既存 muroto_v1 と整合（既存ファイルは C③ 更新前のスナップショットで
        完全一致しないが、列数・行数・spot 部分一致 フィルタの挙動は一致）
        """
        out = os.path.join(self.tmpdir, "fishing_muroto_v1.csv")
        n = emit_fishing_muroto_v1.emit(DEFAULT_MASTER, DEFAULT_C3, DEFAULT_C4, out)
        self.assertEqual(n, 858)

        # Count column per row
        import csv as _csv
        with open(out, "r", encoding="utf-8-sig", newline="") as f:
            reader = _csv.reader(f)
            hdr = next(reader)
            rows = list(reader)
        self.assertEqual(len(hdr), 42)
        for i, r in enumerate(rows):
            self.assertEqual(len(r), 42, f"row {i} has {len(r)} cols, want 42")

        # 非 "室戸" 行は海流8列が空
        for i, r in enumerate(rows):
            if "室戸" not in r[8]:  # spot
                self.assertEqual(r[22:30], [""] * 8,
                                 f"row {i} spot='{r[8]}' must have empty currents")

    def test_fishing_muroto_v1_prefix_match_known_rows(self):
        """
        暫定ゴールデン（室戸沖釣果リポ内）との比較。
        C③更新タイミングの違いで 3行（2026-04-12）に気象15列の差異があるが、
        他の855行は既存ファイルと完全一致する。
        """
        out = os.path.join(self.tmpdir, "fishing_muroto_v1.csv")
        emit_fishing_muroto_v1.emit(DEFAULT_MASTER, DEFAULT_C3, DEFAULT_C4, out)

        import csv as _csv
        with open(GOLDEN_MUROTO_V1, "r", encoding="utf-8-sig", newline="") as f:
            g_rows = list(_csv.reader(f))[1:]
        with open(out, "r", encoding="utf-8-sig", newline="") as f:
            n_rows = list(_csv.reader(f))[1:]

        self.assertEqual(len(g_rows), len(n_rows))
        diff_rows = [i for i in range(len(g_rows)) if g_rows[i] != n_rows[i]]
        # 既知: 2026-04-12 データの C③ 差分で最大3行まで差がある
        for i in diff_rows:
            self.assertEqual(g_rows[i][0], "2026-04-12",
                             f"unexpected diff row {i}: date={g_rows[i][0]}")
            # 海流8列は一致しているはず
            self.assertEqual(g_rows[i][22:30], n_rows[i][22:30],
                             f"current 8-col must match at row {i}")
        # 差分は 3 行以下
        self.assertLessEqual(len(diff_rows), 3, f"too many diffs: {len(diff_rows)}")


if __name__ == "__main__":
    unittest.main()
