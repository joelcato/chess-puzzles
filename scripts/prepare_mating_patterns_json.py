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
DEFAULT_PUZZLES_PER_CHAPTER = 104
MIN_CHAPTER_RATING = 600

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

RATING_BANDS = [
    (600, 799),
    (800, 999),
    (1000, 1199),
    (1200, 1399),
    (1400, 1599),
    (1600, 1799),
    (1800, 1999),
    (2000, 2199),
    (2200, 2399),
    (2400, 2599),
    (2600, 2799),
    (2800, 2999),
    (3000, 3199),
]

RATING_BAND_LABELS = [f"{low}-{high}" for low, high in RATING_BANDS]

# Lower bands we consider for guaranteeing early mate-in-1s
LOWER_BANDS = ["600-799", "800-999", "1000-1199"]

SELECTION_QUOTAS: dict[str, dict[str, dict[str, int]]] = {
    "Back Rank Mate": {
        "white": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 4, "1800-1999": 4, "2000-2199": 5, "2200-2399": 5, "2400-2599": 10, "2600-2799": 4},
        "black": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 4, "1800-1999": 4, "2000-2199": 5, "2200-2399": 5, "2400-2599": 17, "2600-2799": 1},
    },
    "Double Bishop Mate": {
        "white": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 9, "1600-1799": 9, "1800-1999": 11, "2000-2199": 7, "2200-2399": 3, "2400-2599": 1},
        "black": {"800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 9, "1800-1999": 12, "2000-2199": 5, "2200-2399": 4, "2400-2599": 2},
    },
    "Boden's Mate": {
        "white": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 9, "1800-1999": 10, "2000-2199": 9, "2200-2399": 4},
        "black": {"800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 8, "1800-1999": 9, "2000-2199": 15, "2200-2399": 4},
    },
    "Opera Mate": {
        "white": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 5, "1800-1999": 5, "2000-2199": 5, "2200-2399": 5, "2400-2599": 6, "2600-2799": 10},
        "black": {"800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 5, "1800-1999": 6, "2000-2199": 6, "2200-2399": 6, "2400-2599": 6, "2600-2799": 3},
    },
    "Pillsbury's Mate": {
        "white": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 5, "1800-1999": 5, "2000-2199": 5, "2200-2399": 5, "2400-2599": 5, "2600-2799": 9, "2800-2999": 2},
        "black": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 4, "1800-1999": 4, "2000-2199": 4, "2200-2399": 5, "2400-2599": 5, "2600-2799": 10},
    },
    "Smothered Mate": {
        "white": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 10, "1800-1999": 10, "2000-2199": 13, "2200-2399": 2, "2600-2799": 1},
        "black": {"800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 8, "1800-1999": 8, "2000-2199": 11, "2200-2399": 5},
    },
    "Arabian Mate": {
        "white": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 5, "1800-1999": 5, "2000-2199": 6, "2200-2399": 6, "2400-2599": 5, "2600-2799": 4, "2800-2999": 1},
        "black": {"800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 6, "1800-1999": 6, "2000-2199": 6, "2200-2399": 6, "2400-2599": 12},
    },
    "Epaulette Mate": {
        "white": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 5, "1800-1999": 5, "2000-2199": 5, "2200-2399": 4, "2400-2599": 4, "2600-2799": 9},
        "black": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 4, "1800-1999": 4, "2000-2199": 4, "2200-2399": 5, "2400-2599": 5, "2600-2799": 13, "2800-2999": 1},
    },
    "Anastasia's Mate": {
        "white": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 5, "1800-1999": 6, "2000-2199": 6, "2200-2399": 19, "2400-2599": 3, "2600-2799": 1},
        "black": {"800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 5, "1800-1999": 5, "2000-2199": 6, "2200-2399": 7, "2400-2599": 5},
    },
    "Hook Mate": {
        "white": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 4, "1800-1999": 4, "2000-2199": 5, "2200-2399": 5, "2400-2599": 17, "2600-2799": 1},
        "black": {"800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 4, "1800-1999": 5, "2000-2199": 5, "2200-2399": 5, "2400-2599": 10, "2600-2799": 3},
    },
    "Swallow's Tail Mate": {
        "white": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 4, "1800-1999": 4, "2000-2199": 4, "2200-2399": 5, "2400-2599": 15, "2600-2799": 4},
        "black": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 3, "1800-1999": 3, "2000-2199": 4, "2200-2399": 4, "2400-2599": 15, "2600-2799": 3},
    },
    "Blind Swine Mate": {
        "white": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 5, "1800-1999": 5, "2000-2199": 5, "2200-2399": 6, "2400-2599": 14, "2600-2799": 1},
        "black": {"800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 6, "1800-1999": 6, "2000-2199": 6, "2200-2399": 6, "2400-2599": 6, "2600-2799": 2},
    },
    "Corner Mate": {
        "white": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 5, "1800-1999": 5, "2000-2199": 5, "2200-2399": 6, "2400-2599": 6, "2600-2799": 12, "3000-3199": 1},
        "black": {"800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 4, "1800-1999": 5, "2000-2199": 5, "2200-2399": 5, "2400-2599": 5, "2600-2799": 3, "2800-2999": 1},
    },
    "Dovetail Mate": {
        "white": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 4, "1800-1999": 5, "2000-2199": 5, "2200-2399": 5, "2400-2599": 12, "2600-2799": 5},
        "black": {"800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 5, "1800-1999": 5, "2000-2199": 5, "2200-2399": 6, "2400-2599": 6, "2600-2799": 4, "2800-2999": 1},
    },
    "Morphy's Mate": {
        "white": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 2, "1800-1999": 3, "2000-2199": 3, "2200-2399": 3, "2400-2599": 17, "2600-2799": 3, "2800-2999": 1},
        "black": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 3, "1800-1999": 3, "2000-2199": 3, "2200-2399": 3, "2400-2599": 22, "2600-2799": 2},
    },
    "Triangle Mate": {
        "white": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 4, "1800-1999": 5, "2000-2199": 5, "2200-2399": 5, "2400-2599": 11, "2600-2799": 6},
        "black": {"800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 4, "1800-1999": 4, "2000-2199": 4, "2200-2399": 4, "2400-2599": 14, "2600-2799": 2},
    },
    "Kill Box Mate": {
        "white": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 3, "1800-1999": 3, "2000-2199": 3, "2200-2399": 3, "2400-2599": 17, "2600-2799": 6, "2800-2999": 1},
        "black": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 3, "1800-1999": 3, "2000-2199": 3, "2200-2399": 4, "2400-2599": 14, "2600-2799": 5},
    },
    "Vukovic Mate": {
        "white": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 5, "1800-1999": 5, "2000-2199": 5, "2200-2399": 15, "2400-2599": 6},
        "black": {"800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 5, "1800-1999": 5, "2000-2199": 5, "2200-2399": 11, "2400-2599": 5, "2600-2799": 1},
    },
    "Balestra Mate": {
        "white": {"600-799": 4, "800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 6, "1800-1999": 6, "2000-2199": 6, "2200-2399": 15, "2400-2599": 2, "2800-2999": 1},
        "black": {"800-999": 4, "1000-1199": 4, "1200-1399": 4, "1400-1599": 4, "1600-1799": 5, "1800-1999": 5, "2000-2199": 5, "2200-2399": 12, "2400-2599": 3, "2600-2799": 2},
    },
}


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

    # Record the remaining plies (moves) from the displayed position and
    # compute a `mate_in` value in full moves (1 = mate-in-1, 2 = mate-in-2, ...).
    # `moves` is the full moves list; the displayed position is after the first
    # move (we pushed it above), so remaining plies = len(moves) - 1.
    full_move_count = len(moves)
    remaining_plies = max(0, full_move_count - 1)
    mate_in = (remaining_plies + 1) // 2 if remaining_plies > 0 else 0

    return {
        "id": row["PuzzleId"],
        "fen": board.fen(),
        # keep the remaining moves (after the first push) for rendering/solutions
    "moves": moves[1:],
    # store remaining plies and derived mate-in-N (from displayed position)
    "remaining_plies": remaining_plies,
    "mate_in": mate_in,
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


def puzzle_sort_key_low_to_high(p: dict) -> tuple:
    return (
        p["rating"],
        len(p["moves"]),
        -p["popularity"],
        -p["nb_plays"],
        p["id"],
    )


def puzzle_sort_key_high_to_low(p: dict) -> tuple:
    return (
        -p["rating"],
        len(p["moves"]),
        -p["popularity"],
        -p["nb_plays"],
        p["id"],
    )


def puzzle_sort_key_chapter_order(p: dict) -> tuple:
    """Sort puzzles for chapter ordering according to requested hierarchy:
    1. Theme (chapters are already per-theme)
    2. Color: Black first, then White
    3. Mate-tier: mate-in-1, mate-in-2, then mate-in-3+
    4. Rating ascending (easier -> harder)
    5. Popularity descending
    """
    # determine side order: prefer black before white
    try:
        side = chess.Board(p["fen"]).turn
    except Exception:
        # fallback to stored side_to_move if present
        side = chess.WHITE if p.get("side_to_move") == "white" else chess.BLACK
    side_rank = 0 if side == chess.BLACK else 1

    # mate-tier from explicit tags when available
    themes = {t.lower() for t in p.get("themes", [])}
    if "matein1" in themes:
        tier = 0
    elif "matein2" in themes:
        tier = 1
    else:
        tier = 2

    return (side_rank, tier, p["rating"], -p["popularity"], p["id"])


def rating_band_label(rating: int) -> Optional[str]:
    if rating < MIN_CHAPTER_RATING:
        return None
    for low, high in RATING_BANDS:
        if low <= rating <= high:
            return f"{low}-{high}"
    if rating >= RATING_BANDS[-1][0]:
        low, high = RATING_BANDS[-1]
        return f"{low}-{high}"
    return None


def select_by_band_quota(
    candidates: list[dict],
    chapter_label: str,
    side: str,
    quotas_override: Optional[dict] = None,
    already_selected_ids: Optional[set] = None,
) -> list[dict]:
    """Select puzzles to satisfy per-band quotas.

    Parameters:
    - candidates: list of puzzle dicts for this side
    - chapter_label, side: used for default quotas lookup
    - quotas_override: optional dict mapping band->quota to use instead of SELECTION_QUOTAS
    - already_selected_ids: optional set of puzzle ids to skip (already chosen elsewhere)
    """
    quotas = quotas_override if quotas_override is not None else SELECTION_QUOTAS[chapter_label][side]
    selected: list[dict] = []
    selected_ids: set[str] = set(already_selected_ids or set())
    by_band: dict[str, list[dict]] = defaultdict(list)

    eligible = [p for p in candidates if p["rating"] >= MIN_CHAPTER_RATING and p["id"] not in selected_ids]
    for puzzle in sorted(eligible, key=puzzle_sort_key_high_to_low):
        band = rating_band_label(puzzle["rating"])
        if band is not None:
            by_band[band].append(puzzle)

    shortages: list[tuple[str, int, int]] = []
    for band in RATING_BAND_LABELS:
        quota = quotas.get(band, 0)
        if quota <= 0:
            continue
        pool = by_band.get(band, [])
        # Select by popularity first within the band, breaking ties by rating,
        # then by nb_plays and id to be deterministic.
        pool_sorted = sorted(
            pool,
            key=lambda p: (
                -p["popularity"],
                -p["rating"],
                -p["nb_plays"],
                p["id"],
            ),
        )
        taken = 0
        for puzzle in pool_sorted:
            if puzzle["id"] in selected_ids:
                continue
            selected.append(puzzle)
            selected_ids.add(puzzle["id"])
            taken += 1
            if taken == quota:
                break
        if taken < quota:
            shortages.append((band, quota, taken))

    if shortages:
        details = ", ".join(f"{band}: wanted {quota}, got {taken}" for band, quota, taken in shortages)
        raise RuntimeError(f"Quota shortfall for {chapter_label} ({side}): {details}")

    # For chapter output, prioritize mate-in-1 then mate-in-2, then others by rating
    return sorted(selected, key=puzzle_sort_key_chapter_order)


def select_chapter_puzzles(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    raise RuntimeError("select_chapter_puzzles now requires a chapter label")


def select_chapter_puzzles_for_spec(chapter_label: str, candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    white_candidates = [puzzle for puzzle in candidates if chess.Board(puzzle["fen"]).turn == chess.WHITE]
    black_candidates = [puzzle for puzzle in candidates if chess.Board(puzzle["fen"]).turn == chess.BLACK]
    def band_of(p):
        return rating_band_label(p["rating"])

    # Step 1: Select puzzles according to per-band quotas for each side.
    white_selected = select_by_band_quota(white_candidates, chapter_label, "white")
    black_selected = select_by_band_quota(black_candidates, chapter_label, "black")

    # Combine selections but keep color groups separate for now
    selected = white_selected + black_selected
    expected_count = sum(SELECTION_QUOTAS[chapter_label]["white"].values()) + sum(SELECTION_QUOTAS[chapter_label]["black"].values())

    # Step 1b: Ensure at least 4 mate-in-1 puzzles per color (use matein1 tag from CSV themes)
    def count_m1(puzzles: list[dict]) -> int:
        return sum(1 for p in puzzles if "matein1" in {t.lower() for t in p.get("themes", [])})

    # helper to find replacement candidates for a given color
    def find_m1_candidates(pool_candidates: list[dict], already_ids: set) -> list[dict]:
        cands = [p for p in pool_candidates if "matein1" in {t.lower() for t in p.get("themes", [])} and p["id"] not in already_ids]
        # sort by popularity desc, rating desc, nb_plays desc
        return sorted(cands, key=lambda p: (-p["popularity"], -p["rating"], -p["nb_plays"], p["id"]))

    selected_ids = {p["id"] for p in selected}

    # For each color, if fewer than 4 mate-in-1s were selected, replace the easiest
    # selected puzzles of that color with the top mate-in-1 candidates by popularity.
    for color, sel_list, pool_candidates in (
        ("white", white_selected, white_candidates),
        ("black", black_selected, black_candidates),
    ):
        m1_count = count_m1(sel_list)
        if m1_count >= 4:
            continue
        deficit = 4 - m1_count
        m1_pool = find_m1_candidates(pool_candidates, selected_ids)
        if not m1_pool:
            continue
        # select up to 'deficit' replacements
        replacements = m1_pool[:deficit]
        # choose easiest puzzles currently selected in this color to replace (rating ascending)
        easiest = sorted(sel_list, key=lambda p: p["rating"])[:len(replacements)]
        # perform swap: remove easiest from sel_list and selected_ids, add replacements
        for e in easiest:
            try:
                sel_list.remove(e)
            except ValueError:
                pass
            selected_ids.discard(e["id"])
        for r in replacements:
            sel_list.append(r)
            selected_ids.add(r["id"])

    # rebuild combined selected list (white then black to preserve per-side quotas)
    selected = white_selected + black_selected

    # Step 1c: Ensure the first 4 puzzles of the chapter are mate-in-1s (prefer lower bands).
    # From the selected set, pick the top mate-in-1 puzzles in LOWER_BANDS by popularity,
    # breaking ties by rating then nb_plays, and move them to the front of the chapter.
    m1_candidates = [p for p in selected if 'matein1' in {t.lower() for t in p.get('themes', [])}]
    m1_lower = [p for p in m1_candidates if band_of(p) in LOWER_BANDS]
    def m1_sort_key(p):
        return (-p['popularity'], -p['rating'], -p['nb_plays'], p['id'])
    chosen = []
    # prefer lower-band m1s first
    m1_lower_sorted = sorted(m1_lower, key=m1_sort_key)
    chosen.extend(m1_lower_sorted[:4])
    if len(chosen) < 4:
        # fill remaining from other m1 candidates
        remaining_pool = [p for p in m1_candidates if p not in chosen]
        remaining_sorted = sorted(remaining_pool, key=m1_sort_key)
        chosen.extend(remaining_sorted[: (4 - len(chosen)) ])
    # if we found any, move them to the front preserving the chosen order
    if chosen:
        chosen_ids = {p['id'] for p in chosen}
        rest = [p for p in selected if p['id'] not in chosen_ids]
        selected = chosen + rest

    # Verify 4-puzzle page divisibility per color (selections were constructed to respect this)
    if (len(white_selected) % 4) != 0 or (len(black_selected) % 4) != 0:
        raise RuntimeError(f"Selection for {chapter_label} does not preserve 4-puzzle page divisibility after adjustments.")

    # If selection came up short (rare), fill remaining slots from the leftover
    # candidate pools by popularity while preserving color counts as much as possible.
    if len(selected) != expected_count:
        missing = expected_count - len(selected)
        # expected per-side totals from original quotas
        expected_white = sum(SELECTION_QUOTAS[chapter_label]["white"].values())
        expected_black = sum(SELECTION_QUOTAS[chapter_label]["black"].values())
        current_white = sum(1 for p in selected if chess.Board(p["fen"]).turn == chess.WHITE)
        current_black = sum(1 for p in selected if chess.Board(p["fen"]).turn == chess.BLACK)

        # prepare pools
        rem_white_pool = [p for p in white_candidates if p["id"] not in selected_ids and p["id"] not in {q['id'] for q in white_selected}]
        rem_black_pool = [p for p in black_candidates if p["id"] not in selected_ids and p["id"] not in {q['id'] for q in black_selected}]
        rem_white_pool = sorted(rem_white_pool, key=lambda p: (-p["popularity"], -p["rating"], -p["nb_plays"], p["id"]))
        rem_black_pool = sorted(rem_black_pool, key=lambda p: (-p["popularity"], -p["rating"], -p["nb_plays"], p["id"]))

        # fill whites up to expected_white
        while missing > 0 and current_white < expected_white and rem_white_pool:
            p = rem_white_pool.pop(0)
            selected.append(p)
            current_white += 1
            missing -= 1

        # fill blacks up to expected_black
        while missing > 0 and current_black < expected_black and rem_black_pool:
            p = rem_black_pool.pop(0)
            selected.append(p)
            current_black += 1
            missing -= 1

        # if still missing, fill from any remaining candidates regardless of side
        combined = rem_white_pool + rem_black_pool
        combined = sorted(combined, key=lambda p: (-p["popularity"], -p["rating"], -p["nb_plays"], p["id"]))
        while missing > 0 and combined:
            p = combined.pop(0)
            selected.append(p)
            missing -= 1

        if len(selected) != expected_count:
            raise RuntimeError(f"Selection for {chapter_label} produced {len(selected)} puzzles instead of {expected_count} after fallback filling.")

    def band_counts(puzzles: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for band in RATING_BAND_LABELS:
            counts[band] = 0
        for puzzle in puzzles:
            band = rating_band_label(puzzle["rating"])
            if band is not None:
                counts[band] += 1
        return counts

    white_band_counts = band_counts(white_selected)
    black_band_counts = band_counts(black_selected)

    selection_report = [
        {
            "strategy": "explicit-band-quotas-top-rated-per-band",
            "candidate_count": len(candidates),
            "selected_count": len(selected),
            "white_to_move_count": len(white_selected),
            "black_to_move_count": len(black_selected),
            "selection_score": sum(puzzle["rating"] for puzzle in selected),
            "rating_floor": min((puzzle["rating"] for puzzle in selected), default=0),
            "min_chapter_rating": MIN_CHAPTER_RATING,
            "white_band_counts": white_band_counts,
            "black_band_counts": black_band_counts,
        }
    ]

    return selected, selection_report


def build_output() -> dict:
    candidates_by_theme = collect_candidates()
    chapters: list[dict] = []
    total_puzzles = 0

    for chapter_index, spec in enumerate(THEME_SPECS, start=1):
        chapter_candidates = candidates_by_theme.get(spec["slug"], [])
        selected, bucket_report = select_chapter_puzzles_for_spec(spec["label"], chapter_candidates)

        expected_count = sum(SELECTION_QUOTAS[spec["label"]]["white"].values()) + sum(SELECTION_QUOTAS[spec["label"]]["black"].values())

        if len(selected) < expected_count:
            raise RuntimeError(
                f"Theme {spec['slug']} only yielded {len(selected)} puzzles; expected {expected_count}."
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
        total_puzzles += len(puzzles)

    return {
        "title": "Chess Puzzle Book",
        "subtitle": "Mating Patterns",
        "author": "by Joel Cato",
        "puzzles_per_chapter": DEFAULT_PUZZLES_PER_CHAPTER,
        "total_puzzles": total_puzzles,
        "chapters": chapters,
    }


def main() -> None:
    output = build_output()
    OUTPUT_JSON.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Wrote {len(output['chapters'])} chapters to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()