# tests/golden/ — 現行互換CSV/JSONのスナップショット

採取日: 2026-04-18（W5-1 既存データ移行タスクで採取）
採取元: V6.0リポ（OneDrive 稼働中）+ 室戸沖リポ + 室戸海流リポ + 出船可否リポ

## 目的

新アーキの `engines/emit_*` が生成する互換CSV（3本）と、C系の現行ファイル（3本）+ C⑤（1本）を
バイト単位のスナップショットとして保管する。今後の改修で既存アプリの読み取り挙動を壊さないこと
を保証するための比較基準。

## ファイル一覧

| ファイル | サイズ | SHA256 | 由来 |
|---|---:|---|---|
| fishing_data.csv | 168,708 | a66b38fafe26677a7f41c22c03b5a6c61f3c5189d94628160472028a265e48b6 | V6.0リポ現行（master_catch.csv 初期化の源。emit_fishing_data と完全バイト一致） |
| fishing_condition_db.csv | 1,487,613 | 6a7125e5c8bc0102e94fca7928a4ce97e5be3ea5cc3b2119b6c2a1b4b2d0c6d7 | **W5-1 修復後**（12,497行目41列化を分割、(2026-04-12, 室戸) 重複をkeep-lastで解消） |
| fishing_condition_db.json | 7,065,937 | 254141e1b65b67a8698fd3da074e0ca4a70e575de04257fc2bf63e01256b088f | V6.0リポ現行（CSV 修復後と 12,536 レコード整合） |
| fishing_integrated.csv | 227,278 | 11665af4232ebf6d9bdcc440e4805dd27900266aad72f687bc793e2d8fa9d856 | V6.0リポ現行（emit_fishing_integrated と完全バイト一致） |
| fishing_muroto_v1.csv | 266,852 | 77d6cc00fafa4d4477ed855e382a532839e05a9acef8a8cd7aa17906095bcca8 | **W5-1 emit 出力を採用**（修復後C③で 2026-04-12 室戸のC③値が正しく埋まる 3行を含む。稼働中 OneDrive 版より +165 bytes、3レコードの天気水温列が空欄→値入りに） |
| muroto_offshore_current_all.csv | 644,385 | 0ee2f96b8b1c7d0fe44f39823c378f610b589aaad4c512e71d40dfe2395b4236 | 室戸沖リポ現行 |
| forecast_data.json | 2,286 | 75c9bb8210e44f04f6cadc47c70b5b68cc279b96ae553ad622d5f2a8127a3614 | 出船可否リポ現行 |

## バイト一致確認（W5-1 時点）

`engines/emit_all` の出力と以下がバイト完全一致：
- fishing_data.csv       ✓ 完全一致
- fishing_integrated.csv ✓ 完全一致
- fishing_muroto_v1.csv  ✓ 完全一致（emit 出力をゴールデンに採用したため）

## 許容差分

本ゴールデンに対する `cmp` は完全一致を期待する。差分が出る場合は以下を疑う:
1. C③ `fishing_condition_db.csv` に新日付が追加された（ゴールデン更新が必要）
2. master_catch.csv 初期化時のシード値が変わった（UUID再生成でバイト変化）
3. 新しい emit ロジックが導入された（ゴールデン再採取が必要）

## 更新手順

1. C③/C④/C⑤ の最新化（GitHub Actions 手動実行 etc.）
2. `python3 -m engines.emit_all --out-dir tests/golden` で再採取
3. SHA256 を本 README に追記
