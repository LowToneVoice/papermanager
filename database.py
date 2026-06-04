"""
SQLite database setup and CRUD operations for BibManager.
"""

import os
import sqlite3
from pathlib import Path

# DB path can be overridden via environment variable PAPERMANAGER_DB.
# Default: bibmanager.db in the same directory as this file.
#   Personal use (git-tracked DB):  python app.py
#   Others (own fresh DB):          PAPERMANAGER_DB=mydb.db python app.py
DB_PATH = Path(os.environ.get("PAPERMANAGER_DB", Path(__file__).parent / "bibmanager.db"))


def _open_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_conn() -> sqlite3.Connection:
    """Return the per-request shared connection (via Flask g).
    Falls back to a direct connection when called outside request context
    (e.g. init_db at startup).
    """
    try:
        from flask import g
        if not hasattr(g, '_db'):
            g._db = _open_conn()
        return g._db
    except RuntimeError:
        # Outside application context (init_db called at module level)
        return _open_conn()


def close_db(e=None):
    """Close the per-request connection. Register with app.teardown_appcontext."""
    try:
        from flask import g
        db_conn = g.pop('_db', None)
        if db_conn is not None:
            db_conn.close()
    except RuntimeError:
        pass


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS entries (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            cite_key      TEXT    UNIQUE NOT NULL,
            entry_type    TEXT    NOT NULL DEFAULT 'article',
            title         TEXT,
            author        TEXT,
            author_search TEXT,   -- pipe-separated list of authors for search
            year          INTEGER,
            month         TEXT,
            journal       TEXT,
            volume        TEXT,
            number        TEXT,
            pages         TEXT,
            doi           TEXT,
            url           TEXT,
            eprint        TEXT,
            abstract      TEXT,
            raw_bibtex    TEXT,
            imported_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tags (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS entry_tags (
            entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
            tag_id   INTEGER NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,
            PRIMARY KEY (entry_id, tag_id)
        );

        -- Global keyword master list (mirrors tags structure)
        CREATE TABLE IF NOT EXISTS keyword_list (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS entry_keywords (
            entry_id   INTEGER NOT NULL REFERENCES entries(id)       ON DELETE CASCADE,
            keyword_id INTEGER NOT NULL REFERENCES keyword_list(id)  ON DELETE CASCADE,
            PRIMARY KEY (entry_id, keyword_id)
        );

        CREATE TABLE IF NOT EXISTS reading_notes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id   INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
            content    TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS citations_in_other_papers (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id       INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
            source_cite_key TEXT,
            source_title   TEXT,
            content        TEXT,
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- Full-text search virtual table
        CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
            cite_key,
            title,
            author_search,
            journal,
            abstract,
            content='entries',
            content_rowid='id'
        );

        -- Triggers to keep FTS in sync
        CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
            INSERT INTO entries_fts(rowid, cite_key, title, author_search, journal, abstract)
            VALUES (new.id, new.cite_key, new.title, new.author_search, new.journal, new.abstract);
        END;

        CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
            INSERT INTO entries_fts(entries_fts, rowid, cite_key, title, author_search, journal, abstract)
            VALUES ('delete', old.id, old.cite_key, old.title, old.author_search, old.journal, old.abstract);
            INSERT INTO entries_fts(rowid, cite_key, title, author_search, journal, abstract)
            VALUES (new.id, new.cite_key, new.title, new.author_search, new.journal, new.abstract);
        END;

        CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
            INSERT INTO entries_fts(entries_fts, rowid, cite_key, title, author_search, journal, abstract)
            VALUES ('delete', old.id, old.cite_key, old.title, old.author_search, old.journal, old.abstract);
        END;
    """)

    # Migration: move old free-text keywords table -> keyword_list + entry_keywords
    _migrate_keywords(cur)

    conn.commit()
    conn.close()


def _migrate_keywords(cur):
    """One-time migration from old per-paper free-text keywords to global keyword_list."""
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='keywords'")
    if not cur.fetchone():
        return  # old table doesn't exist, nothing to migrate

    cur.execute("SELECT entry_id, keyword FROM keywords")
    rows = cur.fetchall()
    for entry_id, kw in rows:
        kw = kw.strip()
        if not kw:
            continue
        cur.execute("INSERT OR IGNORE INTO keyword_list (name) VALUES (?)", (kw,))
        cur.execute("SELECT id FROM keyword_list WHERE name = ?", (kw,))
        kw_id = cur.fetchone()[0]
        cur.execute(
            "INSERT OR IGNORE INTO entry_keywords (entry_id, keyword_id) VALUES (?, ?)",
            (entry_id, kw_id),
        )
    cur.execute("DROP TABLE IF EXISTS keywords")


# ---------------------------------------------------------------------------
# Entry queries
# ---------------------------------------------------------------------------

def search_entries(
    q: str = '',
    tag_ids: list[int] = None,
    kw_ids: list[int] = None,
    year_from: int = None,
    year_to: int = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """
    Returns (rows, total_count).
    `q` is searched across title, author, cite_key, journal, abstract,
    keywords, reading_notes, and citations content.
    """
    conn = get_conn()
    cur = conn.cursor()

    params: list = []
    where_clauses: list[str] = []

    if q:
        fts_ids = _fts_search(cur, q)
        note_ids = _note_search(cur, q)
        all_ids = list(set(fts_ids) | set(note_ids))
        if not all_ids:
            return [], 0
        placeholders = ','.join('?' * len(all_ids))
        where_clauses.append(f"e.id IN ({placeholders})")
        params.extend(all_ids)

    if year_from is not None:
        where_clauses.append("e.year >= ?")
        params.append(year_from)
    if year_to is not None:
        where_clauses.append("e.year <= ?")
        params.append(year_to)

    if tag_ids:
        for tid in tag_ids:
            where_clauses.append(
                "e.id IN (SELECT entry_id FROM entry_tags WHERE tag_id = ?)"
            )
            params.append(tid)

    if kw_ids:
        for kid in kw_ids:
            where_clauses.append(
                "e.id IN (SELECT entry_id FROM entry_keywords WHERE keyword_id = ?)"
            )
            params.append(kid)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    count_sql = f"SELECT COUNT(*) FROM entries e {where_sql}"
    cur.execute(count_sql, params)
    total = cur.fetchone()[0]

    data_sql = f"""
        SELECT e.id, e.cite_key, e.entry_type, e.title, e.author,
               e.year, e.month, e.journal, e.eprint, e.doi, e.url
        FROM entries e
        {where_sql}
        ORDER BY e.year DESC, e.cite_key ASC
        LIMIT ? OFFSET ?
    """
    cur.execute(data_sql, params + [limit, offset])
    rows = [dict(r) for r in cur.fetchall()]

    # Batch-load associated data for all rows (avoids N+1 queries)
    if rows:
        ids = [row['id'] for row in rows]
        ph  = ','.join('?' * len(ids))

        # Tags
        cur.execute(f"""
            SELECT et.entry_id, t.id, t.name FROM tags t
            JOIN entry_tags et ON et.tag_id = t.id
            WHERE et.entry_id IN ({ph}) ORDER BY t.name
        """, ids)
        tag_map: dict = {}
        for r in cur.fetchall():
            tag_map.setdefault(r[0], []).append({'id': r[1], 'name': r[2]})

        # Keywords
        cur.execute(f"""
            SELECT ek.entry_id, kl.name FROM keyword_list kl
            JOIN entry_keywords ek ON ek.keyword_id = kl.id
            WHERE ek.entry_id IN ({ph}) ORDER BY kl.name
        """, ids)
        kw_map: dict = {}
        for r in cur.fetchall():
            kw_map.setdefault(r[0], []).append(r[1])

        # Reading notes
        cur.execute(f"SELECT entry_id, content FROM reading_notes WHERE entry_id IN ({ph})", ids)
        note_map = {r[0]: r[1] for r in cur.fetchall()}

        # Citations (concatenated text + count)
        cur.execute(f"""
            SELECT entry_id, content FROM citations_in_other_papers
            WHERE entry_id IN ({ph}) ORDER BY entry_id, created_at
        """, ids)
        cit_rows: dict = {}
        for r in cur.fetchall():
            cit_rows.setdefault(r[0], []).append(r[1] or '')
        cit_text_map  = {eid: '\n---\n'.join(parts) for eid, parts in cit_rows.items()}
        cit_count_map = {eid: len(parts)            for eid, parts in cit_rows.items()}

        for row in rows:
            eid = row['id']
            row['tags']           = tag_map.get(eid, [])
            row['keywords']       = kw_map.get(eid, [])
            row['reading_note']   = note_map.get(eid, '')
            row['citations_text'] = cit_text_map.get(eid, '')
            row['citation_count'] = cit_count_map.get(eid, 0)
    else:
        for row in rows:
            row['tags'] = []; row['keywords'] = []
            row['reading_note'] = ''; row['citations_text'] = ''; row['citation_count'] = 0

    return rows, total


def _fts_search(cur, q: str) -> list[int]:
    """部分一致（LIKE）検索。"""
    like = f'%{q}%'
    cur.execute("""
        SELECT id FROM entries
        WHERE title LIKE ? OR author_search LIKE ? OR cite_key LIKE ?
           OR journal LIKE ? OR abstract LIKE ?
    """, (like, like, like, like, like))
    return [r[0] for r in cur.fetchall()]


def _note_search(cur, q: str) -> list[int]:
    like = f'%{q}%'
    cur.execute("""
        SELECT DISTINCT entry_id FROM reading_notes WHERE content LIKE ?
        UNION
        SELECT DISTINCT entry_id FROM citations_in_other_papers WHERE content LIKE ?
    """, (like, like))
    ids = [r[0] for r in cur.fetchall()]
    cur.execute("""
        SELECT DISTINCT ek.entry_id FROM entry_keywords ek
        JOIN keyword_list kl ON kl.id = ek.keyword_id
        WHERE kl.name LIKE ?
    """, (like,))
    ids += [r[0] for r in cur.fetchall()]
    return ids


def get_entry(entry_id: int) -> dict | None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM entries WHERE id = ?", (entry_id,))
    row = cur.fetchone()
    if not row:
        return None
    entry = dict(row)

    cur.execute("""
        SELECT t.id, t.name FROM tags t
        JOIN entry_tags et ON et.tag_id = t.id
        WHERE et.entry_id = ?
        ORDER BY t.name
    """, (entry_id,))
    entry['tags'] = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT kl.id, kl.name FROM keyword_list kl
        JOIN entry_keywords ek ON ek.keyword_id = kl.id
        WHERE ek.entry_id = ?
        ORDER BY kl.name
    """, (entry_id,))
    entry['keywords'] = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT id, content, updated_at FROM reading_notes WHERE entry_id = ?", (entry_id,))
    note = cur.fetchone()
    entry['reading_note'] = dict(note) if note else None

    cur.execute("""
        SELECT id, source_cite_key, source_title, content, created_at
        FROM citations_in_other_papers
        WHERE entry_id = ?
        ORDER BY created_at
    """, (entry_id,))
    entry['citations'] = [dict(r) for r in cur.fetchall()]

    return entry


# ---------------------------------------------------------------------------
# Tag operations
# ---------------------------------------------------------------------------

def get_all_tags() -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT t.id, t.name, COUNT(et.entry_id) as count
        FROM tags t
        LEFT JOIN entry_tags et ON et.tag_id = t.id
        GROUP BY t.id
        ORDER BY t.name
    """)
    rows = [dict(r) for r in cur.fetchall()]
    return rows


def get_or_create_tag(name: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM tags WHERE name = ?", (name.strip(),))
    row = cur.fetchone()
    if row:
        tag_id = row[0]
    else:
        cur.execute("INSERT INTO tags (name) VALUES (?)", (name.strip(),))
        tag_id = cur.lastrowid
    conn.commit()
    return tag_id


def set_entry_tags(entry_id: int, tag_names: list[str]):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM entry_tags WHERE entry_id = ?", (entry_id,))
    for name in tag_names:
        name = name.strip()
        if not name:
            continue
        cur.execute("SELECT id FROM tags WHERE name = ?", (name,))
        row = cur.fetchone()
        if row:
            tag_id = row[0]
        else:
            cur.execute("INSERT INTO tags (name) VALUES (?)", (name,))
            tag_id = cur.lastrowid
        cur.execute(
            "INSERT OR IGNORE INTO entry_tags (entry_id, tag_id) VALUES (?, ?)",
            (entry_id, tag_id)
        )
    conn.commit()


def delete_tag(tag_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    conn.commit()


def rename_tag(tag_id: int, new_name: str):
    conn = get_conn()
    conn.execute("UPDATE tags SET name = ? WHERE id = ?", (new_name.strip(), tag_id))
    conn.commit()


# ---------------------------------------------------------------------------
# Keyword operations (global list)
# ---------------------------------------------------------------------------

def get_all_keywords() -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT kl.id, kl.name, COUNT(ek.entry_id) as count
        FROM keyword_list kl
        LEFT JOIN entry_keywords ek ON ek.keyword_id = kl.id
        GROUP BY kl.id
        ORDER BY kl.name
    """)
    rows = [dict(r) for r in cur.fetchall()]
    return rows


def get_or_create_keyword(name: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM keyword_list WHERE name = ?", (name.strip(),))
    row = cur.fetchone()
    if row:
        kw_id = row[0]
    else:
        cur.execute("INSERT INTO keyword_list (name) VALUES (?)", (name.strip(),))
        kw_id = cur.lastrowid
    conn.commit()
    return kw_id


def set_entry_keywords(entry_id: int, kw_names: list[str]):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM entry_keywords WHERE entry_id = ?", (entry_id,))
    for name in kw_names:
        name = name.strip()
        if not name:
            continue
        cur.execute("SELECT id FROM keyword_list WHERE name = ?", (name,))
        row = cur.fetchone()
        if row:
            kw_id = row[0]
        else:
            cur.execute("INSERT INTO keyword_list (name) VALUES (?)", (name,))
            kw_id = cur.lastrowid
        cur.execute(
            "INSERT OR IGNORE INTO entry_keywords (entry_id, keyword_id) VALUES (?, ?)",
            (entry_id, kw_id)
        )
    conn.commit()


def delete_keyword(kw_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM keyword_list WHERE id = ?", (kw_id,))
    conn.commit()


def rename_keyword(kw_id: int, new_name: str):
    conn = get_conn()
    conn.execute("UPDATE keyword_list SET name = ? WHERE id = ?", (new_name.strip(), kw_id))
    conn.commit()


# ---------------------------------------------------------------------------
# Reading notes
# ---------------------------------------------------------------------------

def set_reading_note(entry_id: int, content: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM reading_notes WHERE entry_id = ?", (entry_id,))
    row = cur.fetchone()
    if row:
        cur.execute("""
            UPDATE reading_notes SET content = ?, updated_at = CURRENT_TIMESTAMP
            WHERE entry_id = ?
        """, (content, entry_id))
    else:
        cur.execute(
            "INSERT INTO reading_notes (entry_id, content) VALUES (?, ?)",
            (entry_id, content)
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Citations in other papers
# ---------------------------------------------------------------------------

def add_citation(entry_id: int, source_cite_key: str, source_title: str, content: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO citations_in_other_papers (entry_id, source_cite_key, source_title, content)
        VALUES (?, ?, ?, ?)
    """, (entry_id, source_cite_key, source_title, content))
    new_id = cur.lastrowid
    conn.commit()
    return new_id


def update_citation(cit_id: int, source_cite_key: str, source_title: str, content: str):
    conn = get_conn()
    conn.execute("""
        UPDATE citations_in_other_papers
        SET source_cite_key = ?, source_title = ?, content = ?
        WHERE id = ?
    """, (source_cite_key, source_title, content, cit_id))
    conn.commit()


def delete_citation(cit_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM citations_in_other_papers WHERE id = ?", (cit_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Entry meta edit & delete
# ---------------------------------------------------------------------------

# Fields that map directly to DB columns (excluding id, imported_at, updated_at)
_META_FIELDS = ('cite_key', 'entry_type', 'title', 'author', 'year', 'month',
                'journal', 'volume', 'number', 'pages', 'doi', 'url', 'eprint', 'abstract')


def create_entry(fields: dict) -> dict:
    """
    Create a brand-new entry from a fields dict.
    Returns the created entry dict (via get_entry).
    Raises ValueError if cite_key is empty or already exists.
    """
    import re
    cite_key = (fields.get('cite_key') or '').strip()
    if not cite_key:
        raise ValueError('cite_key は必須です')

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM entries WHERE cite_key = ?", (cite_key,))
    if cur.fetchone():
        raise ValueError(f'cite_key "{cite_key}" は既に存在します')

    parts = re.split(r'\s+and\s+', fields.get('author', '') or '', flags=re.IGNORECASE)
    author_search = ' | '.join(p.strip() for p in parts if p.strip())

    row = {
        'cite_key':     cite_key,
        'entry_type':   fields.get('entry_type', 'article'),
        'title':        fields.get('title', ''),
        'author':       fields.get('author', ''),
        'author_search': author_search,
        'year':         fields.get('year') or None,
        'month':        fields.get('month', ''),
        'journal':      fields.get('journal', ''),
        'volume':       fields.get('volume', ''),
        'number':       fields.get('number', ''),
        'pages':        fields.get('pages', ''),
        'doi':          fields.get('doi', ''),
        'url':          fields.get('url', ''),
        'eprint':       fields.get('eprint', ''),
        'abstract':     fields.get('abstract', ''),
    }
    row['raw_bibtex'] = _build_bibtex(row)

    cur.execute("""
        INSERT INTO entries
          (cite_key, entry_type, title, author, author_search,
           year, month, journal, volume, number, pages,
           doi, url, eprint, abstract, raw_bibtex)
        VALUES
          (:cite_key, :entry_type, :title, :author, :author_search,
           :year, :month, :journal, :volume, :number, :pages,
           :doi, :url, :eprint, :abstract, :raw_bibtex)
    """, row)
    new_id = cur.lastrowid
    conn.commit()
    return get_entry(new_id)


def update_entry_meta(entry_id: int, fields: dict) -> dict | None:
    """
    Update bibliographic fields of an entry and rebuild raw_bibtex.
    Only keys present in fields are updated; others are left unchanged.
    Returns the updated entry dict, or None if not found.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM entries WHERE id = ?", (entry_id,))
    row = cur.fetchone()
    if not row:
        return None

    current = dict(row)
    for k in _META_FIELDS:
        if k in fields:
            current[k] = fields[k]

    # rebuild author_search
    import re
    parts = re.split(r'\s+and\s+', current.get('author', '') or '', flags=re.IGNORECASE)
    current['author_search'] = ' | '.join(p.strip() for p in parts if p.strip())

    # rebuild raw_bibtex
    current['raw_bibtex'] = _build_bibtex(current)

    cur.execute("""
        UPDATE entries SET
          cite_key=:cite_key, entry_type=:entry_type,
          title=:title, author=:author, author_search=:author_search,
          year=:year, month=:month, journal=:journal,
          volume=:volume, number=:number, pages=:pages,
          doi=:doi, url=:url, eprint=:eprint, abstract=:abstract,
          raw_bibtex=:raw_bibtex, updated_at=CURRENT_TIMESTAMP
        WHERE id=:id
    """, {**current, 'id': entry_id})
    conn.commit()
    return get_entry(entry_id)


def _build_bibtex(e: dict) -> str:
    """Reconstruct a BibTeX entry string from an entry dict."""
    field_order = ('title', 'author', 'journal', 'booktitle', 'year', 'month',
                   'volume', 'number', 'pages', 'doi', 'url', 'eprint',
                   'archiveprefix', 'primaryclass', 'abstract', 'issn', 'isbn',
                   'publisher', 'school', 'note', 'howpublished')
    skip = {'id', 'cite_key', 'entry_type', 'author_search', 'raw_bibtex',
            'imported_at', 'updated_at'}
    lines = [f"@{e.get('entry_type', 'misc')}{{{e.get('cite_key', 'unknown')},"]
    seen = set()
    for k in field_order:
        v = e.get(k)
        if v and k not in skip:
            lines.append(f"  {k} = {{{v}}},")
            seen.add(k)
    for k, v in e.items():
        if k not in seen and k not in skip and v and k not in ('entry_type', 'cite_key'):
            lines.append(f"  {k} = {{{v}}},")
    lines.append("}")
    return '\n'.join(lines)


def delete_entry(entry_id: int):
    """Delete an entry and all associated data (CASCADE handles relations)."""
    conn = get_conn()
    conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def find_duplicates() -> list[list[dict]]:
    """
    Return a list of duplicate groups.
    Each group is a list of ≥2 entry dicts that share a DOI, eprint, or
    normalised title.
    """
    import re

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, cite_key, entry_type, title, author, year, doi, eprint
        FROM entries ORDER BY year, cite_key
    """)
    rows = [dict(r) for r in cur.fetchall()]

    def _norm(t):
        return re.sub(r'[^a-z0-9]', '', (t or '').lower())

    groups: dict[str, list[dict]] = {}

    for r in rows:
        keys = []
        if r['doi']:
            keys.append('doi:' + _norm(r['doi']))
        if r['eprint']:
            keys.append('eprint:' + _norm(r['eprint']))
        nt = _norm(r['title'])
        if len(nt) > 10:       # skip very short titles
            keys.append('title:' + nt)

        for k in keys:
            groups.setdefault(k, []).append(r)

    seen_sets: list[frozenset] = []
    result: list[list[dict]] = []

    for entries in groups.values():
        if len(entries) < 2:
            continue
        fs = frozenset(e['id'] for e in entries)
        if fs in seen_sets:
            continue
        seen_sets.append(fs)
        result.append(entries)

    return result


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_all_bibtex() -> str:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT raw_bibtex FROM entries ORDER BY year, cite_key")
    parts = [row[0] for row in cur.fetchall() if row[0]]
    return '\n\n'.join(parts)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_stats() -> dict:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM entries")
    total = cur.fetchone()[0]
    cur.execute("SELECT year, COUNT(*) as c FROM entries WHERE year IS NOT NULL GROUP BY year ORDER BY year")
    by_year = [dict(r) for r in cur.fetchall()]
    return {'total': total, 'by_year': by_year}
