"""
BibManager – Flask backend
Run:  python app.py
Then open http://localhost:5000 in your browser.
"""

import json
import io
import sqlite3
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file

import database as db
from bib_parser import parse_bib_string, import_entries_to_db
from notion_import import import_notion_csv

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32 MB upload limit


# ---------------------------------------------------------------------------
# Initialise DB on startup
# ---------------------------------------------------------------------------

db.init_db()


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html')


# ---------------------------------------------------------------------------
# Entries
# ---------------------------------------------------------------------------

@app.route('/api/entries')
def api_entries():
    q        = request.args.get('q', '').strip()
    tag_ids  = [int(x) for x in request.args.getlist('tag') if x.isdigit()]
    kw_ids   = [int(x) for x in request.args.getlist('kw') if x.isdigit()]
    year_from = _safe_int(request.args.get('year_from'))
    year_to   = _safe_int(request.args.get('year_to'))
    limit  = min(int(request.args.get('limit', 2000)), 2000)
    offset = int(request.args.get('offset', 0))

    rows, total = db.search_entries(
        q=q, tag_ids=tag_ids, kw_ids=kw_ids,
        year_from=year_from, year_to=year_to,
        limit=limit, offset=offset,
    )
    return jsonify({'entries': rows, 'total': total, 'limit': limit, 'offset': offset})


@app.route('/api/entries', methods=['POST'])
def api_create_entry():
    fields = request.get_json(force=True)
    try:
        entry = db.create_entry(fields)
        return jsonify(entry), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/parse-bibtex', methods=['POST'])
def api_parse_bibtex():
    """Parse a raw BibTeX string and return structured fields."""
    data = request.get_json(force=True)
    bib_text = data.get('bibtex', '')
    entries = parse_bib_string(bib_text)
    if not entries:
        return jsonify({'error': 'BibTeX を解析できませんでした'}), 400
    e = entries[0]
    from bib_parser import split_authors
    return jsonify({
        'cite_key':   e.get('cite_key', ''),
        'entry_type': e.get('entry_type', 'article'),
        'title':      e.get('title', ''),
        'author':     e.get('author', ''),
        'year':       e.get('year', ''),
        'month':      e.get('month', ''),
        'journal':    e.get('journal') or e.get('booktitle') or e.get('school') or '',
        'volume':     e.get('volume', ''),
        'number':     e.get('number', ''),
        'pages':      e.get('pages', ''),
        'doi':        e.get('doi', ''),
        'url':        e.get('url', ''),
        'eprint':     e.get('eprint', ''),
        'abstract':   e.get('abstract', ''),
    })


@app.route('/api/entries/<int:entry_id>')
def api_entry(entry_id):
    entry = db.get_entry(entry_id)
    if entry is None:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(entry)


@app.route('/api/entries/<int:entry_id>', methods=['PATCH'])
def api_update_entry(entry_id):
    data = request.get_json(force=True)

    if 'tags' in data:
        db.set_entry_tags(entry_id, data['tags'])

    if 'keywords' in data:
        db.set_entry_keywords(entry_id, data['keywords'])

    if 'reading_note' in data:
        db.set_reading_note(entry_id, data['reading_note'])

    # Bibliographic meta fields
    meta_keys = ('cite_key', 'entry_type', 'title', 'author', 'year', 'month',
                 'journal', 'volume', 'number', 'pages', 'doi', 'url', 'eprint', 'abstract')
    meta = {k: data[k] for k in meta_keys if k in data}
    if meta:
        updated = db.update_entry_meta(entry_id, meta)
        if updated is None:
            return jsonify({'error': 'Not found'}), 404
        return jsonify(updated)

    return jsonify({'ok': True})


@app.route('/api/entries/<int:entry_id>', methods=['DELETE'])
def api_delete_entry(entry_id):
    db.delete_entry(entry_id)
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------

@app.route('/api/duplicates')
def api_duplicates():
    groups = db.find_duplicates()
    return jsonify(groups)


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

