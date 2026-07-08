# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 概要

BibManager — .bib ファイルと同期できる文献管理 Web アプリ（Flask + SQLite + 単一 HTML の SPA）。依存は Flask のみ。テストスイートは無い。

## コマンド

```bash
source cenv/bin/activate   # リポジトリ内の venv（README では venv/ だが実際は cenv/）
python app.py              # http://127.0.0.1:5000 で起動
```

変更後の動作確認（テストが無いため）:

```bash
python -m py_compile app.py database.py bib_parser.py notion_import.py  # 構文チェック
curl -s http://127.0.0.1:5000/api/stats   # サーバ起動後の疎通確認
```

## データベース（重要）

- DB パスは環境変数 `PAPERMANAGER_DB` で切り替わる。未設定なら `mydb.db`（自動生成・使い捨て可）。
- **`bibmanager.db` は git 管理されており、所有者の実データが入っている。テストや動作確認でこのファイルに書き込まない・削除しないこと。** 動作確認は `PAPERMANAGER_DB` を未設定にするか一時ファイルを指定して行う。
- `papers.db` は旧ファイル。参照しない。

## アーキテクチャ

- `app.py` — Flask ルート層。`/` が UI、`/api/*` が JSON REST API（entries / tags / keywords / citations / import / export / stats）。起動時に `db.init_db()` を実行。
- `database.py` — SQLite の CRUD すべて（最大のモジュール）。スキーマ変更はここ。
- `bib_parser.py` — BibTeX パーサ（外部依存なしの自前実装）。
- `notion_import.py` — Notion CSV からのインポート。
- `templates/index.html` — フロントエンド全体（約 2700 行、vanilla JS）。UI 変更はすべてこの 1 ファイル。

## ドメインルール

- .bib インポートは「既存エントリの bib フィールドのみ更新し、ユーザーが付けたタグ・メモ・言及は保持する」仕様。インポート処理を触るときはこの不変条件を壊さない。
