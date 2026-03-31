# 文献整理ツール DBスキーマ設計書 v1.1

## 1. 目的

本設計書は、文献整理ツール第1版において必要なデータ構造を定義する。
主目的は以下である。

- BibTeX 由来の書誌情報を安定に保持する
- タグ、キーワード、読了状態、ノートを柔軟に管理する
- 著者検索・タグ検索・年範囲検索・ノート検索を行う
- 一覧画面で用いる yyyymm を、可能な限り arXiv 初回投稿年月 に一致させる
- 旧式 arXiv 番号については、yy のみで世紀を決めず、BibTeX の year も参照して保守的に推定 する
- 正規化済み BibTeX を再生成可能にする
- 将来の文献間リンクや箇条書きノート等へ拡張可能にする

第1版では SQLite を前提とする。

⸻

## 2. 設計方針

### 2.1 基本方針

- app DB を正本とする
- BibTeX はインポート元・エクスポート先として扱う
- 文献本体は papers テーブルに置く
- 著者、タグ、キーワードは独立テーブル化する
- 多対多関係は中間テーブルで持つ
- notes は第1版では papers に長文欄として保持する
- raw BibTeX は本番DBには保存しない

## 2.2 年月の設計方針

本ツールでは年月には少なくとも以下の二種類がある。

- 出版年月: BibTeX の year, month
- 一覧表示年月: 一覧画面・標準ソートに使う yyyymm

一覧表示年月は、原則として arXiv 初回投稿年月 を用いる。
ただし旧式 arXiv 番号の yy だけでは世紀が一意に定まらないため、以下のように扱う。

- 新形式 arXiv (YYMM.NNNNN) は機械的に年月抽出可能
- 旧形式 arXiv (archive/YYMMNNN など) は YYMM を抽出するが、YY の世紀決定は BibTeX の出版年と照合 して行う
- arXiv が存在しない文献では出版年月を一覧表示年月の代替とする

従って、DB上では出版年月と一覧表示年月を明確に分離する。

## 2.3 保守方針

- 自動推定された arXiv 年月には、推定由来と確信度を保持する
- 一覧表示年月の計算根拠を残し、将来再計算可能にする
- 旧式番号の世紀判定はアプリロジックで行い、DBには結果と由来を保存する

## 3. エンティティ一覧

第1版で必要な主要エンティティは以下。

- papers
- authors
- paper_authors
- tags
- paper_tags
- keywords
- paper_keywords

将来拡張候補:

- paper_links
- note_items
- import_logs
- paper_date_audit
- bibtex_extra_fields

## 4. テーブル定義

### 4.1 papers

文献本体を保持する主テーブル。

カラム

- id INTEGER PRIMARY KEY
- citation_key TEXT NOT NULL UNIQUE
- entry_type TEXT NOT NULL
- title TEXT NOT NULL
- title_sort TEXT

出版書誌情報

- published_year INTEGER
- published_month INTEGER NOT NULL DEFAULT 0
- journal TEXT
- booktitle TEXT
- publisher TEXT
- series TEXT
- volume TEXT
- number TEXT
- issue TEXT
- pages TEXT
- doi TEXT
- url TEXT

arXiv 関連

- archive_prefix TEXT
- eprint TEXT
- primary_class TEXT
- arxiv_id_normalized TEXT
- arxiv_category TEXT
- arxiv_yy INTEGER
- arxiv_mm INTEGER
- arxiv_year_resolved INTEGER
- arxiv_month_resolved INTEGER
- arxiv_yymm_resolved INTEGER
- arxiv_date_resolution_method TEXT
- arxiv_date_resolution_confidence TEXT

一覧表示・ソート用

- display_year INTEGER
- display_month INTEGER NOT NULL DEFAULT 0
- display_yymm INTEGER NOT NULL
- display_date_source TEXT NOT NULL

補助情報

- abstract TEXT
- pdf_path TEXT
- primary_notes TEXT NOT NULL DEFAULT ''
- secondary_notes TEXT NOT NULL DEFAULT ''
- read_status TEXT NOT NULL DEFAULT 'Not started'
- created_at TEXT NOT NULL
- updated_at TEXT NOT NULL

