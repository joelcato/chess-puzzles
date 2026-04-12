#!/usr/bin/env python3
"""enrich_puzzle_db_display_fen.py

Adds a `display_fen` column to the puzzles table.

display_fen = the FEN after the opponent's first move has been played —
i.e. the position the solver actually sees and must solve from.

This is the same as applying moves[0] to the original FEN.

Processes in batches of 50,000 with WAL journal mode for performance.
Safe to re-run: skips rows where display_fen IS NOT NULL, and skips rows
where it is already set.
"""

import sqlite3
import sys
from pathlib import Path

import chess

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "lichess_puzzles.sqlite"
BATCH_SIZE = 50_000


def main():
    print(f"Database: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-65536")  # 64 MB

    # Add column if it doesn't exist
    existing = [row[1] for row in conn.execute("PRAGMA table_info(puzzles)").fetchall()]
    if "display_fen" not in existing:
        print("Adding display_fen column...")
        conn.execute("ALTER TABLE puzzles ADD COLUMN display_fen TEXT")
        conn.commit()
    else:
        print("display_fen column already exists.")

    # Count remaining work
    remaining = conn.execute(
        "SELECT COUNT(*) FROM puzzles WHERE display_fen IS NULL"
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM puzzles").fetchone()[0]
    already_done = total - remaining
    print(f"Already done: {already_done:,} / {total:,}")
    print(f"Remaining:    {remaining:,}")

    if remaining == 0:
        print("Nothing to do.")
        conn.close()
        return

    processed = 0
    errors = 0

    while True:
        rows = conn.execute(
            "SELECT puzzle_id, fen, moves FROM puzzles WHERE display_fen IS NULL LIMIT ?",
            (BATCH_SIZE,),
        ).fetchall()
        if not rows:
            break

        updates = []
        for puzzle_id, fen, moves_str in rows:
            try:
                moves = moves_str.split() if moves_str else []
                if not moves:
                    # No moves at all — fall back to original FEN
                    updates.append((fen, puzzle_id))
                    continue
                board = chess.Board(fen)
                board.push(chess.Move.from_uci(moves[0]))
                updates.append((board.fen(), puzzle_id))
            except Exception as e:
                # On any parse error, store original FEN so row is not retried
                updates.append((fen, puzzle_id))
                errors += 1

        conn.executemany(
            "UPDATE puzzles SET display_fen = ? WHERE puzzle_id = ?",
            updates,
        )
        conn.commit()

        processed += len(rows)
        pct = 100 * (already_done + processed) / total
        print(f"  {already_done + processed:,} / {total:,} ({pct:.1f}%) — errors so far: {errors}")
        sys.stdout.flush()

    # Add index for future queries on display_fen (useful if anyone queries by FEN)
    existing_indexes = [
        row[1] for row in conn.execute(
            "SELECT type, name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    ]
    if "idx_display_fen" not in existing_indexes:
        print("Creating index on display_fen...")
        conn.execute("CREATE INDEX idx_display_fen ON puzzles(display_fen)")
        conn.commit()

    conn.close()
    print(f"\nDone. {processed:,} rows updated, {errors} errors.")


if __name__ == "__main__":
    main()
