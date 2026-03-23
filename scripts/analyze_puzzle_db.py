import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "lichess_puzzles.sqlite"

TARGET_THEMES = [
    "anastasiaMate",
    "arabianMate",
    "backRankMate",
    "blindSwineMate",
    "cornerMate",
    "dovetailMate",
    "hookMate",
    "pillsburysMate",
    "operaMate",
    "triangleMate",
    "smotheredMate",
    "balestraMate",
    "bodenMate",
    "doubleBishopMate",
    "epauletteMate",
    "killBoxMate",
    "morphysMate",
    "swallowstailMate",
    "vukovicMate",
]


def fetch_all(conn: sqlite3.Connection, query: str, params: tuple = ()) -> list[tuple]:
    return conn.execute(query, params).fetchall()


def print_section(title: str) -> None:
    print(f"\n=== {title} ===")


def analyze_theme_summary(conn: sqlite3.Connection) -> None:
    print_section("Theme summary")
    query = """
    SELECT
        pt.theme,
        COUNT(*) AS puzzle_count,
        MIN(p.rating) AS min_rating,
        ROUND(AVG(p.rating), 1) AS avg_rating,
        MAX(p.rating) AS max_rating,
        ROUND(AVG(p.move_count), 2) AS avg_move_count,
        MIN(p.move_count) AS min_move_count,
        MAX(p.move_count) AS max_move_count
    FROM puzzle_themes pt
    JOIN puzzles p ON p.puzzle_id = pt.puzzle_id
    WHERE pt.theme IN ({placeholders})
    GROUP BY pt.theme
    ORDER BY avg_rating DESC
    """.format(placeholders=",".join("?" for _ in TARGET_THEMES))

    for row in fetch_all(conn, query, tuple(TARGET_THEMES)):
        print(
            f"{row[0]:18s} count={row[1]:6d} floor={row[2]:4d} avg={row[3]:7.1f} "
            f"ceiling={row[4]:4d} avg_moves={row[5]:4.2f} range_moves={row[6]}-{row[7]}"
        )


def analyze_high_rating_sparsity(conn: sqlite3.Connection) -> None:
    print_section("High-rating sparsity (2400+)")
    query = """
    SELECT
        pt.theme,
        SUM(CASE WHEN p.rating >= 2400 THEN 1 ELSE 0 END) AS cnt_2400,
        SUM(CASE WHEN p.rating >= 2600 THEN 1 ELSE 0 END) AS cnt_2600,
        SUM(CASE WHEN p.rating >= 2800 THEN 1 ELSE 0 END) AS cnt_2800,
        MAX(p.rating) AS max_rating
    FROM puzzle_themes pt
    JOIN puzzles p ON p.puzzle_id = pt.puzzle_id
    WHERE pt.theme IN ({placeholders})
    GROUP BY pt.theme
    ORDER BY cnt_2600 ASC, cnt_2400 ASC, max_rating ASC
    """.format(placeholders=",".join("?" for _ in TARGET_THEMES))

    for row in fetch_all(conn, query, tuple(TARGET_THEMES)):
        print(f"{row[0]:18s} 2400+={row[1]:4d} 2600+={row[2]:4d} 2800+={row[3]:4d} max={row[4]}")


def analyze_long_easy_vs_short_hard(conn: sqlite3.Connection) -> None:
    print_section("Long easy vs short hard")

    long_easy_query = """
    SELECT
        pt.theme,
        ROUND(AVG(p.move_count), 2) AS avg_moves_easy,
        COUNT(*) AS cnt_easy
    FROM puzzle_themes pt
    JOIN puzzles p ON p.puzzle_id = pt.puzzle_id
    WHERE pt.theme IN ({placeholders})
      AND p.rating < 1400
    GROUP BY pt.theme
    HAVING COUNT(*) >= 20
    ORDER BY avg_moves_easy DESC
    LIMIT 10
    """.format(placeholders=",".join("?" for _ in TARGET_THEMES))

    print("Lowest-rated pools with longest sequences:")
    for row in fetch_all(conn, long_easy_query, tuple(TARGET_THEMES)):
        print(f"{row[0]:18s} avg_moves_under_1400={row[1]:4.2f} sample={row[2]}")

    short_hard_query = """
    SELECT
        pt.theme,
        ROUND(AVG(p.move_count), 2) AS avg_moves_hard,
        COUNT(*) AS cnt_hard,
        ROUND(AVG(p.rating), 1) AS avg_rating_hard
    FROM puzzle_themes pt
    JOIN puzzles p ON p.puzzle_id = pt.puzzle_id
    WHERE pt.theme IN ({placeholders})
      AND p.rating >= 2200
    GROUP BY pt.theme
    HAVING COUNT(*) >= 10
    ORDER BY avg_moves_hard ASC, avg_rating_hard DESC
    LIMIT 10
    """.format(placeholders=",".join("?" for _ in TARGET_THEMES))

    print("\nHighest-rated pools with shortest sequences:")
    for row in fetch_all(conn, short_hard_query, tuple(TARGET_THEMES)):
        print(f"{row[0]:18s} avg_moves_2200+={row[1]:4.2f} avg_rating={row[3]:6.1f} sample={row[2]}")


def analyze_rating_bands(conn: sqlite3.Connection) -> None:
    print_section("Theme density by coarse rating band")
    query = """
    SELECT
        pt.theme,
        SUM(CASE WHEN p.rating < 1400 THEN 1 ELSE 0 END) AS under_1400,
        SUM(CASE WHEN p.rating BETWEEN 1400 AND 1799 THEN 1 ELSE 0 END) AS band_1400_1799,
        SUM(CASE WHEN p.rating BETWEEN 1800 AND 2199 THEN 1 ELSE 0 END) AS band_1800_2199,
        SUM(CASE WHEN p.rating BETWEEN 2200 AND 2599 THEN 1 ELSE 0 END) AS band_2200_2599,
        SUM(CASE WHEN p.rating >= 2600 THEN 1 ELSE 0 END) AS over_2600
    FROM puzzle_themes pt
    JOIN puzzles p ON p.puzzle_id = pt.puzzle_id
    WHERE pt.theme IN ({placeholders})
    GROUP BY pt.theme
    ORDER BY over_2600 DESC, band_2200_2599 DESC
    """.format(placeholders=",".join("?" for _ in TARGET_THEMES))

    for row in fetch_all(conn, query, tuple(TARGET_THEMES)):
        print(
            f"{row[0]:18s} <1400={row[1]:5d} 1400-1799={row[2]:5d} 1800-2199={row[3]:5d} "
            f"2200-2599={row[4]:5d} 2600+={row[5]:4d}"
        )


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Could not find database at {DB_PATH}. Run scripts/import_csv_to_sqlite.py first."
        )

    with sqlite3.connect(DB_PATH) as conn:
        analyze_theme_summary(conn)
        analyze_high_rating_sparsity(conn)
        analyze_long_easy_vs_short_hard(conn)
        analyze_rating_bands(conn)


if __name__ == "__main__":
    main()
