import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

import chess


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

INPUT_CSV = DATA_DIR / "lichess_db_puzzle.csv"
OUTPUT_JSON = DATA_DIR / "mating_patterns_100_by_theme.json"

MIN_POPULARITY = 0
MIN_PLAYS = 50
PUZZLES_PER_CHAPTER = 100

THEME_SPECS = [
    {"slug": "backRankMate", "label": "Back Rank Mate"},
    {"slug": "doubleBishopMate", "label": "Double Bishop Mate"},
    {"slug": "bodenMate", "label": "Boden's Mate"},
    {"slug": "operaMate", "label": "Opera Mate"},
    {"slug": "pillsburysMate", "label": "Pillsbury's Mate"},
    {"slug": "smotheredMate", "label": "Smothered Mate"},
    {"slug": "arabianMate", "label": "Arabian Mate"},
    {"slug": "epauletteMate", "label": "Epaulette Mate"},
    {"slug": "anastasiaMate", "label": "Anastasia's Mate"},
    {"slug": "hookMate", "label": "Hook Mate"},
    {"slug": "swallowstailMate", "label": "Swallow's Tail Mate"},
    {"slug": "blindSwineMate", "label": "Blind Swine Mate"},
    {"slug": "cornerMate", "label": "Corner Mate"},
    {"slug": "dovetailMate", "label": "Dovetail Mate"},
    {"slug": "morphysMate", "label": "Morphy's Mate"},
    {"slug": "triangleMate", "label": "Triangle Mate"},
    {"slug": "killBoxMate", "label": "Kill Box Mate"},
    {"slug": "vukovicMate", "label": "Vukovic Mate"},
    {"slug": "balestraMate", "label": "Balestra Mate"},
]


def theme_lookup() -> dict[str, dict]:
    return {spec["slug"]: spec for spec in THEME_SPECS}


THEME_LOOKUP = theme_lookup()


def row_passes_baseline(row: dict) -> bool:
    popularity = int(float(row["Popularity"]))
    nb_plays = int(float(row["NbPlays"]))
    return popularity >= MIN_POPULARITY and nb_plays >= MIN_PLAYS


def transform_row(row: dict, theme_spec: dict) -> Optional[dict]:
    fen = row["FEN"]
    moves = row["Moves"].split()

    if not moves:
        return None

    board = chess.Board(fen)
    first_move = chess.Move.from_uci(moves[0])
    if first_move not in board.legal_moves:
        return None

    board.push(first_move)

    return {
        "id": row["PuzzleId"],
        "fen": board.fen(),
        "moves": moves[1:],
        "rating": int(float(row["Rating"])),
        "theme": theme_spec["slug"],
        "themes": row["Themes"].split(),
        "initialPly": 0,
        "sourceGameUrl": row["GameUrl"],
        "popularity": int(float(row["Popularity"])),
        "nb_plays": int(float(row["NbPlays"])),
    }


def collect_candidates() -> dict[str, list[dict]]:
    by_theme: dict[str, list[dict]] = defaultdict(list)

    with INPUT_CSV.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row_passes_baseline(row):
                continue

            row_themes = set(row["Themes"].split())
            matched_specs: dict[str, dict] = {}
            for theme in row_themes:
                spec = THEME_LOOKUP.get(theme)
                if spec is not None:
                    matched_specs[spec["slug"]] = spec

            if not matched_specs:
                continue

            for slug, spec in matched_specs.items():
                transformed = transform_row(row, spec)
                if transformed is None or not transformed["moves"]:
                    continue
                by_theme[slug].append(transformed)

    for slug, puzzles in by_theme.items():
        puzzles.sort(
            key=lambda p: (
                p["rating"],
                len(p["moves"]),
                -p["popularity"],
                -p["nb_plays"],
                p["id"],
            )
        )

    return by_theme


