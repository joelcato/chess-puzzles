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


def fetch_chapter_candidates(
    chapter_spec: dict,
    global_filters: dict,
    conn: sqlite3.Connection,
) -> list[dict]:
    """Issue ONE query per chapter to fetch all candidate rows.

    Strategy:
      1. Collect the union of all themes referenced across every set in the
         chapter.  Use GROUP BY + HAVING COUNT to enforce AND-logic per set
         is handled in Python after fetching.
      2. Apply the widest possible numeric bounds (rating, nb_plays, etc.)
         as a SQL pre-filter to shrink the result set before Python work.
      3. Attach every theme tag for each returned puzzle_id so Python can
         cheaply check per-set theme requirements.
    """
    sets = chapter_spec.get("sets", [])
    if not sets:
        return []

    # --- Compute the union of all theme sets across the chapter ---
    # We'll fetch every puzzle that has ALL themes from at least one set.
    # Easiest: collect unique (frozenset(themes)) groups and for each group
    # issue one tiny inner query, then UNION ALL — but that's still N queries.
    #
    # Better: Collect ALL unique themes across ALL sets, fetch puzzles that
    # have AT LEAST ONE of those themes (very wide net), then filter per-set
    # in Python.  This is ONE query regardless of the number of sets.

    all_themes: set[str] = set()
    for s in sets:
        all_themes.update(s.get("themes", []))

    # Compute widest numeric bounds across all sets for pre-filtering
    min_rating, max_rating = None, None
    min_plays = global_filters.get("min_plays", 0)
    min_popularity = global_filters.get("min_popularity", 0)

    sides: set[str] = set()
    first_move_pieces: set[str] = set()
    openings: list[str] = []

    for s in sets:
        rng = s.get("rating")
        if rng:
            lo, hi = rng
            min_rating = lo if min_rating is None else min(min_rating, lo)
            max_rating = hi if max_rating is None else max(max_rating, hi)
        if s.get("side_to_move"):
            sides.add(SIDE_MAP.get(str(s["side_to_move"]).lower(), s["side_to_move"]))
        if s.get("first_move_piece"):
            first_move_pieces.add(str(s["first_move_piece"]).upper())
        if s.get("opening"):
            openings.append(s["opening"])
        mp = s.get("min_plays", min_plays)
        min_plays = min(min_plays, mp)
        mpop = s.get("min_popularity", min_popularity)
        min_popularity = min(min_popularity, mpop)

    params: list = []

    # Build FROM: join puzzle_themes once to find puzzles that have ANY of
    # the required themes, using GROUP BY to count distinct matching themes.
    # We do NOT enforce AND-logic here — that's done per-set in Python.
    theme_placeholders = ",".join("?" for _ in all_themes)
    params.extend(sorted(all_themes))

    where_parts: list[str] = []

    if min_rating is not None:
        where_parts.append("p.rating >= ?")
        params.append(min_rating)
    if max_rating is not None:
        where_parts.append("p.rating <= ?")
        params.append(max_rating)
    if sides:
        side_placeholders = ",".join("?" for _ in sides)
        where_parts.append(f"p.side_to_move IN ({side_placeholders})")
        params.extend(sorted(sides))
    if first_move_pieces:
        fmp_placeholders = ",".join("?" for _ in first_move_pieces)
        where_parts.append(f"p.first_move_piece IN ({fmp_placeholders})")
        params.extend(sorted(first_move_pieces))
    if min_plays > 0:
        where_parts.append("p.nb_plays >= ?")
        params.append(min_plays)
    if min_popularity > 0:
        where_parts.append("p.popularity >= ?")
        params.append(min_popularity)
    # opening filters: must satisfy at least one opening substring
    if openings:
        opening_parts = " OR ".join("p.opening_tags LIKE ?" for _ in openings)
        where_parts.append(f"({opening_parts})")
        params.extend(f"%{o}%" for o in openings)

    where_clause = ("WHERE " + "\n  AND ".join(where_parts)) if where_parts else ""

    sql = f"""
SELECT p.puzzle_id, p.fen, p.moves, p.move_count,
       p.rating, p.rating_deviation, p.popularity, p.nb_plays,
       p.game_url, p.opening_tags, p.side_to_move, p.first_move_piece,
       p.display_fen,
       group_concat(pt.theme, ' ') AS all_themes
FROM puzzles p
JOIN puzzle_themes pt ON pt.puzzle_id = p.puzzle_id
  AND pt.theme IN ({theme_placeholders})
{where_clause}
GROUP BY p.puzzle_id
""".strip()

    cur = conn.execute(sql, params)
    rows = cur.fetchall()

    # Convert to dicts; split themes string into a set for fast membership checks
    puzzles: list[dict] = []
    for row in rows:
        p = dict(zip(COLUMNS, row[:13]))
        p["moves"] = p["moves"].split() if p["moves"] else []
        p["_themes"] = set(row[13].split()) if row[13] else set()
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


