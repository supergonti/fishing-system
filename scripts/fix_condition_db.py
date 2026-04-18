"""
scripts/fix_condition_db.py — fishing_condition_db.csv 12,497行目の41列化を修復

設計準拠:
  指示書_W5-1_既存データ移行_20260418.md §5 Step 1
  設計_W2-3_Cグループ_20260417.md §7.1
  W1-3 現状調査で判明した破損パターン

破損パターン:
  正常: '...下弦\\r\\n2026-04-12,室戸,室戸,...' （118箇所）
  破損: '...下弦2026-04-12,室戸,室戸,...'         （1箇所 = 12,497行目）
  → moon_phase列の末尾値と次行の date 先頭が \\r\\n 欠落で連結されている

処理方針（2段階）:
  Step A: 41列化の検出 → \\r\\n 挿入で21列×2行に分割
    1. 既存ファイルを {path}.bak.20260418 としてバックアップ
    2. バイナリで読み込み、月齢名直後の日付パターンを \\r\\n 挿入で復元
    3. 全行が21列であることを検証
  Step B: (日付, 地点名) 重複の解消
    4. CSV を論理行で再読み込み
    5. (日付, 地点名) の重複がある場合、keep-last ポリシー（最後に出現した行を残す）
       ※ 本仕様の根拠: 41列連結バグで復元された行は「前日夜に取得した予報値」、
          既存の後続行は「当日再取得された実測値」であり、後者を信頼する運用判断
          （W5-1 ユーザー判断、2026-04-18）
    6. 全重複が解消され21列×一意レコードになることを検証

CLI:
  python3 scripts/fix_condition_db.py [--src PATH] [--check-only]
  python3 scripts/fix_condition_db.py --force        # バックアップ既存でも上書き
  python3 scripts/fix_condition_db.py --no-dedupe    # 重複解消を行わない（Step Aのみ）
"""

import argparse
import csv
import os
import re
import shutil
import sys


# CSV 列定義（W1-3 現状調査より、21列）
EXPECTED_COLS = 21

# moon_phase（月齢名）候補 — fishing_condition_db.csv に出現する
# 主要な和名のみ列挙。日付開始は YYYY- で始まる
MOON_PHASES = [
    "新月", "三日月", "上弦", "小望月", "満月", "十六夜",
    "立待月", "居待月", "寝待月", "更待月", "下弦", "有明月",
    "二十六夜", "三十日月", "朔",
]

# 破損パターン: 月齢名 直後に YYYY- が連続（本来は \r\n 区切り）
BREAK_PATTERN = re.compile(
    r"(" + "|".join(MOON_PHASES) + r")(\d{4}-\d{2}-\d{2})",
    re.UNICODE,
)


def repair_bytes(raw: bytes) -> tuple[bytes, int]:
    """
    破損バイト列を修復する。
    Returns: (修復後bytes, 挿入した \r\n の個数)
    """
    text = raw.decode("utf-8-sig", errors="strict")
    # BOM は decoder で除去済み。書き戻すとき BOM を付け直す必要あり
    # → caller 側で BOM を保持する方針。ここでは本文のみ処理
    # しかし decode("utf-8-sig") は BOM を食うので、別ルートでBOM有無を判定

    # バイナリパターン置換の方が安全: utf-8 表現で月齢名 + 日付 を検出
    # （文字列処理で行うと decode/encode で bom処理が面倒）
    fixed_count = 0
    out = raw
    for phase in MOON_PHASES:
        for y in range(2020, 2031):
            pattern = f"{phase}{y}-".encode("utf-8")
            replacement = f"{phase}\r\n{y}-".encode("utf-8")
            # "phase,YYYY-" のような正常な境界は別パターン
            count = out.count(pattern)
            if count:
                out = out.replace(pattern, replacement)
                fixed_count += count
    return out, fixed_count


