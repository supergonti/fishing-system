# 開発版／安定版の運用方針（fishing-system）

本リポジトリ `fishing-system` における開発版（`_dev.html`）と安定版の運用ルールを
`Claude 取り扱いファイル/CLAUDE.md` の「開発ファイルの運用ルール」に沿って具体化したもの。

---

## 1. 原則

| 役割 | ファイル名 | 更新タイミング |
|---|---|---|
| **安定版** | `<アプリ名>.html`（例: `fishingdata.html`） | 開発版がひと段落した時、Gonti さんが「この時点で更新」と明示したタイミングのみ |
| **開発版** | `<アプリ名>_dev.html`（例: `fishingdata_dev.html`） | 日々の修正・改善を反映する（毎開発で更新） |

- 両ファイルとも同じリポジトリに配置し、GitHub に push する
- GitHub Pages 上で新旧バージョンを同時に確認できる状態を維持する
- 開発作業は常に**開発版に対して行う**。安定版への反映は明示的な上書き操作
- 安定版の無断改変は禁止。直接 `<アプリ名>.html` を編集してはならない

---

## 2. 該当範囲と現状（W5-3 完了時点）

W5-2 の統合リポ構築時点では、旧リポの「development.html」は基本的に採用せず、
**安定版のみを移植**した。そのため 2026-04-18 現在、`_dev.html` ファイルは**存在しない**。

将来開発を再開する時点で、以下の命名で `_dev.html` を作成する：

| 安定版 | 想定される開発版 |
|---|---|
| `collector.html` | `collector_dev.html` |
| `condition.html` | `condition_dev.html` |
| `fishingdata.html` | `fishingdata_dev.html` |
| `muroto_offshore_current.html` | `muroto_offshore_current_dev.html` |
| `muroto_fishing_analysis.html` | `muroto_fishing_analysis_dev.html` |
| `muroto_fishingforecast.html` | `muroto_fishingforecast_dev.html` |

---

## 3. 運用フロー（標準）

1. Gonti さん or Claude が開発版（`<アプリ名>_dev.html`）を修正
2. ローカルで `python -m http.server 8000` → ブラウザ動作確認
3. 必要に応じ push → GitHub Pages で確認
4. Gonti さん判断で「この dev を安定版に昇格する」と明示
5. `<アプリ名>_dev.html` の内容を `<アプリ名>.html` に上書きコピーして commit
6. ナビ（`<nav class="fs-nav">`）には安定版のみを載せる。`_dev.html` は直URLでのみアクセス

---

## 4. 命名ルールの例外と由来

- `muroto_fishing_analysis.html` は旧リポ（`Fishing-Record-Analysis`）で `index.html` と
  `development.html` の2本体制だったが、統合リポでは安定版だけを採用し、
  `muroto_fishing_analysis.html` にリネームした（W5-2 統合リポ構築）
- 将来この解析アプリの開発版を作るときは `muroto_fishing_analysis_dev.html` とする
- `fishingdata.html` は将来「海域別」を導入する場合、安定版側が `muroto_fishingdata.html` に
  改名される可能性がある（Gonti さん方針、2026-04-18 W5-3 指示書 §0.4）。
  その場合の開発版は `muroto_fishingdata_dev.html`

---

## 5. 共通ナビバーとの関係

`<nav class="fs-nav">` の `<a>` 要素は**安定版のみ**を指す。
開発版は直 URL（例: `http://localhost:8000/fishingdata_dev.html`）でアクセス。

安定版のみを掲載することで：
- ユーザー（主に Gonti さん自身）が誤って開発版を正本として扱うのを防ぐ
- 将来人に共有するときもナビから開発版を見せない
- ナビの見た目がコンパクトに保たれる
