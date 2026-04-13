#!/usr/bin/env python3
"""build_puzzle_json.py — YAML-config-driven puzzle JSON builder.

Usage:
    python scripts/build_puzzle_json.py configs/mating_patterns_100_by_theme.yaml
    python scripts/build_puzzle_json.py configs/mate_in_one_800.yaml

Reads a YAML config file that describes a puzzle book (title, chapters, sets).
Queries data/lichess_puzzles.sqlite for each chapter with a SINGLE query that
fetches all candidate rows, then applies per-set selection/deduplication in
Python. This is much faster than one query per set.

DB requirements:
    - puzzles table with columns:
        puzzle_id, fen, moves, move_count, rating, rating_deviation,
        popularity, nb_plays, game_url, opening_tags,
        side_to_move ('w'/'b'), first_move_piece ('K'/'Q'/'R'/'B'/'N'/'P')
    - puzzle_themes table with columns: puzzle_id, theme (one row per tag)
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "lichess_puzzles.sqlite"

# Puzzle row column order (must match SELECT in fetch_chapter_candidates)
COLUMNS = [
    "puzzle_id", "fen", "moves", "move_count",
    "rating", "rating_deviation", "popularity", "nb_plays",
    "game_url", "opening_tags", "side_to_move", "first_move_piece",
    "display_fen",
]

# Map YAML side_to_move values to DB values
SIDE_MAP = {
    "white": "w",
    "black": "b",
    "w": "w",
    "b": "b",
}

# Python sort key names (same as DB column names for the fields we care about)
SORT_FIELD_PY = {
    "rating", "popularity", "nb_plays", "rating_deviation",
    "side_to_move", "first_move_piece", "move_count",
}


def _build_set_subquery(
    set_spec: dict,
    global_filters: dict,
    set_index: int,
) -> tuple[str, list]:
    """Build one SELECT branch (for UNION ALL) against the denormalized
    puzzle_theme_rows table — one row per (puzzle, theme) with all puzzle
    columns inline.  No JOINs needed; the covering index on
    (theme, side_to_move, first_move_piece, nb_plays DESC, rating, popularity)
    satisfies WHERE + ORDER BY + LIMIT in a single index scan.

    When a set specifies multiple themes (AND-logic), we drive from the
    rarest theme and add EXISTS checks against puzzle_theme_rows for the rest.
    """
    themes = set_spec.get("themes", [])
    side_to_move = set_spec.get("side_to_move")
    rating_range = set_spec.get("rating")
    mate_in = set_spec.get("mate_in")
    opening = set_spec.get("opening")
    first_move_piece = set_spec.get("first_move_piece")
    count = set_spec.get("count")
    sort_specs = set_spec.get("sort", [{"field": "nb_plays", "order": "desc"}])

    min_plays = set_spec.get("min_plays", global_filters.get("min_plays", 0))
    min_popularity = set_spec.get("min_popularity", global_filters.get("min_popularity", 0))

    params: list = []
    where_parts: list[str] = []

    # Drive from the first (primary) theme; any additional themes use EXISTS
    primary_theme = themes[0] if themes else None
    extra_themes = themes[1:] if len(themes) > 1 else []

    if primary_theme:
        where_parts.append("r.theme = ?")
        params.append(primary_theme)

    # mate_in maps to a theme tag — treat as an extra required theme
    if mate_in is not None:
        mi_tags = [f"mateIn{n}" for n in mate_in] if isinstance(mate_in, list) else [f"mateIn{mate_in}"]
        extra_themes = list(extra_themes) + mi_tags

    # Additional required themes: EXISTS against puzzle_theme_rows (fast — covered index)
    for extra in extra_themes:
        where_parts.append(
            "EXISTS (SELECT 1 FROM puzzle_theme_rows x "
            "WHERE x.puzzle_id = r.puzzle_id AND x.theme = ?)"
        )
        params.append(extra)

    if side_to_move:
        db_side = SIDE_MAP.get(str(side_to_move).lower(), side_to_move)
        where_parts.append("r.side_to_move = ?")
        params.append(db_side)

    if rating_range:
        lo, hi = rating_range
        where_parts.append("r.rating >= ? AND r.rating <= ?")
        params.extend([lo, hi])

    if first_move_piece:
        where_parts.append("r.first_move_piece = ?")
        params.append(str(first_move_piece).upper())

    if min_plays > 0:
        where_parts.append("r.nb_plays >= ?")
        params.append(min_plays)

    if min_popularity > 0:
        where_parts.append("r.popularity >= ?")
        params.append(min_popularity)

    if opening:
        where_parts.append("r.opening_tags LIKE ?")
        params.append(f"%{opening}%")

    where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    order_parts = []
    for s in sort_specs:
        field = s.get("field", "nb_plays")
        direction = "DESC" if s.get("order", "asc").lower() == "desc" else "ASC"
        if field in SORT_FIELD_PY:
            order_parts.append(f"r.{field} {direction}")
    order_clause = ("ORDER BY " + ", ".join(order_parts)) if order_parts else ""

    limit_clause = f"LIMIT {int(count)}" if count is not None else ""

    sql = f"""
  SELECT r.puzzle_id, r.fen, r.moves, r.move_count,
         r.rating, r.rating_deviation, r.popularity, r.nb_plays,
         r.game_url, r.opening_tags, r.side_to_move, r.first_move_piece,
         r.display_fen,
         {set_index} AS set_index
  FROM puzzle_theme_rows r
  {where_clause}
  {order_clause}
  {limit_clause}""".strip()

    return sql, params


def fetch_chapter_puzzles(
    chapter_spec: dict,
    global_filters: dict,
    conn: sqlite3.Connection,
) -> list[dict]:
    """Build one UNION ALL query — one branch per set — so that all filtering,
    sorting, and limiting happens in SQL. Python only deduplicates and
    applies the chapter-level sort.
    """
    sets = chapter_spec.get("sets", [])
    if not sets:
        return []

    branches: list[str] = []
    all_params: list = []

    for i, set_spec in enumerate(sets):
        branch_sql, branch_params = _build_set_subquery(set_spec, global_filters, i)
        branches.append(branch_sql)
        all_params.extend(branch_params)

    # Wrap each branch so UNION ALL preserves per-branch ORDER BY + LIMIT.
    # SQLite requires subqueries here to honour the inner ORDER BY.
    wrapped = [f"SELECT * FROM ({b})" for b in branches]
    sql = "\nUNION ALL\n".join(wrapped)

    cur = conn.execute(sql, all_params)
    rows = cur.fetchall()

    # Columns: COLUMNS + set_index (last column)
    puzzles: list[dict] = []
    seen_ids: set[str] = set()
    for row in rows:
        pid = row[0]
        if pid in seen_ids:
            continue
        seen_ids.add(pid)
        p = dict(zip(COLUMNS, row[:13]))
        p["moves"] = p["moves"].split() if p["moves"] else []
        p["_set_index"] = row[13]
        puzzles.append(p)

    return puzzles


def python_sort_key(sort_specs: list[dict]):
    """Return a sort-key function for a list of {field, order} dicts."""
    def key(p: dict):
        result = []
        for s in sort_specs:
            field = s["field"]
            val = p.get(field)
            if val is None:
                val = ""
            desc = s.get("order", "asc").lower() == "desc"
            if isinstance(val, (int, float)):
                result.append(-val if desc else val)
            else:
                # string: compare lowercased; invert for DESC
                v = val.lower()
                if desc:
                    result.append(tuple(~ord(c) for c in v))
                else:
                    result.append(v)
        return result
    return key


def build_chapter(chapter_spec: dict, global_filters: dict, conn: sqlite3.Connection) -> dict:
    """Fetch all puzzles for a chapter via a single UNION ALL SQL query,
    then deduplicate and apply the chapter-level sort in Python."""
    title = chapter_spec["title"]
    print(f"  Chapter: {title}", end="", flush=True)

    # Single DB round-trip: all sets combined into one UNION ALL query
    all_puzzles = fetch_chapter_puzzles(chapter_spec, global_filters, conn)
    print(f" — {len(all_puzzles)} puzzles selected", end="")

    # Apply chapter-level sort (e.g. nb_plays desc to interleave piece types)
    chapter_sort = chapter_spec.get("sort")
    if chapter_sort:
        all_puzzles.sort(key=python_sort_key(chapter_sort))

    # Strip internal keys before storing
    clean_puzzles = [{k: v for k, v in p.items() if not k.startswith("_")} for p in all_puzzles]

    white_puzzles = [p for p in clean_puzzles if p.get("side_to_move") == "w"]
    black_puzzles = [p for p in clean_puzzles if p.get("side_to_move") == "b"]

    print(f" ({len(white_puzzles)} white, {len(black_puzzles)} black)")

    return {
        "title": title,
        "puzzle_count": len(clean_puzzles),
        "white_to_move_count": len(white_puzzles),
        "black_to_move_count": len(black_puzzles),
        "puzzles": clean_puzzles,
        "groups": {
            "white_to_move": white_puzzles,
            "black_to_move": black_puzzles,
        },
    }


def build_document(config: dict, conn: sqlite3.Connection) -> dict:
    book = config.get("book", {})
    global_filters = config.get("filters", {})
    default_chapter_sort = config.get("default_chapter_sort")

    chapters_spec = config.get("chapters", [])
    chapters = []
    total_puzzles = 0

    for chapter_spec in chapters_spec:
        # Inject default_chapter_sort if chapter has no explicit sort
        if default_chapter_sort and "sort" not in chapter_spec:
            chapter_spec = dict(chapter_spec)
            chapter_spec["sort"] = default_chapter_sort
        chapter = build_chapter(chapter_spec, global_filters, conn)
        chapters.append(chapter)
        total_puzzles += chapter["puzzle_count"]

    document = {
        "title": book.get("title", "Chess Puzzle Book"),
        "subtitle": book.get("subtitle", ""),
        "author": book.get("author", ""),
        "publisher": book.get("publisher", ""),
        "toc": book.get("toc", True),
        "chapter_title_pages": book.get("chapter_title_pages", True),
        "total_puzzle_count": total_puzzles,
        "chapters": chapters,
    }
    return document


def main():
    parser = argparse.ArgumentParser(
        description="Build a puzzle JSON from a YAML config and the Lichess SQLite DB."
    )
    parser.add_argument(
        "config",
        help="Path to the YAML config file (e.g. configs/mating_patterns_100_by_theme.yaml)",
    )
    parser.add_argument(
        "--db",
        default=str(DB_PATH),
        help=f"Path to the SQLite database (default: {DB_PATH})",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Override the output JSON path (default: read from config book.output_json)",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = BASE_DIR / config_path
    if not config_path.exists():
        print(f"ERROR: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_rel = config.get("book", {}).get("output_json")
        if not output_rel:
            print("ERROR: no output_json in config book section and --output not specified", file=sys.stderr)
            sys.exit(1)
        output_path = BASE_DIR / output_rel

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Config:   {config_path}")
    print(f"Database: {db_path}")
    print(f"Output:   {output_path}")
    print()

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-65536")  # 64 MB cache

    try:
        document = build_document(config, conn)
    finally:
        conn.close()

    print()
    print(f"Writing {output_path} ...")
    with open(output_path, "w") as f:
        json.dump(document, f, indent=2, ensure_ascii=False)

    total = document["total_puzzle_count"]
    print(f"Done. {total} puzzles written across {len(document['chapters'])} chapters.")


if __name__ == "__main__":
    main()
