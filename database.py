"""
SQLite database setup and CRUD operations for BibManager.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "bibmanager.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


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

        CREATE TABLE IF NOT EXISTS keywords (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
            keyword  TEXT    NOT NULL
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

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Entry queries
# ---------------------------------------------------------------------------

def search_entries(
    q: str = '',
    tag_ids: list[int] = None,
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
        # Use FTS for main fields
        fts_ids = _fts_search(cur, q)
        # Also search keywords and notes
        kw_ids = _keyword_note_search(cur, q)
        all_ids = list(set(fts_ids) | set(kw_ids))
        if not all_ids:
            conn.close()
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

    # Attach tags for each row
    for row in rows:
        cur.execute("""
            SELECT t.id, t.name FROM tags t
            JOIN entry_tags et ON et.tag_id = t.id
            WHERE et.entry_id = ?
        """, (row['id'],))
        row['tags'] = [dict(r) for r in cur.fetchall()]

    conn.close()
    return rows, total


def _fts_search(cur, q: str) -> list[int]:
    try:
        cur.execute(
            "SELECT rowid FROM entries_fts WHERE entries_fts MATCH ? ORDER BY rank",
            (q,)
        )
        return [r[0] for r in cur.fetchall()]
    except Exception:
        # Fallback to LIKE if FTS query has syntax issues
        like = f'%{q}%'
        cur.execute("""
            SELECT id FROM entries
            WHERE title LIKE ? OR author_search LIKE ? OR cite_key LIKE ?
               OR journal LIKE ? OR abstract LIKE ?
        """, (like, like, like, like, like))
        return [r[0] for r in cur.fetchall()]


def _keyword_note_search(cur, q: str) -> list[int]:
    like = f'%{q}%'
    cur.execute("SELECT DISTINCT entry_id FROM keywords WHERE keyword LIKE ?", (like,))
    ids = [r[0] for r in cur.fetchall()]
    cur.execute("""
        SELECT DISTINCT entry_id FROM reading_notes WHERE content LIKE ?
        UNION
        SELECT DISTINCT entry_id FROM citations_in_other_papers WHERE content LIKE ?
    """, (like, like))
    ids += [r[0] for r in cur.fetchall()]
    return ids


def get_entry(entry_id: int) -> dict | None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM entries WHERE id = ?", (entry_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    entry = dict(row)

    cur.execute("""
        SELECT t.id, t.name FROM tags t
        JOIN entry_tags et ON et.tag_id = t.id
        WHERE et.entry_id = ?
        ORDER BY t.name
    """, (entry_id,))
    entry['tags'] = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT id, keyword FROM keywords WHERE entry_id = ? ORDER BY id", (entry_id,))
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

    conn.close()
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
    conn.close()
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
    conn.close()
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
    conn.close()


def delete_tag(tag_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    conn.commit()
    conn.close()


def rename_tag(tag_id: int, new_name: str):
    conn = get_conn()
    conn.execute("UPDATE tags SET name = ? WHERE id = ?", (new_name.strip(), tag_id))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Keyword operations
# ---------------------------------------------------------------------------

def set_entry_keywords(entry_id: int, keywords: list[str]):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM keywords WHERE entry_id = ?", (entry_id,))
    for kw in keywords:
        kw = kw.strip()
        if kw:
            cur.execute("INSERT INTO keywords (entry_id, keyword) VALUES (?, ?)", (entry_id, kw))
    conn.commit()
    conn.close()


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
    conn.close()


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
    conn.close()
    return new_id


def update_citation(cit_id: int, source_cite_key: str, source_title: str, content: str):
    conn = get_conn()
    conn.execute("""
        UPDATE citations_in_other_papers
        SET source_cite_key = ?, source_title = ?, content = ?
        WHERE id = ?
    """, (source_cite_key, source_title, content, cit_id))
    conn.commit()
    conn.close()


def delete_citation(cit_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM citations_in_other_papers WHERE id = ?", (cit_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_all_bibtex() -> str:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT raw_bibtex FROM entries ORDER BY year, cite_key")
    parts = [row[0] for row in cur.fetchall() if row[0]]
    conn.close()
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
    conn.close()
    return {'total': total, 'by_year': by_year}
