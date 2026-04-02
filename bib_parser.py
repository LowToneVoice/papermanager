"""
Pure-Python BibTeX parser.
Handles the full bibbib.bib including:
  - Multiple entry types (article, book, misc, incollection, inproceedings, mastersthesis, …)
  - Multi-line field values with balanced braces
  - LaTeX special characters in values
  - Japanese / Unicode author names
  - Custom fields (eprint, archivePrefix, primaryClass, …)
"""

import re
import sqlite3
from pathlib import Path


# ---------------------------------------------------------------------------
# Low-level tokeniser
# ---------------------------------------------------------------------------

def _read_balanced(text: str, start: int) -> str:
    """
    Starting at text[start] (which must be '{'), read until the matching '}'.
    Returns the content between the outer braces (not including them).
    """
    assert text[start] == '{'
    depth = 0
    i = start
    while i < len(text):
        c = text[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
        i += 1
    raise ValueError(f"Unbalanced braces starting at position {start}")


def _strip_outer(value: str) -> str:
    """Remove surrounding braces or double-quotes from a field value string."""
    value = value.strip()
    if value.startswith('{') and value.endswith('}'):
        return value[1:-1].strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1].strip()
    return value


# ---------------------------------------------------------------------------
# Entry parser
# ---------------------------------------------------------------------------

def parse_bib_string(bib_text: str) -> list[dict]:
    """
    Parse a BibTeX string and return a list of entry dicts.
    Each dict has keys: entry_type, cite_key, and one key per bib field (lowercase).
    """
    entries: list[dict] = []

    # Regex to find the start of each entry: @TYPE{
    entry_starts = list(re.finditer(r'@(\w+)\s*\{', bib_text, re.IGNORECASE))

    for idx, match in enumerate(entry_starts):
        entry_type = match.group(1).lower()

        # Skip @string, @comment, @preamble
        if entry_type in ('string', 'comment', 'preamble'):
            continue

        # The body of the entry is between the opening '{' and its matching '}'
        body_start = match.end() - 1  # points to '{'
        try:
            body = _read_balanced(bib_text, body_start)
        except (ValueError, AssertionError):
            continue  # malformed entry – skip

        # First token before the first comma is the cite_key
        comma_pos = body.find(',')
        if comma_pos == -1:
            continue
        cite_key = body[:comma_pos].strip()
        fields_text = body[comma_pos + 1:]

        entry = {'entry_type': entry_type, 'cite_key': cite_key}

        # Parse fields: field_name = {value} or field_name = "value" or field_name = number
        i = 0
        while i < len(fields_text):
            # Skip whitespace / commas
            while i < len(fields_text) and fields_text[i] in ' \t\n\r,':
                i += 1
            if i >= len(fields_text):
                break

            # Read field name (up to '=')
            eq = fields_text.find('=', i)
            if eq == -1:
                break
            field_name = fields_text[i:eq].strip().lower()

            # Advance past '='
            i = eq + 1
            while i < len(fields_text) and fields_text[i] in ' \t\n\r':
                i += 1

            if i >= len(fields_text):
                break

            c = fields_text[i]
            if c == '{':
                try:
                    value = _read_balanced(fields_text, i)
                    i += len(value) + 2  # skip opening and closing brace
                except (ValueError, AssertionError):
                    break
            elif c == '"':
                # Find closing " that is not preceded by odd number of backslashes
                j = i + 1
                while j < len(fields_text):
                    if fields_text[j] == '"':
                        break
                    if fields_text[j] == '{':
                        # skip balanced block inside double-quoted value
                        try:
                            inner = _read_balanced(fields_text, j)
                            j += len(inner) + 2
                        except (ValueError, AssertionError):
                            j += 1
                    else:
                        j += 1
                value = fields_text[i + 1:j]
                i = j + 1
            else:
                # Bare value (number or macro) — read until comma or }
                j = i
                while j < len(fields_text) and fields_text[j] not in ',}':
                    j += 1
                value = fields_text[i:j].strip()
                i = j

            entry[field_name] = value.strip()

        entries.append(entry)

    return entries


def parse_bib_file(path: str) -> list[dict]:
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    return parse_bib_string(text)


# ---------------------------------------------------------------------------
# Author helpers
# ---------------------------------------------------------------------------

