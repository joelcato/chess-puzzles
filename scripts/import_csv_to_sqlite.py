import csv
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

INPUT_CSV = DATA_DIR / "lichess_db_puzzle.csv"
OUTPUT_DB = DATA_DIR / "lichess_puzzles.sqlite"
BATCH_SIZE = 10_000


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA temp_store=MEMORY;

DROP TABLE IF EXISTS puzzle_themes;
DROP TABLE IF EXISTS puzzles;

CREATE TABLE puzzles (
    puzzle_id TEXT PRIMARY KEY,
    fen TEXT NOT NULL,
    moves TEXT NOT NULL,
    move_count INTEGER NOT NULL,
    rating INTEGER NOT NULL,
    rating_deviation INTEGER,
    popularity INTEGER,
    nb_plays INTEGER,
    game_url TEXT,
    opening_tags TEXT
);

CREATE TABLE puzzle_themes (
    puzzle_id TEXT NOT NULL,
    theme TEXT NOT NULL,
    PRIMARY KEY (puzzle_id, theme),
    FOREIGN KEY (puzzle_id) REFERENCES puzzles(puzzle_id)
);

CREATE INDEX idx_puzzles_rating ON puzzles(rating);
CREATE INDEX idx_puzzles_move_count ON puzzles(move_count);
CREATE INDEX idx_puzzles_popularity ON puzzles(popularity);
CREATE INDEX idx_puzzles_nb_plays ON puzzles(nb_plays);
CREATE INDEX idx_puzzle_themes_theme ON puzzle_themes(theme);
CREATE INDEX idx_puzzle_themes_theme_puzzle ON puzzle_themes(theme, puzzle_id);
""".strip()


PUZZLE_INSERT = """
INSERT INTO puzzles (
    puzzle_id,
    fen,
    moves,
    move_count,
    rating,
    rating_deviation,
    popularity,
    nb_plays,
    game_url,
    opening_tags
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""".strip()

THEME_INSERT = "INSERT INTO puzzle_themes (puzzle_id, theme) VALUES (?, ?)"


def to_int(value: str) -> int | None:
    if value == "":
        return None
    return int(float(value))


def import_csv(input_csv: Path, output_db: Path) -> None:
    output_db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(output_db) as conn:
        conn.executescript(SCHEMA)

        puzzle_rows: list[tuple] = []
        theme_rows: list[tuple[str, str]] = []
        row_count = 0

        with input_csv.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                puzzle_id = row["PuzzleId"]
                moves = row["Moves"].strip()
                move_count = len(moves.split()) if moves else 0

                puzzle_rows.append(
                    (
                        puzzle_id,
                        row["FEN"],
                        moves,
                        move_count,
                        to_int(row["Rating"]),
                        to_int(row["RatingDeviation"]),
                        to_int(row["Popularity"]),
                        to_int(row["NbPlays"]),
                        row["GameUrl"],
                        row["OpeningTags"],
                    )
                )

                for theme in set(row["Themes"].split()):
                    theme_rows.append((puzzle_id, theme))

                row_count += 1
                if row_count % BATCH_SIZE == 0:
                    conn.executemany(PUZZLE_INSERT, puzzle_rows)
                    conn.executemany(THEME_INSERT, theme_rows)
                    conn.commit()
                    print(f"Imported {row_count} puzzles...")
                    puzzle_rows.clear()
                    theme_rows.clear()

        if puzzle_rows:
            conn.executemany(PUZZLE_INSERT, puzzle_rows)
            conn.executemany(THEME_INSERT, theme_rows)
            conn.commit()

        total_puzzles = conn.execute("SELECT COUNT(*) FROM puzzles").fetchone()[0]
        total_themes = conn.execute("SELECT COUNT(*) FROM puzzle_themes").fetchone()[0]
        distinct_themes = conn.execute("SELECT COUNT(DISTINCT theme) FROM puzzle_themes").fetchone()[0]

    print(f"Imported {total_puzzles} puzzles into {output_db}")
    print(f"Imported {total_themes} puzzle-theme rows across {distinct_themes} distinct themes")


def main() -> None:
    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"Could not find input CSV: {INPUT_CSV}")

    import_csv(INPUT_CSV, OUTPUT_DB)


if __name__ == "__main__":
    main()