def verify_csv_shape(path: str) -> tuple[int, list[tuple[int, int]]]:
    """
    CSV を読んで全行の列数をチェック。
    Returns: (データ行数, [(行番号, 実列数), ...] で21列以外のもの)
    """
    bad = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        if len(header) != EXPECTED_COLS:
            raise AssertionError(
                f"header列数が{EXPECTED_COLS}ではない: {len(header)}"
            )
        total = 0
        for i, row in enumerate(reader, start=2):
            total += 1
            if len(row) != EXPECTED_COLS:
                bad.append((i, len(row)))
    return total, bad


def verify_no_duplicates(path: str) -> list[tuple[str, str]]:
    """
    (日付, 地点名) の重複をチェック。
    Returns: 重複キーのリスト（空ならOK）
    """
    seen = {}
    dups = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        # 1列目=日付, 2列目=地点名（W1-3 現状調査に基づく）
        for i, row in enumerate(reader, start=2):
            if len(row) < 2:
                continue
            key = (row[0], row[1])
            if key in seen:
                dups.append(key)
            else:
                seen[key] = i
    return dups


def dedupe_keep_last(path: str) -> tuple[int, list[tuple[str, str, int, int]]]:
    """
    (日付, 地点名) が重複する行を、最後に出現した行だけ残して削除する。

    - 列順・ヘッダ・BOM・CRLF 改行はすべて原本のまま保持する。
    - 1段階目(split)で書き出したときのエンコーディング・改行規約を崩さない。

    Returns: (削除した行数, [(date, 地点名, keep_lineno, drop_lineno), ...])
    """
    # バイナリ読込して BOM 有無と改行コードを検出
    with open(path, "rb") as f:
        raw = f.read()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    # 改行コード検出（CRLF 優先、無ければ LF）
    newline_bytes = b"\r\n" if b"\r\n" in raw else b"\n"

    # テキストデコード（BOMは除去して中身だけ取る）
    text = raw.decode("utf-8-sig", errors="strict")
    # DictReader 風にパース
    import io
    reader = csv.reader(io.StringIO(text), delimiter=",")
    header = next(reader)
    rows = list(reader)

    # keep-last を実現するため、末尾→先頭でスキャンして初出だけ保持 → 逆順に戻す
    seen = set()
    kept_idx: list[int] = []
    drop_records: list[tuple[str, str, int, int]] = []
    # 一旦、各 (日付,地点) の最後の出現インデックスを見つける
    last_index: dict[tuple[str, str], int] = {}
    for i, row in enumerate(rows):
        if len(row) < 2:
            continue
        last_index[(row[0], row[1])] = i
    # 原本順に走査して、最後の出現のみ残す
    for i, row in enumerate(rows):
        if len(row) < 2:
            kept_idx.append(i)  # スキーマ外は保持
            continue
        key = (row[0], row[1])
        if last_index.get(key) == i:
            kept_idx.append(i)
        else:
            # 削除対象: 物理行番号(ヘッダ+1)と、残す方の行番号を記録
            drop_lineno = i + 2
            keep_lineno = last_index[key] + 2
            drop_records.append((row[0], row[1], keep_lineno, drop_lineno))

    if not drop_records:
        return 0, []

    # 書き出し（原本のエンコーディング・改行を踏襲）
    out = io.StringIO()
    writer = csv.writer(out, lineterminator=newline_bytes.decode("ascii"))
    writer.writerow(header)
    for i in kept_idx:
        writer.writerow(rows[i])

    body = out.getvalue().encode("utf-8")
    if has_bom:
        body = b"\xef\xbb\xbf" + body

    with open(path, "wb") as f:
        f.write(body)

    return len(drop_records), drop_records