def split_authors(author_field: str) -> list[str]:
    """Split a BibTeX author field on ' and ' (case-insensitive)."""
    if not author_field:
        return []
    parts = re.split(r'\s+and\s+', author_field, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


def first_author_last_name(author_field: str) -> str:
    """Return the last name of the first author for quick display."""
    authors = split_authors(author_field)
    if not authors:
        return ''
    first = authors[0]
    # Handle "Last, First" format
    if ',' in first:
        return first.split(',')[0].strip()
    # Handle "First Last" format — take last word
    parts = first.split()
    return parts[-1] if parts else first


# ---------------------------------------------------------------------------
# LaTeX normalisation (for search)
# ---------------------------------------------------------------------------

_LATEX_MAP = {
    r'\"a': 'ä', r'\"o': 'ö', r'\"u': 'ü',
    r'\"A': 'Ä', r'\"O': 'Ö', r'\"U': 'Ü',
    r"\'{e}": 'é', r"\'{a}": 'á', r"\'{o}": 'ó',
    r'\'e': 'é', r'\'a': 'á', r'\'o': 'ó',
    r'\ss': 'ß', r'\o': 'ø', r'\O': 'Ø',
    r'\ae': 'æ', r'\AE': 'Æ', r'\aa': 'å', r'\AA': 'Å',
    r'{\o}': 'ø', r'{\O}': 'Ø',
    r'\textonehalf{}': '½', r'\textonehalf': '½',
    r'\textbf': '', r'\textit': '', r'\emph': '',
}

def normalise_latex(text: str) -> str:
    """Best-effort conversion of LaTeX escapes to Unicode."""
    if not text:
        return text
    for latex, uni in _LATEX_MAP.items():
        text = text.replace(latex, uni)
    # Remove remaining \cmd{...} or \cmd
    text = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\[a-zA-Z]+', '', text)
    # Remove bare braces
    text = text.replace('{', '').replace('}', '')
    return text.strip()


# ---------------------------------------------------------------------------
# Database import
# ---------------------------------------------------------------------------

def import_entries_to_db(entries: list[dict], db_conn: sqlite3.Connection) -> dict:
    """
    Insert / update entries in the database.
    Returns a summary dict: {added, updated, skipped}.
    Existing tags/notes/keywords are never touched on update.
    """
    cur = db_conn.cursor()
    summary = {'added': 0, 'updated': 0, 'skipped': 0}

    for e in entries:
        cite_key = e.get('cite_key', '').strip()
        if not cite_key:
            summary['skipped'] += 1
            continue

        # Build raw_bibtex reconstruction
        raw = _reconstruct_bibtex(e)

        # Normalised author string for search
        author_raw = e.get('author', '')
        authors_list = split_authors(author_raw)
        author_search = ' | '.join(authors_list)  # stored for full-text search

        row = {
            'cite_key': cite_key,
            'entry_type': e.get('entry_type', 'misc'),
            'title': normalise_latex(e.get('title', '')),
            'author': normalise_latex(author_raw),
            'author_search': normalise_latex(author_search),
            'year': _safe_int(e.get('year')),
            'month': e.get('month', ''),
            'journal': e.get('journal') or e.get('booktitle') or e.get('school') or '',
            'volume': e.get('volume', ''),
            'number': e.get('number', ''),
            'pages': e.get('pages', ''),
            'doi': e.get('doi', ''),
            'url': e.get('url', ''),
            'eprint': e.get('eprint', ''),
            'abstract': e.get('abstract', ''),
            'raw_bibtex': raw,
        }

        cur.execute("SELECT id FROM entries WHERE cite_key = ?", (cite_key,))
        existing = cur.fetchone()

        if existing is None:
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
            summary['added'] += 1
        else:
            # Update bib fields only; leave tags/notes untouched
            cur.execute("""
                UPDATE entries SET
                  entry_type=:entry_type, title=:title, author=:author,
                  author_search=:author_search,
                  year=:year, month=:month, journal=:journal,
                  volume=:volume, number=:number, pages=:pages,
                  doi=:doi, url=:url, eprint=:eprint,
                  abstract=:abstract, raw_bibtex=:raw_bibtex,
                  updated_at=CURRENT_TIMESTAMP
                WHERE cite_key=:cite_key
            """, row)
            summary['updated'] += 1

    db_conn.commit()
    return summary


def _safe_int(val) -> int | None:
    try:
        return int(str(val).strip())
    except (TypeError, ValueError):
        return None


def _reconstruct_bibtex(e: dict) -> str:
    """Reconstruct a minimal BibTeX entry string from a parsed dict."""
    skip = {'entry_type', 'cite_key'}
    lines = [f"@{e['entry_type']}{{{e['cite_key']},"]
    for k, v in e.items():
        if k in skip or not v:
            continue
        lines.append(f"  {k} = {{{v}}},")
    lines.append("}")
    return '\n'.join(lines)
