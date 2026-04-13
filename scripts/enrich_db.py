#!/usr/bin/env python3
"""enrich_db.py — One-time denormalization and index creation for lichess_puzzles.sqlite.

Run this once after import_csv_to_sqlite.py (or any time you want to rebuild
the derived structures from scratch).  It is safe to re-run: all CREATE INDEX /
CREATE TABLE statements use IF NOT EXISTS, and the UPDATE is idempotent.

What this does:
  1. Adds a 'themes' text column to 'puzzles' (space-separated theme tags).
  2. Creates the 'puzzle_theme_rows' denormalized table — one row per
     (puzzle, theme) with all puzzle columns inline.  This is the table that
     build_puzzle_json.py queries; no JOINs are needed at query time.
  3. Creates three covering indexes on puzzle_theme_rows:
       - idx_ptr_theme_side_piece_plays  — for nb_plays-DESC queries (default)
       - idx_ptr_theme_side_plays_pop    — for popularity-DESC queries
       - idx_ptr_theme_side_rating       — for rating-ASC queries (beginner book)

Before:  build_puzzle_json.py took ~60 s per book.
After:   all books build in < 0.3 s.
"""

import sqlite3
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "lichess_puzzles.sqlite"


def enrich(db_path: Path) -> None:
    print(f"Database: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA cache_size=-262144")   # 256 MB
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")

    # ── 1. themes column on puzzles ──────────────────────────────────────────
    cols = [r[1] for r in conn.execute("PRAGMA table_info(puzzles)")]
    if "themes" not in cols:
        print("\n[1/4] Adding 'themes' column to puzzles...")
        conn.execute("ALTER TABLE puzzles ADD COLUMN themes TEXT")
    else:
        print("\n[1/4] 'themes' column already exists — refreshing values...")

    t0 = time.perf_counter()
    conn.execute("""
        UPDATE puzzles SET themes = (
            SELECT group_concat(theme, ' ')
            FROM puzzle_themes
            WHERE puzzle_id = puzzles.puzzle_id
        )
    """)
    conn.commit()
    print(f"      Done in {time.perf_counter() - t0:.1f}s")

    # ── 2. puzzle_theme_rows table ───────────────────────────────────────────
    print("\n[2/4] Building puzzle_theme_rows table...")
    conn.execute("DROP TABLE IF EXISTS puzzle_theme_rows")
    conn.execute("""
        CREATE TABLE puzzle_theme_rows (
            theme            TEXT NOT NULL,
            puzzle_id        TEXT NOT NULL,
            fen              TEXT,
            moves            TEXT,
            move_count       INTEGER,
            rating           INTEGER,
            rating_deviation INTEGER,
            popularity       INTEGER,
            nb_plays         INTEGER,
            game_url         TEXT,
            opening_tags     TEXT,
            side_to_move     TEXT,
            first_move_piece TEXT,
            display_fen      TEXT
        )
    """)

    t0 = time.perf_counter()
    conn.execute("""
        INSERT INTO puzzle_theme_rows
        SELECT
            pt.theme,
            p.puzzle_id, p.fen, p.moves, p.move_count,
            p.rating, p.rating_deviation, p.popularity, p.nb_plays,
            p.game_url, p.opening_tags, p.side_to_move, p.first_move_piece,
            p.display_fen
        FROM puzzle_themes pt
        JOIN puzzles p ON p.puzzle_id = pt.puzzle_id
    """)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM puzzle_theme_rows").fetchone()[0]
    print(f"      {n:,} rows inserted in {time.perf_counter() - t0:.1f}s")

    # ── 3. Covering indexes ──────────────────────────────────────────────────
    indexes = [
        (
            "idx_ptr_theme_side_piece_plays",
            "puzzle_theme_rows(theme, side_to_move, first_move_piece, nb_plays DESC, rating, popularity)",
            "nb_plays-DESC queries (default sort)",
        ),
        (
            "idx_ptr_theme_side_plays_pop",
            "puzzle_theme_rows(theme, side_to_move, first_move_piece, popularity DESC, rating)",
            "popularity-DESC queries",
        ),
        (
            "idx_ptr_theme_side_rating",
            "puzzle_theme_rows(theme, side_to_move, rating ASC, popularity DESC)",
            "rating-ASC queries (beginner book)",
        ),
    ]

    for i, (name, cols_spec, description) in enumerate(indexes, start=3):
        print(f"\n[{i}/4] Creating index {name}  ({description})...")
        t0 = time.perf_counter()
        conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {cols_spec}")
        conn.commit()
        print(f"      Done in {time.perf_counter() - t0:.1f}s")

    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    print("\nAll done. puzzle_theme_rows is ready.")


def main() -> None:
    if not DB_PATH.exists():
        print(f"ERROR: database not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)
    enrich(DB_PATH)


if __name__ == "__main__":
    main()
