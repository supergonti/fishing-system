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

---

## ローカル開発・動作確認（W5-3 追記）

### 起動手順

1. 前提: Python 3.11、Node.js 20（収集系のみ使う場合は Python だけで可）
2. 依存インストール: `pip install -r requirements.txt`
3. ローカル HTTP サーバ起動: `python -m http.server 8000`
4. ブラウザで `http://localhost:8000/<アプリ名>.html` にアクセス
5. ページ最上部の共通ナビバーで6アプリ間を移動できる

### 共通ナビバーについて

W5-3 で全6アプリの先頭に共通ナビ（`<nav class="fs-nav">`）を埋め込んだ。
現在ページは自動でハイライトされる（`<body data-fs-page="...">` を読み取って判定）。

### favicon について

`favicon.svg` をルートに配置し、全 HTML から `<link rel="icon" type="image/svg+xml" href="./favicon.svg">` で参照。
ブラウザタブで青地に波と釣り針のアイコンが表示される。差し替えたい場合は `favicon.svg` を編集するだけ。

### fetch_forecast.py の使い方（W5-3 改善）

```powershell
# 既定: data/forecast_data.json に保存
python scripts/fetch_forecast.py

# 出力先を変えたい場合
python scripts/fetch_forecast.py --output /tmp/test_forecast.json
```

- 失敗時は最大3回まで指数バックオフ（2/4/8秒）で再試行
- ログは stderr と `logs/forecast.log` に時刻つきで出力
- 例外時は exit 1（CI から失敗を検知できる）

---

## トラブルシューティング

| 症状 | 対応 |
|---|---|
| `./data/*.csv` が 404 になる | `python -m http.server 8000` 経由で開く（`file://` 直叩きは NG） |
| favicon が表示されない | ブラウザキャッシュをクリア（Ctrl + F5） |
| `fetch_forecast.py` が exit 1 | 3回再試行でも取れていない。Open-Meteo 一時障害 or 社内プロキシで弾かれている可能性。`logs/forecast.log` を確認、時間を空けて再実行 |
| `update-conditions.yml` が空振り | `data/fishing_data.csv` の push がトリガー。collector.html から push されていないと動かない |
| ナビが既存レイアウトとぶつかる | `fs-nav` プレフィックスで衝突回避済。それでも干渉する場合は該当ファイルの `<style>.fs-nav...</style>` を調整 |

---

## データアーキテクチャの原則

- `data/master_catch.csv` を**正本**とし、`engines/` の emit 系で派生 CSV を生成
- 散在コピー（旧リポ各所の同名 CSV）は統合リポでは保持しない
- 全データ参照は `./data/<filename>` の相対パスで統一（HTML/JS とも）

詳細は `fishing-renovation/設計_W3-1_統合アーキ_20260417.md` ほか W3 系設計ドキュメント参照。

---

## 将来の海域別拡張

現行の6アプリは室戸沖を主対象とする。将来「足摺沖」「宇和島沖」など海域別ソフトを追加する場合：

### ファイル命名ルール（推奨）

- `<海域名>_fishingdata.html`（例: `asizuri_fishingdata.html`）
- `<海域名>_fishing_analysis.html`
- `<海域名>_fishingforecast.html`

### ナビへの追加方法

`<nav class="fs-nav">` 内に `<a>` を1行追加し、対応する HTML の `<body>` に `data-fs-page="<識別子>"` を設定する。
海域が3つ以上に増えたら、`<details>` か CSS dropdown でグルーピングを検討。

### データ層の拡張

地点別データは `data/<海域名>/<filename>` のサブフォルダに格納する方針が基本。
集約マスター（`master_catch.csv`）は海域フィルタを `area` 列で扱う想定（既存スキーマ）。

---

## 開発版／安定版の運用

CLAUDE.md の運用ルールに従い、開発中の HTML は `<アプリ名>_dev.html` として並置する。
詳しくは [`docs/versioning.md`](./docs/versioning.md) を参照。

現時点（W5-3 完了時点）では `_dev.html` ファイルは存在しない。必要になった時点で個別作成する。
