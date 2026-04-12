#!/usr/bin/env python3
"""
Enrich lichess_puzzles.sqlite with derived columns:
  - side_to_move:     'w' or 'b', from the FEN active-colour field
  - first_move_piece: 'K','Q','R','B','N','P' — the piece type of the first move
                      (after the opponent's setup move, i.e. from the displayed position)

Both are derived purely from existing data — no external libraries needed for
side_to_move; first_move_piece uses python-chess to read the piece on the
from-square of the first remaining move (moves[0] after the initial push).

Run once to add the columns and populate them. Safe to re-run (skips if already done).
"""
import sqlite3
from pathlib import Path
from typing import Optional
import chess

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "lichess_puzzles.sqlite"
BATCH_SIZE = 50_000


def piece_symbol(piece: chess.Piece) -> str:
    """Return uppercase piece letter: K Q R B N P"""
    return piece.symbol().upper()


def derive_fields(fen: str, moves_str: str) -> tuple[str, Optional[str]]:
    """
    Returns (side_to_move, first_move_piece).
    side_to_move: 'w' or 'b' — whose turn it is in the displayed position
                  (i.e. AFTER the opponent's first move from the raw FEN).
    first_move_piece: piece letter of the move the solver plays, or None on error.

    The raw DB FEN is the position BEFORE the opponent's forcing move.
    moves[0] is the opponent's move; moves[1] is the solver's first move.
    """
    # side_to_move: the side that the SOLVER plays (i.e. whose turn it is in
    # the displayed puzzle position).
    #
    # Lichess stores the FEN one half-move BEFORE the puzzle starts: the raw
    # FEN is the position where the opponent is about to make their "blunder"
    # (moves[0]).  After that blunder the turn flips, so the solver's colour
    # is simply the OPPOSITE of the active colour in the raw FEN.
    #
    # We derive this by flipping the FEN's active-colour field rather than
    # actually pushing the move through python-chess — it's equivalent and
    # avoids the overhead for this particular field.
    fen_side = fen.split()[1]  # 'w' or 'b' — the side that plays moves[0]
    side_to_move = 'b' if fen_side == 'w' else 'w'  # solver is the OTHER side

    # first_move_piece: the piece the solver moves (moves[1] in the raw list)
    moves = moves_str.split()
    if len(moves) < 2:
        return side_to_move, None

    try:
        board = chess.Board(fen)
        # push the opponent's move (moves[0])
        board.push(chess.Move.from_uci(moves[0]))
        # the solver's first move is moves[1]
        solver_move = chess.Move.from_uci(moves[1])
        piece = board.piece_at(solver_move.from_square)
        if piece is None:
            return side_to_move, None
        return side_to_move, piece_symbol(piece)
    except Exception:
        return side_to_move, None


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    cur = conn.cursor()

    # Add columns if they don't exist
    existing = {row[1] for row in cur.execute("PRAGMA table_info(puzzles)")}
    if "side_to_move" not in existing:
        print("Adding column: side_to_move")
        cur.execute("ALTER TABLE puzzles ADD COLUMN side_to_move TEXT")
    else:
        print("Column side_to_move already exists")

    if "first_move_piece" not in existing:
        print("Adding column: first_move_piece")
        cur.execute("ALTER TABLE puzzles ADD COLUMN first_move_piece TEXT")
    else:
        print("Column first_move_piece already exists")

    conn.commit()

    # Count rows needing update
    cur.execute("SELECT COUNT(*) FROM puzzles WHERE side_to_move IS NULL")
    remaining = cur.fetchone()[0]
    print(f"Rows to update: {remaining:,}")

    if remaining == 0:
        print("Nothing to do.")
        conn.close()
        return

    processed = 0
    while True:
        cur.execute(
            "SELECT puzzle_id, fen, moves FROM puzzles WHERE side_to_move IS NULL LIMIT ?",
            (BATCH_SIZE,),
        )
        rows = cur.fetchall()
        if not rows:
            break

        updates = []
        for puzzle_id, fen, moves_str in rows:
            side, piece = derive_fields(fen, moves_str or "")
            updates.append((side, piece, puzzle_id))

        cur.executemany(
            "UPDATE puzzles SET side_to_move=?, first_move_piece=? WHERE puzzle_id=?",
            updates,
        )
        conn.commit()
        processed += len(rows)
        print(f"  {processed:,} / {remaining:,} updated...")

    # Add indexes for fast filtering
    print("Creating indexes...")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_side_to_move ON puzzles(side_to_move)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_first_move_piece ON puzzles(first_move_piece)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rating ON puzzles(rating)")
    conn.commit()

    print("Done.")
    conn.close()


if __name__ == "__main__":
    main()