### 4.2 各カラムの意味

published_year, published_month

- BibTeX の year, month に対応する出版年月
- month 不明は 0
- 書籍・雑誌・会議録などに対する正式書誌年月

archive_prefix, eprint, primary_class

- BibTeX の arXiv 関連フィールド
- 出力時には archivePrefix, eprint, primaryClass に戻す

arxiv_id_normalized

- 正規化済み arXiv ID
- 例: 2603.19189, 2603.19189v1 → 正規化して 2603.19189, cond-mat/0507008
- バージョン番号は落としてよい

arxiv_category

- 旧形式 arXiv のカテゴリ部分
- 例: cond-mat, quant-ph
- 新形式では NULL 可

arxiv_yy, arxiv_mm

- eprint から抽出した生の yy, mm
- 旧形式・新形式いずれも、取得できる場合に保持
- 例: cond-mat/0507008 → yy=5, mm=7; 2603.19189 → yy=26, mm=3

arxiv_year_resolved, arxiv_month_resolved

- 世紀解決後の arXiv 初回投稿年月
- year は4桁、month は 1〜12

arxiv_yymm_resolved

- arxiv_year_resolved × 100 + arxiv_month_resolved

arxiv_date_resolution_method

- arXiv 年月の解決方法: new_style_direct, old_style_with_published_year, old_style_with_manual_override, not_applicable

arxiv_date_resolution_confidence

- 推定の確信度: high, medium, manual, none

display_year, display_month, display_yymm

- 一覧画面・標準ソートに用いる年月
- arXiv 年月があればそれを使う、なければ出版年月を使う
- month 不明は 0

display_date_source

- 一覧表示年月の由来: arxiv, published, manual

### 4.3 arXiv 年月解決ルール

これは DB カラムではなく、アプリロジックとして実装するべき規則である。

#### 4.3.1 新形式 arXiv

新形式 arXiv (YYMM.NNNNN / YYMM.NNNN / YYMM.NNNNNvK)

形式:

- YYMM.NNNNN
- YYMM.NNNN
- YYMM.NNNNNvK (v1, v2, ... などのバージョン番号は無視)

処理:

- YY, MM を直接読む
- 世紀は原則 20YY
- バージョン情報があれば削除

例:

- 2603.19189 → 2026-03
- 2603.19189v1 → 2026-03 (v1 を無視)
- 0507.1234 → 2005-07

結果:

- arxiv_date_resolution_method = 'new_style_direct'
- arxiv_date_resolution_confidence = 'high'

#### 4.3.2 旧形式 arXiv

形式:
 • archive/YYMMNNN
 • archive/YYMMNNNN

処理:
 • YY, MM を抽出する
 • 世紀は published_year を参照して解決する
 • 解決規則の推奨は以下:

解決規則
候補年を
 • 1900 + YY
 • 2000 + YY

の2つ作る。

そのうち、
 • published_year が存在し、かつ
 • candidate_year <= published_year
 • さらに published_year - candidate_year が現実的範囲（例えば 0〜20 年程度）

を満たす候補を優先する。

通常は:
 • 1931 論文に 31xx 型の旧式 arXiv は存在しないので、誤認識を避ける
 • 0507008 なら 2005-07 が自然
 • 9811052 なら 1998-11 が自然

#### 4.3.3 解決不能時

 • arxiv_year_resolved, arxiv_month_resolved, arxiv_yymm_resolved は NULL
 • arxiv_date_resolution_method = 'not_applicable'
 • arxiv_date_resolution_confidence = 'none'

#### 4.3.4 手動修正

将来拡張を見込み、アプリ側で手動修正可能にしてよい。
その場合:
 • arxiv_date_resolution_method = 'old_style_with_manual_override'
 • arxiv_date_resolution_confidence = 'manual'

### 4.4 一覧表示年月の計算規則

display_yymm は次の規則で決める。

 1. arxiv_yymm_resolved が存在すればそれを採用
 2. なければ published_year, published_month を採用
 3. どちらも不完全なら、既知部分のみで埋める
 • 例: 出版年のみ既知なら YYYY00

