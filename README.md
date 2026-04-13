# Chess Puzzles

This repo builds themed chess puzzle books from the Lichess puzzle database.

## Python environment

Use the project virtual environment:

```zsh
source .venv/bin/activate
```

## Build the SQLite database

### 1. Import the raw CSV

```zsh
python scripts/import_csv_to_sqlite.py
```

Creates `data/lichess_puzzles.sqlite` with:
- `puzzles` — one row per puzzle, with enriched columns (`side_to_move`, `first_move_piece`, `display_fen`)
- `puzzle_themes` — one row per `(puzzle, theme)` pair (normalized source of truth)

### 2. Enrich the database (one-time setup)

```zsh
python scripts/enrich_db.py
```

This performs all one-time denormalization and index creation:

- Adds `themes` text column to `puzzles` (space-separated, e.g. `"mateIn1 crushing short"`)
- Creates **`puzzle_theme_rows`** — a denormalized table with one row per `(puzzle, theme)`,
  all puzzle columns inline. This is the table all book-building queries run against —
  no JOINs needed at query time.
- Creates covering indexes:
  - `(theme, side_to_move, first_move_piece, nb_plays DESC, rating, popularity)` — for nb_plays-sorted queries
  - `(theme, side_to_move, first_move_piece, popularity DESC, rating)` — for popularity-sorted queries
  - `(theme, side_to_move, rating ASC, popularity DESC)` — for rating-sorted queries (beginner book)

After this step, book builds that previously took ~60 seconds run in under 0.3 seconds.

## Build a puzzle book

```zsh
python scripts/build_puzzle_json.py configs/mate_in_one_400.yaml
python scripts/build_puzzle_json.py configs/mate_in_one_800.yaml
python scripts/build_puzzle_json.py configs/mating_patterns_100_by_theme.yaml
```

Then generate LaTeX and compile:

```zsh
python scripts/generate_latex_from_json.py data/mate_in_one_400.json
cd output && /Library/TeX/texbin/pdflatex -interaction=nonstopmode mate_in_one_400.tex
```

## How the pipeline works

```
lichess_db_puzzle.csv
        │
        ▼
import_csv_to_sqlite.py  →  lichess_puzzles.sqlite (puzzles + puzzle_themes)
        │
        ▼
enrich_db.py             →  puzzle_theme_rows table + covering indexes  [one-time]
        │
        ▼
build_puzzle_json.py     →  data/<book>.json   (YAML config → SQL UNION ALL → JSON)
        │
        ▼
generate_latex_from_json.py  →  output/<book>.tex
        │
        ▼
pdflatex                 →  output/<book>.pdf
```

### How `build_puzzle_json.py` works

Python reads the YAML config and **constructs a SQL query** — it does not process data in Python.
For each chapter, it builds one `UNION ALL` query: one `SELECT … WHERE … ORDER BY … LIMIT` branch
per set in the chapter. Each branch hits `puzzle_theme_rows` with a covering index scan —
SQLite returns exactly the rows needed, already sorted and limited.

Python's only remaining jobs:
- Deduplicate across sets (e.g. prevent a puzzle from appearing in two sets)
- Apply the chapter-level re-sort (e.g. `nb_plays DESC` to interleave piece types)
- Write the JSON

## Notes

- The raw source of truth remains `data/lichess_db_puzzle.csv`.
- `lichess_puzzles.sqlite` is a derived cache — can be rebuilt from the CSV at any time.
- `puzzle_theme_rows` is a derived denormalization — rebuilt by `enrich_db.py`.