@app.route('/api/tags')
def api_tags():
    return jsonify(db.get_all_tags())


@app.route('/api/tags', methods=['POST'])
def api_create_tag():
    data = request.get_json(force=True)
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'name required'}), 400
    tag_id = db.get_or_create_tag(name)
    return jsonify({'id': tag_id, 'name': name})


@app.route('/api/tags/<int:tag_id>', methods=['DELETE'])
def api_delete_tag(tag_id):
    db.delete_tag(tag_id)
    return jsonify({'ok': True})


@app.route('/api/tags/<int:tag_id>', methods=['PATCH'])
def api_rename_tag(tag_id):
    data = request.get_json(force=True)
    new_name = data.get('name', '').strip()
    if not new_name:
        return jsonify({'error': 'name required'}), 400
    db.rename_tag(tag_id, new_name)
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------

@app.route('/api/keywords')
def api_keywords():
    return jsonify(db.get_all_keywords())


@app.route('/api/keywords', methods=['POST'])
def api_create_keyword():
    data = request.get_json(force=True)
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'name required'}), 400
    kw_id = db.get_or_create_keyword(name)
    return jsonify({'id': kw_id, 'name': name})


@app.route('/api/keywords/<int:kw_id>', methods=['DELETE'])
def api_delete_keyword(kw_id):
    db.delete_keyword(kw_id)
    return jsonify({'ok': True})


@app.route('/api/keywords/<int:kw_id>', methods=['PATCH'])
def api_rename_keyword(kw_id):
    data = request.get_json(force=True)
    new_name = data.get('name', '').strip()
    if not new_name:
        return jsonify({'error': 'name required'}), 400
    db.rename_keyword(kw_id, new_name)
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Citations in other papers
# ---------------------------------------------------------------------------

@app.route('/api/entries/<int:entry_id>/citations', methods=['POST'])
def api_add_citation(entry_id):
    data = request.get_json(force=True)
    cit_id = db.add_citation(
        entry_id,
        data.get('source_cite_key', ''),
        data.get('source_title', ''),
        data.get('content', ''),
    )
    return jsonify({'id': cit_id})


@app.route('/api/citations/<int:cit_id>', methods=['PATCH'])
def api_update_citation(cit_id):
    data = request.get_json(force=True)
    db.update_citation(
        cit_id,
        data.get('source_cite_key', ''),
        data.get('source_title', ''),
        data.get('content', ''),
    )
    return jsonify({'ok': True})


@app.route('/api/citations/<int:cit_id>', methods=['DELETE'])
def api_delete_citation(cit_id):
    db.delete_citation(cit_id)
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Import (.bib)
# ---------------------------------------------------------------------------

@app.route('/api/import', methods=['POST'])
def api_import():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    f = request.files['file']
    text = f.read().decode('utf-8', errors='replace')
    entries = parse_bib_string(text)
    conn = db.get_conn()
    try:
        summary = import_entries_to_db(entries, conn)
        conn.commit()
    finally:
        conn.close()
    return jsonify(summary)


# ---------------------------------------------------------------------------
# Import (Notion CSV)
# ---------------------------------------------------------------------------

@app.route('/api/notion-import', methods=['POST'])
def api_notion_import():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    f = request.files['file']
    text = f.read().decode('utf-8', errors='replace')
    summary = import_notion_csv(text)
    return jsonify(summary)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@app.route('/api/export')
def api_export():
    bib_text = db.export_all_bibtex()
    buf = io.BytesIO(bib_text.encode('utf-8'))
    buf.seek(0)
    return send_file(buf, mimetype='text/plain',
                     as_attachment=True, download_name='exported.bib')


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@app.route('/api/stats')
def api_stats():
    return jsonify(db.get_stats())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_int(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    print("=" * 50)
    print("  BibManager")
    print(f"  http://localhost:{port}")
    print("=" * 50)
    app.run(debug=True, port=port)
