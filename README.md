# 起動

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py

# 機能

- BibTeX 単件登録
- bib 一括インポート
- tags / keywords / notes / read status 管理
- arXiv ベースの yyyymm ソート
- 正規化 BibTeX エクスポート