display_date_source は以下の通り。
 • arxiv_yymm_resolved 使用時 → arxiv
 • 出版年月使用時 → published
 • 将来の手動修正時 → manual

### 4.5 制約

published_month
 • published_month BETWEEN 0 AND 12

arxiv_mm
 • NULL または 1 <= arxiv_mm <= 12

arxiv_month_resolved
 • NULL または 1 <= arxiv_month_resolved <= 12

display_month
 • display_month BETWEEN 0 AND 12

read_status
 • read_status IN ('Not started','Only abstract','Skimmed','In progress','Done')

### 4.6 インデックス

 • INDEX idx_papers_display_yymm ON papers(display_yymm)
 • INDEX idx_papers_published_year ON papers(published_year)
 • INDEX idx_papers_title_sort ON papers(title_sort)
 • INDEX idx_papers_read_status ON papers(read_status)
 • INDEX idx_papers_arxiv_id_normalized ON papers(arxiv_id_normalized)
 • INDEX idx_papers_display_date_source ON papers(display_date_source)

### 4.7 authors

著者マスタ。

カラム
 • id INTEGER PRIMARY KEY
 • display_name TEXT NOT NULL
 • normalized_name TEXT NOT NULL
 • family_name TEXT
 • given_name TEXT

説明
 • display_name: 表示用
 • normalized_name: 検索用
 • family_name: 抽出できる場合のみ
 • given_name: 抽出できる場合のみ

制約
 • UNIQUE(display_name, normalized_name)

インデックス
 • INDEX idx_authors_normalized_name ON authors(normalized_name)
 • INDEX idx_authors_family_name ON authors(family_name)

### 4.8 paper_authors

文献と著者の対応、および著者順序を管理する。

カラム
 • paper_id INTEGER NOT NULL
 • author_id INTEGER NOT NULL
 • author_order INTEGER NOT NULL

主キー
 • PRIMARY KEY (paper_id, author_order)

外部キー
 • paper_id REFERENCES papers(id) ON DELETE CASCADE
 • author_id REFERENCES authors(id) ON DELETE RESTRICT

インデックス
 • INDEX idx_paper_authors_author_id ON paper_authors(author_id)
 • INDEX idx_paper_authors_paper_id ON paper_authors(paper_id)

### 4.9 tags

タグマスタ。

カラム
 • id INTEGER PRIMARY KEY
 • name TEXT NOT NULL UNIQUE
 • name_normalized TEXT NOT NULL UNIQUE
 • created_at TEXT NOT NULL

インデックス
 • INDEX idx_tags_name_normalized ON tags(name_normalized)

### 4.10 paper_tags

文献とタグの対応。

カラム
 • paper_id INTEGER NOT NULL
 • tag_id INTEGER NOT NULL

主キー
 • PRIMARY KEY (paper_id, tag_id)

外部キー
 • paper_id REFERENCES papers(id) ON DELETE CASCADE
 • tag_id REFERENCES tags(id) ON DELETE RESTRICT

インデックス
 • INDEX idx_paper_tags_tag_id ON paper_tags(tag_id)

### 4.11 keywords

キーワードマスタ。

カラム
 • id INTEGER PRIMARY KEY
 • name TEXT NOT NULL UNIQUE
 • name_normalized TEXT NOT NULL UNIQUE
 • created_at TEXT NOT NULL

インデックス
 • INDEX idx_keywords_name_normalized ON keywords(name_normalized)

### 4.12 paper_keywords

文献とキーワードの対応。

カラム
 • paper_id INTEGER NOT NULL
 • keyword_id INTEGER NOT NULL

主キー
 • PRIMARY KEY (paper_id, keyword_id)

外部キー
 • paper_id REFERENCES papers(id) ON DELETE CASCADE
 • keyword_id REFERENCES keywords(id) ON DELETE RESTRICT

インデックス
 • INDEX idx_paper_keywords_keyword_id ON paper_keywords(keyword_id)

## 5. 列挙値仕様

### 5.1 read_status

