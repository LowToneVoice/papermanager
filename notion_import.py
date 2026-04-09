"""
Notion CSV import for BibManager.

Columns in the Notion export CSV:
  tag, key words, yyyymm, Great Authors, title,
  What is said to be written, What WAS written, Bibtex

Also handles the _all.csv variant with different column order:
  Bibtex, Great Authors, What WAS written, What is said to be written,
  key words, tag, title, yyyymm
"""

import csv
import io
import re
import sqlite3

import database as db
from bib_parser import parse_bib_string


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def import_notion_csv(csv_text: str) -> dict:
    """
    Parse a Notion CSV export and merge data into the existing DB.
    Returns a summary dict: {matched, skipped, not_found, errors}.
    """
    rows = _parse_csv(csv_text)
    summary = {'matched': 0, 'skipped': 0, 'not_found': 0, 'errors': []}

    conn = db.get_conn()
    cur = conn.cursor()

    for row in rows:
        try:
            _process_row(row, cur, summary)
        except Exception as e:
            summary['errors'].append(str(e))

    conn.commit()
    conn.close()
    return summary


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

def _parse_csv(csv_text: str) -> list[dict]:
    """Parse CSV and normalise column names."""
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = []
    for raw in reader:
        # Normalise keys: strip whitespace, lowercase
        row = {k.strip(): v.strip() if v else '' for k, v in raw.items()}
        rows.append(row)
    return rows


def _get_field(row: dict, *candidates: str) -> str:
    """Return first non-empty field from candidates (case-insensitive)."""
    lrow = {k.lower(): v for k, v in row.items()}
    for c in candidates:
        v = lrow.get(c.lower(), '')
        if v:
            return v
    return ''


# ---------------------------------------------------------------------------
# Per-row processing
# ---------------------------------------------------------------------------

def _process_row(row: dict, cur: sqlite3.Cursor, summary: dict):
    bibtex_raw = _get_field(row, 'Bibtex', 'bibtex')
    notion_title = _get_field(row, 'title')
    tag_str   = _get_field(row, 'tag')
    kw_str    = _get_field(row, 'key words', 'keywords')
    what_said = _get_field(row, 'What is said to be written')
    what_was  = _get_field(row, 'What WAS written', 'What was written')

    # Extract cite_key from the embedded BibTeX
    notion_cite_key = _extract_cite_key(bibtex_raw)

    # Find matching entry in DB
    entry_id = _find_entry(cur, notion_cite_key, notion_title, bibtex_raw)

    if entry_id is None:
        summary['not_found'] += 1
        summary['errors'].append(
            f"No match: cite_key={notion_cite_key!r}  title={notion_title!r}"
        )
        return

    # --- Tags ---
    if tag_str:
        tags = [t.strip() for t in tag_str.split(',') if t.strip()]
        # Merge with existing tags (don't overwrite)
        cur.execute("""
            SELECT t.name FROM tags t
            JOIN entry_tags et ON et.tag_id = t.id
            WHERE et.entry_id = ?
        """, (entry_id,))
        existing_tags = {r[0] for r in cur.fetchall()}
        new_tags = list(existing_tags | set(tags))
        db.set_entry_tags(entry_id, new_tags)

    # --- Keywords ---
    if kw_str:
        kws = [k.strip() for k in re.split(r'[,;]', kw_str) if k.strip()]
        # Merge with existing keywords
        cur.execute("""
            SELECT kl.name FROM keyword_list kl
            JOIN entry_keywords ek ON ek.keyword_id = kl.id
            WHERE ek.entry_id = ?
        """, (entry_id,))
        existing_kws = {r[0] for r in cur.fetchall()}
        new_kws = list(existing_kws | set(kws))
        db.set_entry_keywords(entry_id, new_kws)

    # --- Reading note (What WAS written) ---
    if what_was:
        cur.execute("SELECT id, content FROM reading_notes WHERE entry_id = ?", (entry_id,))
        existing = cur.fetchone()
        if existing:
            # Append only if not already present
            if what_was not in (existing['content'] or ''):
                new_content = (existing['content'] or '') + '\n\n' + what_was
                cur.execute("""
                    UPDATE reading_notes SET content = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE entry_id = ?
                """, (new_content.strip(), entry_id))
        else:
            cur.execute(
                "INSERT INTO reading_notes (entry_id, content) VALUES (?, ?)",
                (entry_id, what_was)
            )

    # --- Citation / "What is said to be written" ---
    if what_said:
        cur.execute("""
            SELECT id FROM citations_in_other_papers
            WHERE entry_id = ? AND source_cite_key = 'Notion import'
        """, (entry_id,))
        existing_cit = cur.fetchone()
        if not existing_cit:
            cur.execute("""
                INSERT INTO citations_in_other_papers
                  (entry_id, source_cite_key, source_title, content)
                VALUES (?, ?, ?, ?)
            """, (entry_id, 'Notion import', 'Notionメモ', what_said))

    summary['matched'] += 1


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------

def _extract_cite_key(bibtex_raw: str) -> str:
    """Extract cite_key from a BibTeX string, e.g. @article{Miller1952, ..."""
    if not bibtex_raw:
        return ''
    m = re.search(r'@\w+\s*\{([^,\s]+)', bibtex_raw)
    return m.group(1).strip() if m else ''


def _extract_title_from_bibtex(bibtex_raw: str) -> str:
    """Extract title field value from a BibTeX string."""
    if not bibtex_raw:
        return ''
    m = re.search(r'\btitle\s*=\s*[\{"](.*?)[\}"]', bibtex_raw, re.IGNORECASE | re.DOTALL)
    if m:
        return re.sub(r'\s+', ' ', m.group(1).strip(' {}'))
    return ''


def _normalise_title(t: str) -> str:
    """Lowercase, strip punctuation for fuzzy matching."""
    return re.sub(r'[^a-z0-9 ]', '', t.lower()).strip()


def _find_entry(cur: sqlite3.Cursor, notion_key: str, notion_title: str, bibtex_raw: str) -> int | None:
    """
    Try to match a DB entry in order:
    1. notion_key directly matches entries.cite_key
    2. Title extracted from embedded BibTeX matches entries.title
    3. notion_title column matches entries.title
    """
    # 1. Direct cite_key match
    if notion_key:
        cur.execute("SELECT id FROM entries WHERE cite_key = ?", (notion_key,))
        row = cur.fetchone()
        if row:
            return row[0]

    # 2. Title from embedded BibTeX
    bib_title = _extract_title_from_bibtex(bibtex_raw)
    if bib_title:
        entry_id = _match_by_title(cur, bib_title)
        if entry_id:
            return entry_id

    # 3. notion_title column
    if notion_title:
        entry_id = _match_by_title(cur, notion_title)
        if entry_id:
            return entry_id

    return None


def _match_by_title(cur: sqlite3.Cursor, title: str) -> int | None:
    """Exact case-insensitive title match."""
    cur.execute(
        "SELECT id FROM entries WHERE lower(title) = lower(?)",
        (title.strip(),)
    )
    row = cur.fetchone()
    return row[0] if row else None
