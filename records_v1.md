# v1作成にあたっての記録

## ディレクトリ構成

```txt
paper_manager/
├── app.py
├── requirements.txt
├── README.md
├── data/
│   └── papers.db
├── documents/
│   ├── dbscheme.md
│   └── screenspec.md
├── src/
│   ├── config.py
│   ├── db.py
│   ├── models.py
│   ├── schemas.py
│   ├── repositories/
│   │   ├── papers.py
│   │   ├── authors.py
│   │   ├── tags.py
│   │   └── keywords.py
│   ├── services/
│   │   ├── bibtex_parser.py
│   │   ├── bibtex_exporter.py
│   │   ├── arxiv_date_resolver.py
│   │   ├── duplicate_detector.py
│   │   ├── search_service.py
│   │   ├── notion_importer.py
│   │   └── normalization.py
│   ├── ui/
│   │   ├── list_page.py
│   │   ├── detail_page.py
│   │   ├── import_page.py
│   │   ├── export_page.py
│   │   └── notion_page.py
│   └── utils/
│       ├── dates.py
│       ├── strings.py
│       └── authors.py
└── tests/
    ├── test_arxiv_date_resolver.py
    ├── test_bibtex_parser.py
    ├── test_duplicate_detector.py
    ├── test_search_service.py
    └── test_exporter.py
```

## 実装フェーズ

### Phase 1: 基盤

- SQLite 初期化
- SQLAlchemy モデル
- DDL 作成
-　最小 CRUD

### Phase 2: BibTeX import

- 単一エントリ貼り付け
- `.bib`一括読み込み
- 正規化
- arXiv 年月解決
- 重複警告

### Phase 3: 一覧・詳細UI

- 文献一覧
- フィルタ
- ソート
- 詳細編集
- tags / keywords / read status / notes 編集

### Phase 4: BibTeX エクスポート

- 全件エクスポート
- 正規化済み出力

### Phase 5: Notion 移行

- CSV マッピング
- インポート