以下の5値に限定する。
 • Not started
 • Only abstract
 • Skimmed
 • In progress
 • Done

内部順序

 1. Not started
 2. Only abstract
 3. Skimmed
 4. In progress
 5. Done

### 5.2 display_date_source

 • arxiv
 • published
 • manual

### 5.3 arxiv_date_resolution_method

 • new_style_direct
 • old_style_with_published_year
 • old_style_with_manual_override
 • not_applicable

### 5.4 arxiv_date_resolution_confidence

 • high
 • medium
 • manual
 • none

## 6. 正規化ルール

### 6.1 title_sort

検索用の正規化タイトル。
 • 前後空白除去
 • 連続空白圧縮
 • 小文字化
 • 必要なら一部記号除去

### 6.2 normalized_name

著者検索用。
 • 小文字化
 • 前後空白除去
 • 連続空白圧縮
 • 句読点や余分な記号を軽く除去

### 6.3 name_normalized

タグ・キーワード用。
 • 小文字化
 • 前後空白除去
 • 連続空白圧縮

### 6.4 arxiv_id_normalized

 • v1, v2 などの版番号を落とす
 • 大文字小文字揺れを正規化
 • 空白を除去

⸻

## 7. BibTeX 再構成方針

BibTeX 出力では 出版書誌情報 を用いる。
一覧表示年月に使う display_yymm は BibTeX の year, month には出力しない。

### 7.1 出力対象主要フィールド

 • entry type
 • citation key
 • author
 • title
 • journal / booktitle / publisher
 • year ← published_year
 • month ← published_month
 • volume
 • number
 • issue
 • pages
 • doi
 • url
 • archivePrefix ← archive_prefix
 • eprint
 • primaryClass ← primary_class
 • abstract
 • series

### 7.2 month

 • 内部表現は整数 0〜12
 • BibTeX 出力時は published_month = 0 なら month を出さない
 • 1〜12 の場合のみ出力

## 8. 検索クエリ設計上の注意

### 8.1 一覧表示

一覧には以下が必要。
 • display_yymm
 • authors_display
 • title
 • tags_display
 • keywords_display
 • read_status
 • primary_notes
 • secondary_notes
 • display_date_source

これを毎回組み立てるより、表示用 View を用意するのが望ましい。

推奨 View: paper_list_view

含める列:
 • paper_id
 • citation_key
 • display_yymm
 • display_date_source
 • authors_display
 • title
 • tags_display
 • keywords_display
 • read_status
 • primary_notes
 • secondary_notes
 • updated_at

### 8.2 タグ複数指定検索

AND 条件を満たす必要があるので GROUP BY ... HAVING COUNT(DISTINCT tag_id) = N を使う。

### 8.3 年範囲検索

一覧の年月基準で絞る場合は
 • display_yymm BETWEEN ... AND ...

出版年で絞る場合は
 • published_year BETWEEN ... AND ...

を使い分けられるようにする。

## 9. 将来拡張の余地

### 9.1 年月監査テーブル

推定ロジックの追跡を厳密にしたくなった場合は、次を追加可能。

paper_date_audit
 • id
 • paper_id
 • source_type
 • raw_value
 • resolved_year
 • resolved_month
 • method
 • confidence
 • note
 • created_at

ただし v1 では必須ではない。

### 9.2 文献間リンク

paper_links
 • id
 • source_paper_id
 • target_paper_id
 • link_type
 • note

### 9.3 箇条書きノート

note_items
 • id
 • paper_id
 • note_type
 • content
 • sort_order
 • linked_paper_id NULLABLE

## 10. SQLite DDL 叩き台

