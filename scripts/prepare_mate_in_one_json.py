import csv
import json
from pathlib import Path

import chess

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

INPUT_CSV = DATA_DIR / "lichess_db_puzzle.csv"
OUTPUT_JSON = DATA_DIR / "mate_in_one_800.json"

MAX_RATING = 800
MIN_POPULARITY = 0
MIN_PLAYS = 50
MAX_PUZZLES = 600  # adjust as you like


def row_is_easy_mate_in_one(row: dict) -> bool:
    themes = row["Themes"].split()
    rating = int(float(row["Rating"]))
    popularity = int(float(row["Popularity"]))
    nb_plays = int(float(row["NbPlays"]))

    return (
        "mateIn1" in themes
        and rating <= MAX_RATING
        and popularity >= MIN_POPULARITY
        and nb_plays >= MIN_PLAYS
    )


def transform_row(row: dict) -> dict | None:
    """
    Lichess puzzle DB semantics:
    - FEN is BEFORE opponent makes their move
    - Moves are in UCI
    - The position to show is AFTER applying the first move
    - The solution begins with the second move
    """
    fen = row["FEN"]
    moves = row["Moves"].split()

    if not moves:
        return None

    board = chess.Board(fen)

    first_move = chess.Move.from_uci(moves[0])
    if first_move not in board.legal_moves:
        return None

    board.push(first_move)

    display_fen = board.fen()
    solution_moves = moves[1:]  # these are the moves the user solves from the shown position

    return {
        "id": row["PuzzleId"],
        "fen": display_fen,
        "moves": solution_moves,
        "rating": int(float(row["Rating"])),
        "theme": "mateIn1",
        "initialPly": 0,
        "sourceGameUrl": row["GameUrl"],
    }


def main():
    input_path = Path(INPUT_CSV)
    output_path = Path(OUTPUT_JSON)

    results = []

    with input_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            if not row_is_easy_mate_in_one(row):
                continue

            transformed = transform_row(row)
            if transformed is None:
                continue

            # For mate in 1, after applying the first move, we usually want exactly one move left.
            if len(transformed["moves"]) != 1:
                continue

            results.append(transformed)

            if len(results) >= MAX_PUZZLES:
                break

    output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {len(results)} puzzles to {output_path}")


if __name__ == "__main__":
    main()