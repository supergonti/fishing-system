# W7-5 拡張プルーフ実施レポート

実施日：2026-04-21
PR：`feature/w7-5-expansion-proof` → main（`#<TBD>`）
対応指示書：`指示書_W7-5_拡張プルーフテスト_20260420.md`
親計画：`計画書_司令塔5_釣り場分類人機協調改革_20260420.md`（§3-5 sea_area 階層）
依存：W7-4（`ace321a`）マージ済

---

## 1. テスト概要

W7-4 で導入した `current_points[].sea_area` 階層化が、実際の海域拡張フェーズ（足摺沖 4 点追加）で正しく機能することを、**本物の stations_master.json を一切変更せずに**、fixture のみで実証する。

### 1-1. 設計原則

| 原則 | 具体 |
|---|---|
| 本物ファイル不変 | `data/b_mapping/stations_master.json` / `spot_station_map.json` / `master_catch.csv` を W7-5 では一切変更しない |
| fixture 独立 | `tests/fixtures/` 配下に mock 3 ファイルを配置し、SpotClassifier の各パス引数で差し替える |
| 本物は read-only 参照 | 別名辞書（`spot_canonical_rules.json`）と回帰テスト用の本物 csv は read で参照 |
| 学習の非対称性 | fixture 側で "足摺岬" canonical の sea_area='足摺沖' を注入、lookup hit 経路を実測 |

### 1-2. fixture 構成

| ファイル | 内容 | サイズ | encoding / 改行 |
|---|---|---:|---|
| `tests/fixtures/stations_master_with_ashizuri.json` | 室戸 5 点（sea_area='室戸沖'）+ 足摺 4 点（sea_area='足摺沖'） + 既存 weather_stations 8 点、version `2.1.0-test-ashizuri` | 2,322 B | utf-8 / LF |
| `tests/fixtures/spot_station_map_with_ashizuri.json` | 室戸沖（canonical_spot='室戸沖'）+ 足摺岬（canonical_spot='足摺岬', raw_spots=["足摺岬","足摺岬沖","高知足摺岬"]）、version `1.0.0-test-ashizuri` | 835 B | utf-8 / LF |
| `tests/fixtures/master_catch_ashizuri_sample.csv` | 足摺系 3 行 + 室戸系 2 行、26 列スキーマ遵守、record_id は UUID v4 | 1,257 B | utf-8-sig (BOM) / CRLF / 末尾改行 |

### 1-3. ダミー足摺沖 4 点の座標（fixture）

足摺岬の ENS / WSW / 南北に 2-5km ほど配置した非実在座標（真の CMEMS グリッドは別タスクで決定）：

| name | lat | lng | sea_area | 足摺岬(32.72,132.95) からの距離 |
|---|---:|---:|---|---:|
| 足摺北 | 32.75 | 132.95 | 足摺沖 | 3.336 km |
| 足摺南 | 32.68 | 132.95 | 足摺沖 | 4.448 km |
| 足摺東 | 32.72 | 133.00 | 足摺沖 | 4.678 km |
| 足摺西 | 32.72 | 132.90 | 足摺沖 | 4.678 km |

参考：足摺岬 (32.72, 132.95) から室戸 5 点は 113-133 km（閾値 50 km 超のため本来閾値越えで None だが、sea_area フィルタ後は足摺 4 点に収束するため該当しない）

---

## 2. 検証項目（pytest ケース）

| # | テスト関数 | 目的 |
|---|---|---|
| 1 | `test_ashizuri_spot_routes_to_ashizuri_current_points` | canonical='足摺岬' が lookup hit → sea_area='足摺沖' フィルタ → 足摺 4 点に収束 |
| 2 | `test_muroto_spot_stays_in_muroto_current_points` | canonical='室戸沖' が lookup hit → sea_area='室戸沖' フィルタ → 室戸 5 点に収束、足摺 4 点に混ざらない |
| 3 | `test_ashizuri_raw_variants_all_route_correctly` | '足摺岬沖'（alias 未登録、lookup miss → flat fallback だが距離上足摺 4 点に収束） '高知足摺岬'（県名 prefix 除去で canonical='足摺岬' → lookup hit） |
| 4 | `test_existing_rows_nearest_station_regression` | 本物 `data/master_catch.csv` 座標あり全行で `nearest_station` 値が W7-5 後も完全一致 |
| 5 | `test_fixture_csv_is_utf8_bom_crlf` | fixture csv の encoding / 改行 / 26 列保全（司令塔5 §W7-5 軽微補足） |
| 6 | `test_real_stations_master_is_unchanged_by_w7_5` | 本物 stations_master.json の current_points 数 = 5 ＆ sea_area 全て '室戸沖'、足摺4点未混入（W7-5 契約の機械的担保） |

---

## 3. 実行結果

### 3-1. pytest（Windows 側 PowerShell、2026-04-21 実測）

```
platform win32 -- Python 3.14.3, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Dev\fishing-system
collected 37 items

tests/test_expansion_ashizuri.py        6 件 PASSED  (W7-5 新規)
tests/test_sea_area_hierarchy.py       10 件 PASSED  (W7-4 回帰)
tests/test_substring_fallback.py       15 件 PASSED  (W7-2 回帰)
tests/test_unknown_sentinel.py          6 件 PASSED  (W7-1 回帰)
────────────────────────────────────────────────────────────
合計                                   37 件 PASSED, 0 FAILED (0.17s)
```

（W7-5 新規 6 件 + W7-1/2/4 回帰 31 件。W7-3 は collector.html UI 領域で pytest カバレッジなし。）