```sql
CREATE TABLE papers (
  id INTEGER PRIMARY KEY,
  citation_key TEXT NOT NULL UNIQUE,
  entry_type TEXT NOT NULL,
  title TEXT NOT NULL,
  title_sort TEXT,

  published_year INTEGER,
  published_month INTEGER NOT NULL DEFAULT 0 CHECK (published_month BETWEEN 0 AND 12),

  journal TEXT,
  booktitle TEXT,
  publisher TEXT,
  series TEXT,
  volume TEXT,
  number TEXT,
  issue TEXT,
  pages TEXT,
  doi TEXT,
  url TEXT,

  archive_prefix TEXT,
  eprint TEXT,
  primary_class TEXT,
  arxiv_id_normalized TEXT,
  arxiv_category TEXT,
  arxiv_yy INTEGER,
  arxiv_mm INTEGER CHECK (arxiv_mm IS NULL OR (arxiv_mm BETWEEN 1 AND 12)),
  arxiv_year_resolved INTEGER,
  arxiv_month_resolved INTEGER CHECK (arxiv_month_resolved IS NULL OR (arxiv_month_resolved BETWEEN 1 AND 12)),
  arxiv_yymm_resolved INTEGER,
  arxiv_date_resolution_method TEXT NOT NULL DEFAULT 'not_applicable'
    CHECK (arxiv_date_resolution_method IN (
      'new_style_direct',
      'old_style_with_published_year',
      'old_style_with_manual_override',
      'not_applicable'
    )),
  arxiv_date_resolution_confidence TEXT NOT NULL DEFAULT 'none'
    CHECK (arxiv_date_resolution_confidence IN ('high','medium','manual','none')),

  display_year INTEGER,
  display_month INTEGER NOT NULL DEFAULT 0 CHECK (display_month BETWEEN 0 AND 12),
  display_yymm INTEGER NOT NULL,
  display_date_source TEXT NOT NULL
    CHECK (display_date_source IN ('arxiv','published','manual')),

  abstract TEXT,
  pdf_path TEXT,
  primary_notes TEXT NOT NULL DEFAULT '',
  secondary_notes TEXT NOT NULL DEFAULT '',
  read_status TEXT NOT NULL DEFAULT 'Not started'
    CHECK (read_status IN ('Not started','Only abstract','Skimmed','In progress','Done')),

  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE authors (
  id INTEGER PRIMARY KEY,
  display_name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  family_name TEXT,
  given_name TEXT,
  UNIQUE(display_name, normalized_name)
);

CREATE TABLE paper_authors (
  paper_id INTEGER NOT NULL,
  author_id INTEGER NOT NULL,
  author_order INTEGER NOT NULL,
  PRIMARY KEY (paper_id, author_order),
  UNIQUE (paper_id, author_id, author_order),
  FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
  FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE RESTRICT
);

CREATE TABLE tags (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  name_normalized TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);

CREATE TABLE paper_tags (
  paper_id INTEGER NOT NULL,
  tag_id INTEGER NOT NULL,
  PRIMARY KEY (paper_id, tag_id),
  FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
  FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE RESTRICT
);

CREATE TABLE keywords (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  name_normalized TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);

CREATE TABLE paper_keywords (
  paper_id INTEGER NOT NULL,
  keyword_id INTEGER NOT NULL,
  PRIMARY KEY (paper_id, keyword_id),
  FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
  FOREIGN KEY (keyword_id) REFERENCES keywords(id) ON DELETE RESTRICT
);

CREATE INDEX idx_papers_display_yymm ON papers(display_yymm);
CREATE INDEX idx_papers_published_year ON papers(published_year);
CREATE INDEX idx_papers_title_sort ON papers(title_sort);
CREATE INDEX idx_papers_read_status ON papers(read_status);
CREATE INDEX idx_papers_arxiv_id_normalized ON papers(arxiv_id_normalized);
CREATE INDEX idx_papers_display_date_source ON papers(display_date_source);

CREATE INDEX idx_authors_normalized_name ON authors(normalized_name);
CREATE INDEX idx_authors_family_name ON authors(family_name);

CREATE INDEX idx_paper_authors_author_id ON paper_authors(author_id);
CREATE INDEX idx_paper_authors_paper_id ON paper_authors(paper_id);

CREATE INDEX idx_tags_name_normalized ON tags(name_normalized);
CREATE INDEX idx_paper_tags_tag_id ON paper_tags(tag_id);

CREATE INDEX idx_keywords_name_normalized ON keywords(name_normalized);
CREATE INDEX idx_paper_keywords_keyword_id ON paper_keywords(keyword_id);
```
