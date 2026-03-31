# 文献整理ツール 画面仕様書 v1.1

## 1. 目的

本仕様書は、第1版の UI 構成、画面要素、主要操作、状態遷移を定義する。
第1版では以下を重視する。
 • 一覧画面中心で日常運用できること
 • 文献詳細でノートをしっかり書けること
 • BibTeX 貼り付け登録が容易であること
 • 一覧画面の yyyymm が、可能な限り arXiv 初回投稿年月 を反映すること
 • 旧式 arXiv 番号の年月解決が曖昧な場合でも、後から根拠を追えること

⸻

## 2. 画面一覧

第1版で必要な画面は以下。

 1. 文献一覧画面
 2. 文献詳細画面
 3. 新規登録画面
 4. 一括インポート画面
 5. タグ/キーワード管理補助 UI
 6. Notion 移行画面
 7. エクスポート画面

⸻

## 3. 画面遷移概要
 • 起動時 → 文献一覧画面
 • 一覧で文献選択 → 文献詳細画面
 • 一覧で「新規追加」 → 新規登録画面
 • 一覧で「一括インポート」 → 一括インポート画面
 • 一覧または詳細で「エクスポート」 → エクスポート画面
 • メニューから → Notion 移行画面

⸻

## 4. 文献一覧画面

### 4.1 目的

 • 文献全体を俯瞰する
 • 著者、タグ、キーワード、年範囲で絞る
 • notes を一覧で直接確認する
 • 日常利用の中心画面とする
 • 研究時系列を arXiv 初回投稿ベース で把握する

⸻

### 4.2 主要領域

 1. ヘッダバー
 2. 検索・絞り込みパネル
 3. 文献リスト本体
 4. 補助情報表示

⸻

### 4.3 ヘッダバー

要素
 • アプリ名
 • 新規追加ボタン
 • 一括インポートボタン
 • エクスポートボタン
 • Notion 移行ボタン
 • 設定ボタン（任意）

⸻

### 4.4 検索・絞り込みパネル

必須項目
 • 著者検索入力
 • タイトル検索入力
 • notes 検索入力
 • タグ複数選択
 • キーワード複数選択
 • 年月 from
 • 年月 to
 • read status フィルタ
 • ソート順切替

年月フィルタの意味

第1版では、一覧ソートと整合するため display_yymm を基準とする。
つまり、原則として arXiv 初回投稿年月で絞る。
arXiv がない文献では出版年月が使われる。

将来拡張

将来的には
 • display_yymm 基準
 • published_year/month 基準
を切り替え可能にしてよいが、v1 では不要。

ソート UI
 • display_yymm desc
 • display_yymm asc

二次ソートは内部で authors asc 固定

⸻

### 4.5 文献リスト本体

#### 4.5.1 表示形式

 • テーブル風またはカード風の可変高さリスト
 • 行ごとに1文献
 • notes が全文表示されるため固定行高は採用しない

#### 4.5.2 常時表示項目

 • yyyymm
 • authors
 • title
 • tags
 • keywords
 • read status
 • primary notes
 • secondary notes

補助表示
 • 必要に応じて date source を小さく表示できる
 • arXiv
 • published

これはデバッグ用・保守用として有用である。

⸻

#### 4.5.3 各列仕様

yyyymm
 • 表示値は display_yymm
 • 原則として arXiv 初回投稿年月
 • arXiv がなければ出版年月
 • month 不明は 00

yyyymm の補助表示

必要に応じて、yyyymm の横または下に小さく由来を表示する。
 • arXiv
 • published

第1版では常時表示必須ではないが、詳細画面では必ず確認できるようにする。

authors
 • 著者順に連結表示
 • 区切りは ,
 • 長い場合は折り返し可

title
 • 48文字程度で省略表示
 • 超過時は …

tags
 • チップまたはカンマ区切り表示

keywords
 • チップまたはカンマ区切り表示

read status
 • 5状態のいずれかを表示

primary notes / secondary notes
 • 省略せず全文表示
 • セル内折り返し
 • 改行保持

⸻

## 4.6 一覧画面の操作

行クリック
 • 文献詳細画面へ遷移

行メニュー
 • 編集
 • 削除（任意）
 • BibTeXコピー（任意）

ソート切替
 • display_yymm 昇順 / 降順

⸻

## 5. 文献詳細画面

### 5.1 目的

 • 1件の文献を集中して読む/編集する
 • notes を記述する
 • BibTeX と PDF path を確認する
 • 一覧年月の由来を明示的に確認する

⸻

### 5.2 表示順

 1. authors
 2. display yymm
 3. published yymm
 4. title
 5. tags
 6. keywords
 7. primary notes
 8. secondary notes
 9. read status
 10. normalized BibTeX
 11. PDF path
 12. arXiv metadata

⸻

### 5.3 各領域仕様

基本情報領域

表示項目:
 • authors
 • title
 • entry type
 • citation key

年月領域

表示項目:
 • display yymm
 • display date source
 • published year/month
 • arXiv normalized id
 • arxiv_year_resolved / arxiv_month_resolved
 • arxiv_date_resolution_method
 • arxiv_date_resolution_confidence

意図

一覧に出ている年月が
 • arXiv 由来なのか
 • 出版由来なのか
 • どう解決されたのか
を後から追跡可能にする。