def main():
    parser = argparse.ArgumentParser(
        description="fishing_condition_db.csv 12,497行目41列化を修復"
    )
    parser.add_argument(
        "--src",
        default="data/fishing_condition_db.csv",
        help="入力CSVのパス（デフォルト: カレントの fishing_condition_db.csv）",
    )
    parser.add_argument(
        "--backup-suffix",
        default=".bak.20260418",
        help="バックアップファイルの拡張子（既存のときは上書きせず、--force 必要）",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="修復せず、現状の破損状況を表示するのみ",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="バックアップが既に存在しても上書きする",
    )
    parser.add_argument(
        "--no-dedupe",
        action="store_true",
        help="Step A（41列化分割）のみ実施し、Step B（重複解消）を行わない",
    )
    args = parser.parse_args()

    src = args.src
    if not os.path.exists(src):
        print(f"[ERROR] ソースが存在しない: {src}")
        sys.exit(2)

    # 現状チェック
    try:
        total_before, bad_before = verify_csv_shape(src)
    except Exception as e:
        print(f"[ERROR] CSV読み込み失敗: {e}")
        sys.exit(2)

    print(f"[INFO] 読込: {src}")
    print(f"[INFO] データ行数: {total_before}")
    print(f"[INFO] 21列以外の行: {len(bad_before)}")
    for line, cols in bad_before:
        print(f"         行{line}: {cols}列")

    # 事前重複チェック（修復後の報告用）
    dups_before = verify_no_duplicates(src)

    if args.check_only:
        print(f"[INFO] (日付, 地点名) 重複: {len(dups_before)}件")
        for k in dups_before[:10]:
            print(f"         {k}")
        print("[INFO] --check-only 指定。修復せず終了")
        exit_code = 0 if (not bad_before and not dups_before) else 1
        sys.exit(exit_code)

    if not bad_before and not dups_before:
        print("[OK] 既に21列正常＆重複なし。修復不要")
        sys.exit(0)

    # バックアップ（Step A 着手前の原本を保存）
    backup = src + args.backup_suffix
    if os.path.exists(backup) and not args.force:
        print(f"[ERROR] バックアップ既存: {backup}（--force で上書き可）")
        sys.exit(2)
    shutil.copy2(src, backup)
    print(f"[OK] バックアップ: {backup}")

    # === Step A: 41列化の分割修復 ===
    n_inserted = 0
    if bad_before:
        with open(src, "rb") as f:
            raw = f.read()
        fixed, n_inserted = repair_bytes(raw)
        if fixed == raw:
            print("[ERROR] 修復パターンに該当なし（CSVは21列違反だがパターン不明）")
            sys.exit(3)
        with open(src, "wb") as f:
            f.write(fixed)
        print(f"[OK] Step A: {n_inserted} 箇所に \\r\\n を挿入")
    else:
        print("[SKIP] Step A: 41列化違反なし")

    # 分割後の形状検証
    total_after_split, bad_after_split = verify_csv_shape(src)
    print(f"[INFO] Step A 後: {total_after_split} 行、21列違反 {len(bad_after_split)}件")
    if bad_after_split:
        print("[FAIL] 修復後も21列違反が残存")
        for line, cols in bad_after_split:
            print(f"         行{line}: {cols}列")
        sys.exit(4)

    # === Step B: 重複解消 (keep-last) ===
    n_dedupe = 0
    if not args.no_dedupe:
        dups_after_split = verify_no_duplicates(src)
        if dups_after_split:
            n_dedupe, drop_records = dedupe_keep_last(src)
            print(f"[OK] Step B: {n_dedupe} 行を削除 (keep-last)")
            for date, place, keep_ln, drop_ln in drop_records:
                print(f"         ({date}, {place}): 残す=行{keep_ln}, 削除=行{drop_ln}")
        else:
            print("[SKIP] Step B: 重複なし")
    else:
        print("[SKIP] Step B: --no-dedupe 指定")

    # 最終検証
    total_final, bad_final = verify_csv_shape(src)
    dups_final = verify_no_duplicates(src)
    print(f"[INFO] 最終状態: {total_final} 行、21列違反 {len(bad_final)}件、重複 {len(dups_final)}件")

    if bad_final or dups_final:
        print("[FAIL] 最終状態に問題あり")
        sys.exit(5)

    print(f"[DONE] 修復完了")
    print(f"  Step A: \\r\\n 挿入 {n_inserted}箇所")
    print(f"  Step B: 重複削除 {n_dedupe}行")
    print(f"  行数: {total_before} → {total_final}")


if __name__ == "__main__":
    main()
