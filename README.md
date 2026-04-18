# fishing-system（室戸沖釣果統合システム）

室戸岬沖の釣果記録と海洋観測データを一元管理する統合リポジトリです。
釣果の収集・集計・解析・出船判断までを6アプリ＋データ層（`data/`）で構成します。

2026-04-18 に 4つの旧リポジトリ（V6.0 / 室戸沖釣果 / 海流 / 解析v2 / 出船可否）を
凍結（Archive）し、本リポジトリへ集約しました（W5-2 統合リポ構築）。

## アプリ構成（6本）

| URL | ファイル | 用途 |
|---|---|---|
| `/collector.html` | `collector.html` | V5.5 釣果収集（スマホ入力 → GitHub へ `data/fishing_data.csv` を直接 push） |
| `/condition.html` | `condition.html` | 気象条件DB（IndexedDB、Open-Meteo からの環境条件取り込み） |
| `/fishingdata.html` | `fishingdata.html` | 統合釣果DB（`data/fishing_integrated.csv` を読み込み表示） |
| `/muroto_offshore_current.html` | `muroto_offshore_current.html` | 室戸沖海流ダッシュボード（CMEMS 由来） |
| `/muroto_fishing_analysis.html` | `muroto_fishing_analysis.html` | 釣果解析（`data/analysis/analysis_result.json` を読み込み） |
| `/muroto_fishingforecast.html` | `muroto_fishingforecast.html` | 出船可否判断（Open-Meteo + `data/criteria.json`） |

## データ層（`data/`）

全マスターデータを `data/` 配下に集約する。

| ファイル | 内容 | 生成元 |
|---|---|---|
| `master_catch.csv` | 26列の正本マスター釣果（W5-1 新アーキ） | `engines/init_master.py` |
| `fishing_data.csv` | V6.0 互換 19列（collector/fishingdata で共有） | `engines/emit_fishing_data.py` |
| `fishing_condition_db.csv` | 気象条件（Open-Meteo 由来、8地点分） | `scripts/update-conditions.js` |
| `fishing_condition_db.json` | 同上（JSON 形式） | 同上 |
| `fishing_integrated.csv` | 釣果×気象 LEFT JOIN（34列） | `engines/emit_fishing_integrated.py` or `scripts/merge-data.js` |
| `fishing_muroto_v1.csv` | 釣果×気象×海流2点 JOIN（42列） | `engines/emit_fishing_muroto_v1.py` or `scripts/build_database.py` |
| `muroto_offshore_current_all.csv` | 室戸沖海流（5地点、CMEMS 由来） | `scripts/main.py` |
| `forecast_data.json` | 出船予報（Open-Meteo 由来、無認証） | `scripts/fetch_forecast.py` |
| `criteria.json` | 出船判定基準 | 手動編集 |
| `analysis/analysis_result.json` | 解析v2 の統計/可視化エンジン出力 | `scripts/analyze_engine.py` |
| `js/fishing_muroto_v1_data.js` | muroto_v1 の JS ラップ（室戸沖釣果 HTML 用） | `scripts/build_database.py` |
| `js/muroto_offshore_current_dashboard_data.js` | 海流ダッシュボード用 JS | `scripts/update_offshore_dashboard_data.py` |

## アーキテクチャ概要

```
[collector.html] → GitHub push → data/fishing_data.csv
                                         ↓
                      (engines/init_master.py 起点)
                                         ↓
                              data/master_catch.csv   ← 正本
                                         ↓
                   ┌─────────────┼─────────────┐
                   ↓             ↓             ↓
         emit_fishing_data  emit_fishing_muroto_v1  emit_fishing_integrated
                   ↓             ↓             ↓
         fishing_data.csv  fishing_muroto_v1.csv  fishing_integrated.csv
```

詳細な設計は `fishing-renovation/` 配下の設計ドキュメント（W1〜W5 のバッチ成果）を参照。

## 開発環境

- Python 3.11
- Node.js 20（`scripts/*.js` の実行用）
- Git (Windows)、GitHub Pages（`main` ブランチから公開）

## セットアップ

```powershell
# C:\Dev\ 以下に配置して使う
cd C:\Dev\fishing-system
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## 主要コマンド

```powershell
# ゴールデン比較テスト（W4-1 / W5-1）
python -m tests.golden_match_test

# master_catch から3互換CSVを一括生成（W4-1）
python -m engines.emit_all --out-dir .ci_out

# データ整合性検査（W4-3）
python scripts/validate_all.py `
  --condition-csv  data/fishing_condition_db.csv `
  --condition-json data/fishing_condition_db.json `
  --current-csv    data/muroto_offshore_current_all.csv `
  --forecast-json  data/forecast_data.json

# 解析エンジン実行（data/analysis/analysis_result.json を更新）
python scripts/analyze_engine.py
```

## GitHub Actions ワークフロー

| ワークフロー | トリガー | 役割 |
|---|---|---|
| `update-conditions.yml` | `data/fishing_data.csv` push / 週1 / 手動 | Open-Meteo から条件DB更新 |
| `update_data.yml` | 毎日 6:30 JST / 手動 | CMEMS から海流データ更新（secrets 必須） |
| `build-and-deploy.yml` | `data/*.csv` push / 週1 / 手動 | muroto_v1.csv + JS 再ビルド |
| `update-forecast.yml` | 6/9/12/15/18 時 / 手動 | Open-Meteo から予報JSON更新（secrets 不要） |
| `rebuild_master.yml` | 週1 / 手動 | `emit_all` + `golden_match_test` + `validate_all` |

### Secrets（W5-4 で設定）

| Secret | 用途 |
|---|---|
| `CMEMS_USERNAME` | Copernicus Marine Service API 認証 |
| `CMEMS_PASSWORD` | 同上 |

## ローカル開発手順

```powershell
# ローカルで 6アプリの動作確認
cd C:\Dev\fishing-system
python -m http.server 8000
# ブラウザで http://localhost:8000/collector.html 等
```

## 移行元リポジトリ（Archive 予定）

2026-04-18 時点で以下の 4リポジトリを凍結予定（W5-4 で GitHub 上を Archive 化）：

- `supergonti/Fishing-Record-Tool`（V6.0 釣果収集）
- `supergonti/muroto-ocean-current`（海流データ）
- `supergonti/muroto-fishing-database`（室戸沖釣果DB）
- `supergonti/Fishing-Record-Analysis`（解析v2）
- `supergonti/muroto_fishing_forecast`（出船可否）

本リポジトリ（`supergonti/fishing-system`）がこれら5つを統合した正本となります。