分類領域
 • tags
 • keywords
 • read status

notes 領域
 • primary notes: 大きめテキストエリア
 • secondary notes: 大きめテキストエリア

BibTeX 領域
 • 正規化 BibTeX を表示
 • コピーボタンがあると望ましい

PDF path 領域
 • 文字列表示
 • 編集可能
 • 開くボタンは不要

⸻

### 5.4 詳細画面の操作

 • 保存
 • 戻る
 • BibTeX コピー
 • 必要なら arXiv 年月の手動修正（将来拡張候補）

第1版では、手動修正 UI は必須ではないが、内部構造上は後から追加可能にしておく。

⸻

## 6. 新規登録画面

### 6.1 目的

 • BibTeX 貼り付けから新規文献を登録する
 • arXiv 年月の自動解釈結果を確認する

### 6.2 要素

 • BibTeX 入力テキストエリア
 • パース結果プレビュー領域
 • 重複候補警告領域
 • 年月解釈プレビュー領域
 • 登録ボタン
 • キャンセルボタン

### 6.3 パース結果プレビュー

表示項目:
 • citation key
 • title
 • authors
 • published year/month
 • eprint
 • normalized arXiv ID
 • resolved arXiv yymm
 • display yymm
 • display date source

意図

登録前に、
 • どの yyyymm が一覧に出るか
 • 旧式 arXiv 番号がどう解釈されたか
を確認できるようにする。

### 6.4 重複警告

 • title + first author + year 類似で候補を表示
 • 自動拒否はしない

⸻

## 7. 一括インポート画面

### 7.1 目的

 • .bib ファイルをまとめて取り込む
 • arXiv 年月の自動解釈をまとめて確認する

### 7.2 要素

 • ファイル選択
 • 取り込み件数表示
 • エラー件数表示
 • 重複候補一覧
 • 年月解釈警告一覧
 • 実行ボタン

### 7.3 年月解釈警告一覧

次のようなケースを警告対象にすると望ましい。
 • 旧式 arXiv で published_year と照合しても解釈が不自然
 • eprint はあるが年月抽出に失敗
 • display_yymm が出版年月にフォールバックした

第1版では警告表示のみでも十分。

⸻

## 8. タグ/キーワード入力 UI

### 8.1 要求

 • 複数選択
 • 新規追加可能
 • 既存候補から選択可能

### 8.2 推奨 UI

 • トークン入力型
 • サジェスト付き
 • Enter で新規追加

⸻

## 9. Notion移行画面

### 9.1 目的

 • 一回限りのデータ移行

### 9.2 要素

 • CSV ファイル選択
 • 列マッピング設定
 • プレビュー
 • 取り込み実行

### 9.3 マッピング候補

 • タイトル
 • 著者
 • タグ
 • キーワード
 • primary notes
 • secondary notes
 • BibTeX 情報
 • arXiv 掲載年月

注意

Notion 側の「arXiv掲載年月」がある場合、それを内部の display_yymm 候補として参照する将来拡張はありうるが、第1版では BibTeX/eprint 由来を優先してよい。

⸻

## 10. エクスポート画面

### 10.1 目的

 • 正規化 BibTeX をファイル出力する

### 10.2 要素

 • 出力先選択
 • 全件出力 / 絞り込み結果のみ出力（任意）
 • 実行ボタン

注

第1版では全件出力のみでもよい。

⸻

## 11. 共通 UI ルール

### 11.1 保存タイミング

 • 第1版は 明示保存ボタン方式 を推奨

### 11.2 バリデーション

 • citation key 空欄不可
 • title 空欄不可
 • published_month は 00〜12
 • read status は定義済み値のみ
 • display_yymm は内部で必ず埋まること

### 11.3 エラーメッセージ

 • BibTeX パース失敗
 • citation key 重複
 • 必須項目不足
 • 不正な month
 • arXiv 年月解決失敗（警告）

⸻

## 12. 一覧表示用 View の推奨

paper_list_view

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

⸻

## 13. MVP 優先順位

最優先
 • 文献一覧画面
 • 文献詳細画面
 • BibTeX 貼り付け登録
 • .bib 一括インポート
 • タグ/キーワード/notes/read status 編集
 • display_yymm ベースのソート
 • BibTeX エクスポート

次点
 • 新規登録時の年月解釈プレビュー
 • 一括インポート時の年月警告
 • display_date_source の補助表示

後回し可
 • arXiv 年月手動修正 UI
 • 高度なインライン編集
 • FTS 最適化

⸻

## 14. 実装上の補足

一覧で notes を全文表示するため、描画コストが上がる。
さらに可変高さリストになるため、以下のいずれかを見込むべき。
 • 仮想スクロール
 • ページネーション
 • 遅延レンダリング

また、年月解釈ロジックはアプリ内に独立した関数として実装し、次の入出力を持たせるべきである。

推奨関数インターフェース

入力:
 • eprint
 • archive_prefix
 • published_year

出力:
 • arxiv_id_normalized
 • arxiv_category
 • arxiv_yy
 • arxiv_mm
 • arxiv_year_resolved
 • arxiv_month_resolved
 • arxiv_yymm_resolved
 • arxiv_date_resolution_method
 • arxiv_date_resolution_confidence

こうしておくと、将来的に解釈規則を変えてもDB全体を再計算しやすい。