W7-5 新規 6 件内訳：

1. `test_ashizuri_spot_routes_to_ashizuri_current_points` ─ lookup hit 経路の足摺
2. `test_muroto_spot_stays_in_muroto_current_points` ─ lookup hit 経路の室戸
3. `test_ashizuri_raw_variants_all_route_correctly` ─ 足摺岬沖 / 高知足摺岬 raw 揺れ
4. `test_existing_rows_nearest_station_regression` ─ 本物 master_catch.csv 全行 regression
5. `test_fixture_csv_is_utf8_bom_crlf` ─ fixture encoding 健全性
6. `test_real_stations_master_is_unchanged_by_w7_5` ─ 本物 stations_master.json 不変保証

### 3-2. ビジュアル確認（指示書 §5-2 の直接 print 相当、2026-04-21 実測）

fixture 構成で classify() を 5 raw 揺れパターンで実行した結果：

| raw | lat | lng | nearest_station | current_point | current_distance_km |
|---|---:|---:|---|---|---:|
| 足摺岬 | 32.72 | 132.95 | 足摺 | 足摺北 | 3.335847799336888 |
| 足摺岬沖 | 32.72 | 132.95 | 足摺 | 足摺北 | 3.335847799336888 |
| 高知足摺岬 | 32.72 | 132.95 | 足摺 | 足摺北 | 3.335847799336888 |
| 室戸沖 | 33.29 | 134.18 | 室戸 | 北東 | 10.479816759747118 |
| 高知室戸沖 | 33.29 | 134.18 | 室戸 | 北東 | 10.479816759747118 |

判定：
- 足摺系 3 raw 揺れすべて `nearest_station=足摺`, `current_point ∈ {足摺北,足摺南,足摺東,足摺西}` に収束（本ケースでは足摺北が最近傍 3.336 km で優勝）
- 室戸系 2 raw パターンは `nearest_station=室戸`, `current_point=北東` (10.480 km) に収束、足摺 4 点には寄らない
- `足摺岬沖` は canonical='足摺岬沖' で lookup miss → flat fallback だが、足摺 4 点が室戸 5 点より圧倒的に近い（3-5 km vs 113-143 km）ため結果的に足摺点に収束。sea_area 階層化の貢献は `高知足摺岬` → canonical='足摺岬' の lookup hit 経路で享受

### 3-3. 本物ファイル不変確認（`git status --short`）

```
?? docs/W7-5_expansion_proof_report.md
?? tests/fixtures/master_catch_ashizuri_sample.csv
?? tests/fixtures/spot_station_map_with_ashizuri.json
?? tests/fixtures/stations_master_with_ashizuri.json
?? tests/test_expansion_ashizuri.py
```

- `data/b_mapping/stations_master.json`：未変更（`??` にも `M` にも現れない）
- `data/b_mapping/spot_station_map.json`：未変更
- `data/b_mapping/spot_canonical_rules.json`：未変更
- `data/master_catch.csv`：未変更
- production コード（`engines/` / `scripts/` / `collector*.html`）：未変更
- `.github/workflows/`：未変更

本物ファイル不変契約（W7-5 原本 §3 および緊急停止条件 #8 / #10）完全遵守。

---

## 4. 結論

sea_area 階層（W7-4 導入）は実運用シナリオ（足摺沖追加）で正しく機能することを、fixture ベースの E2E プルーフで実証した。本物の `data/b_mapping/stations_master.json` への足摺 4 点追加は、**足摺沖遊漁船データ取り込み開始時（別タスク）** に実施する。

W7 シリーズ（W7-1 〜 W7-5）の最終実行タスクが完了し、親計画 §9 の KPI「足摺沖ダミー 4 点を stations_master に入れたら仮データが足摺沖 4 点に正しく割当」が fixture 経由で達成。

---

## 5. 次のステップ（別タスク）

W7-5 マージ後、運用観察を経て以下のタスク群へ接続（本 PR の範囲外）：

1. 足摺沖 4 点の正式座標を決定（CMEMS グリッドから最近傍点選定）
2. `data/b_mapping/stations_master.json` に 4 点追加（sea_area='足摺沖'、version `2.2.0` へ minor bump）
3. `data/b_mapping/spot_station_map.json` に足摺系 canonical_spot を追加（confidence='manual'）
4. `collector.html` / `collector_dev.html` で足摺沖 spot の入力動作確認（S4 シリーズ領域）
5. CI パイプライン（sync_after_current_update）で足摺沖海流データの取得と派生 CSV 生成確認
6. W7-6（解析 UI グループ分類の改良）は親計画 §5 で別プロジェクト扱い、司令塔6 以降で検討

---

## 6. 参考

- `指示書_W7-5_拡張プルーフテスト_20260420.md`（原本、§1〜§9）
- `計画書_司令塔5_釣り場分類人機協調改革_20260420.md` §3-5（sea_area 階層）
- `司令塔5_事前確認レポート_W7全指示書整合性_20260420.md` §W7-5（fixture csv BOM+CRLF 軽微補足）
- `W7-4_完了報告_20260421.md`（W7-4 merged: `ace321a`、regression mismatch=0）

---

## 改訂履歴

| 版 | 日付 | 変更 |
|---|---|---|
| 初版 | 2026-04-21 | W7-5 拡張プルーフ実装、fixture 3 ファイル ＋ pytest 6 件 配置。Windows 側 pytest 結果は W7-5 完了報告受領時に差し込み |