def apply_set_filter(candidates: list[dict], set_spec: dict, global_filters: dict) -> list[dict]:
    """Filter candidates to those matching set_spec, sort, and take count."""
    themes = set(set_spec.get("themes", []))
    side_to_move = set_spec.get("side_to_move")
    rating_range = set_spec.get("rating")
    mate_in = set_spec.get("mate_in")
    opening = set_spec.get("opening")
    first_move_piece = set_spec.get("first_move_piece")
    count = set_spec.get("count")
    sort_specs = set_spec.get("sort", [{"field": "popularity", "order": "desc"}])

    min_plays = set_spec.get("min_plays", global_filters.get("min_plays", 0))
    min_popularity = set_spec.get("min_popularity", global_filters.get("min_popularity", 0))

    # Build required mateIn theme tag(s) if mate_in is specified
    mate_in_themes: set[str] = set()
    if mate_in is not None:
        if isinstance(mate_in, list):
            mate_in_themes = {f"mateIn{n}" for n in mate_in}
        else:
            mate_in_themes = {f"mateIn{mate_in}"}

    db_side = SIDE_MAP.get(str(side_to_move).lower(), side_to_move) if side_to_move else None

    filtered = []
    for p in candidates:
        puzzle_themes = p.get("_themes", set())

        # AND-logic: puzzle must have ALL required themes
        if themes and not themes.issubset(puzzle_themes):
            continue
        if db_side and p.get("side_to_move") != db_side:
            continue
        if rating_range:
            lo, hi = rating_range
            r = p.get("rating", 0)
            if r < lo or r > hi:
                continue
        if mate_in_themes and not mate_in_themes.intersection(puzzle_themes):
            continue
        if opening and not (p.get("opening_tags") or "").find(opening) >= 0:
            continue
        if first_move_piece and p.get("first_move_piece") != str(first_move_piece).upper():
            continue
        if min_plays > 0 and (p.get("nb_plays") or 0) < min_plays:
            continue
        if min_popularity > 0 and (p.get("popularity") or 0) < min_popularity:
            continue

        filtered.append(p)

    # Sort by set-level sort spec (determines which N are selected)
    filtered.sort(key=python_sort_key(sort_specs))

    # Take exactly count, or all if count is None
    return filtered[:count] if count is not None else filtered


def build_chapter(chapter_spec: dict, global_filters: dict, conn: sqlite3.Connection) -> dict:
    """Fetch all candidates for a chapter in ONE query, apply per-set selection in Python."""
    title = chapter_spec["title"]
    print(f"  Chapter: {title}", end="", flush=True)

    # Single DB round-trip for the entire chapter
    candidates = fetch_chapter_candidates(chapter_spec, global_filters, conn)
    print(f" — {len(candidates):,} candidates fetched")

    all_puzzles: list[dict] = []
    seen_ids: set[str] = set()

    for i, set_spec in enumerate(chapter_spec.get("sets", [])):
        selected = apply_set_filter(candidates, set_spec, global_filters)
        added = 0
        for p in selected:
            if p["puzzle_id"] not in seen_ids:
                seen_ids.add(p["puzzle_id"])
                # Strip the internal _themes key before storing
                clean = {k: v for k, v in p.items() if not k.startswith("_")}
                all_puzzles.append(clean)
                added += 1

    # Apply chapter-level sort
    chapter_sort = chapter_spec.get("sort")
    if chapter_sort:
        all_puzzles.sort(key=python_sort_key(chapter_sort))

    # Split into white/black groups
    white_puzzles = [p for p in all_puzzles if p.get("side_to_move") == "w"]
    black_puzzles = [p for p in all_puzzles if p.get("side_to_move") == "b"]

    print(f"    → {len(all_puzzles)} puzzles selected ({len(white_puzzles)} white, {len(black_puzzles)} black)")

    return {
        "title": title,
        "puzzle_count": len(all_puzzles),
        "white_to_move_count": len(white_puzzles),
        "black_to_move_count": len(black_puzzles),
        "puzzles": all_puzzles,
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