def select_chapter_puzzles(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    ranked = sorted(
        candidates,
        key=lambda p: (
            -p["rating"],
            len(p["moves"]),
            -p["popularity"],
            -p["nb_plays"],
            p["id"],
        ),
    )

    white_ranked = [
        puzzle
        for puzzle in ranked
        if chess.Board(puzzle["fen"]).turn == chess.WHITE
    ]
    black_ranked = [
        puzzle
        for puzzle in ranked
        if chess.Board(puzzle["fen"]).turn == chess.BLACK
    ]

    best_split: Optional[dict] = None
    for white_count in range(0, PUZZLES_PER_CHAPTER + 1, 4):
        black_count = PUZZLES_PER_CHAPTER - white_count
        if black_count % 4 != 0:
            continue
        if len(white_ranked) < white_count or len(black_ranked) < black_count:
            continue

        white_selected = white_ranked[:white_count]
        black_selected = black_ranked[:black_count]
        combined = white_selected + black_selected
        score = sum(puzzle["rating"] for puzzle in combined)

        split = {
            "white_count": white_count,
            "black_count": black_count,
            "score": score,
            "white_selected": white_selected,
            "black_selected": black_selected,
        }

        if best_split is None:
            best_split = split
            continue

        if split["score"] > best_split["score"]:
            best_split = split
            continue

        if split["score"] == best_split["score"]:
            white_rating_floor = min(
                (puzzle["rating"] for puzzle in split["white_selected"]),
                default=float("inf"),
            )
            black_rating_floor = min(
                (puzzle["rating"] for puzzle in split["black_selected"]),
                default=float("inf"),
            )
            best_white_rating_floor = min(
                (puzzle["rating"] for puzzle in best_split["white_selected"]),
                default=float("inf"),
            )
            best_black_rating_floor = min(
                (puzzle["rating"] for puzzle in best_split["black_selected"]),
                default=float("inf"),
            )
            if (white_rating_floor, black_rating_floor, white_count) > (
                best_white_rating_floor,
                best_black_rating_floor,
                best_split["white_count"],
            ):
                best_split = split

    if best_split is None:
        raise RuntimeError(
            "Could not find a 100-puzzle white/black split with both counts divisible by 4."
        )

    white_selected = sorted(
        best_split["white_selected"],
        key=lambda p: (
            p["rating"],
            len(p["moves"]),
            -p["popularity"],
            -p["nb_plays"],
            p["id"],
        ),
    )
    black_selected = sorted(
        best_split["black_selected"],
        key=lambda p: (
            p["rating"],
            len(p["moves"]),
            -p["popularity"],
            -p["nb_plays"],
            p["id"],
        ),
    )
    selected = white_selected + black_selected

    selection_report = [
        {
            "strategy": "top-rated-feasible-side-split",
            "candidate_count": len(candidates),
            "selected_count": len(selected),
            "white_to_move_count": best_split["white_count"],
            "black_to_move_count": best_split["black_count"],
            "selection_score": best_split["score"],
        }
    ]

    return selected, selection_report


def build_output() -> dict:
    candidates_by_theme = collect_candidates()
    chapters: list[dict] = []

    for chapter_index, spec in enumerate(THEME_SPECS, start=1):
        chapter_candidates = candidates_by_theme.get(spec["slug"], [])
        selected, bucket_report = select_chapter_puzzles(chapter_candidates)

        if len(selected) < PUZZLES_PER_CHAPTER:
            raise RuntimeError(
                f"Theme {spec['slug']} only yielded {len(selected)} puzzles; expected {PUZZLES_PER_CHAPTER}."
            )

        puzzles = []
        white_to_move = []
        black_to_move = []
        for puzzle_index, puzzle in enumerate(selected, start=1):
            entry = {
                "id": puzzle["id"],
                "fen": puzzle["fen"],
                "moves": puzzle["moves"],
                "rating": puzzle["rating"],
                "theme": spec["slug"],
                "sourceGameUrl": puzzle["sourceGameUrl"],
                "chapter_index": chapter_index,
                "chapter_label": spec["label"],
                "chapter_slug": spec["slug"],
                "chapter_puzzle_index": puzzle_index,
                "side_to_move": "white" if chess.Board(puzzle["fen"]).turn == chess.WHITE else "black",
            }
            puzzles.append(entry)
            if entry["side_to_move"] == "white":
                white_to_move.append(entry)
            else:
                black_to_move.append(entry)

        chapters.append(
            {
                "slug": spec["slug"],
                "label": spec["label"],
                "chapter_index": chapter_index,
                "puzzle_count": len(puzzles),
                "white_to_move_count": len(white_to_move),
                "black_to_move_count": len(black_to_move),
                "selection_buckets": bucket_report,
                "puzzles": puzzles,
                "groups": {
                    "white_to_move": white_to_move,
                    "black_to_move": black_to_move,
                },
            }
        )

    return {
        "title": "Chess Puzzle Book",
        "subtitle": "Mating Patterns",
        "author": "by Joel Cato",
        "puzzles_per_chapter": PUZZLES_PER_CHAPTER,
        "chapters": chapters,
    }


def main() -> None:
    output = build_output()
    OUTPUT_JSON.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Wrote {len(output['chapters'])} chapters to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()