# BibManager

bibファイルと同期できる文献管理Webアプリ。

## セットアップ

### 必要なもの
- Python 3.10 以上

### 初めて使う人向け（クローンから起動まで）

```bash
git clone https://github.com/LowToneVoice/papermanager.git
cd papermanager
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
PAPERMANAGER_DB=mydb.db python app.py
```

`PAPERMANAGER_DB=mydb.db` を指定することで、リポジトリに含まれるデータベースとは別の空のデータベースが自動生成されます。

> **毎回入力を省略したい場合** — プロジェクトルートに `.env` ファイルを作成してください：
> ```
> PAPERMANAGER_DB=mydb.db
> ```
> その後は `python app.py` だけで起動できます（python-dotenv は不要、シェルで `export PAPERMANAGER_DB=mydb.db` でも可）。

ブラウザで http://localhost:5000 を開く。

### 開発者・リポジトリ管理者向け（既存DBを引き継ぐ場合）

```bash
source venv/bin/activate
python app.py   # 環境変数なし → bibmanager.db（git管理）を使用
```

## 初回の使い方

1. 画面右上の **「⬆ Import .bib」** をクリック
2. `.bib` ファイルをドラッグ&ドロップ、またはクリックして選択
3. インポート完了（追加/更新/スキップ件数が表示される）

## 機能

| 機能 | 操作 |
|------|------|
| 検索 | ヘッダーの検索バー（タイトル・著者・キーワード・メモを全文検索） |
| `/` キー | 検索バーにフォーカス |
| タグフィルタ | 左サイドバーのタグをクリック（AND絞り込み） |
| 年フィルタ | 左サイドバーの年入力欄 |
| 詳細表示 | 文献カードをクリック |
| タグ追加 | 詳細パネル > タグ欄にタイプ（Enterまたはカンマで確定、既存タグはオートコンプリート） |
| キーワード追加 | 詳細パネル > キーワード欄にタイプ（Enterで確定） |
| 読書メモ | 詳細パネル > 「実際に何が書かれていたか」欄（フォーカスが外れたとき自動保存） |
| 他文献での言及 | 詳細パネル > 「他の文献での言及」> 「＋ 言及を追加」 |
| BibTeX コピー | 詳細パネル > BibTeX欄の📋ボタン |
| エクスポート | ヘッダーの「⬇ Export .bib」 |

## bibファイルとの同期

- **インポート:** bibファイルを読み込む。既存エントリはbibフィールドのみ更新し、タグ・メモは保持。
- **エクスポート:** 現在のDBの全エントリをbibファイルとして出力。

## ファイル構成

```
bibmanager/
├── app.py          # Flaskアプリ本体・APIエンドポイント
├── bib_parser.py   # bibファイルのパース（純Pythonで外部依存なし）
├── database.py     # SQLite操作・CRUD
├── bibmanager.db   # データベース（自動生成）
├── templates/
│   └── index.html  # フロントエンドUI
└── README.md
```

## データベースのバックアップ

`bibmanager.db` を定期的にコピーしておくことを推奨。
