# Chess Puzzles

This repo builds themed chess puzzle books from the Lichess puzzle database.

## Python environment

Use the project virtual environment:

```zsh
source .venv/bin/activate
```

## Build the SQLite exploration database

Import the raw CSV into SQLite:

```zsh
python scripts/import_csv_to_sqlite.py
```

This creates `data/lichess_puzzles.sqlite` with:
- `puzzles`: one row per puzzle
- `puzzle_themes`: one row per `(puzzle, theme)` pair

## Run exploratory analysis

```zsh
python scripts/analyze_puzzle_db.py
```

The analysis script prints summaries for:
- theme floor / ceiling / average rating
- high-rating sparsity
- long easy sequences vs short hard sequences
- coarse rating-band density per theme

## Generate the chaptered puzzle JSON and TeX

```zsh
python scripts/prepare_mating_patterns_json.py
python scripts/generate_latex_from_json.py
```

The generated JSON now stores each chapter in two grouped sections:
- `white_to_move`
- `black_to_move`

The TeX generator renders those as separate page groups within each chapter, while preserving the chapter title page and solutions layout.

## Notes

- The raw source of truth remains `data/lichess_db_puzzle.csv`.
- The SQLite database is a derived cache for faster exploration.
- The actively supported pipeline is:
	- SQLite import / analysis
	- themed JSON generation
	- JSON-to-TeX generation
