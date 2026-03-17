import json
import re
from pathlib import Path
from typing import Any

import chess


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

INPUT_JSON = DATA_DIR / "mate_in_one_800.json"
OUTPUT_TEX = OUTPUT_DIR / "mate_in_one_800.tex"

BOOK_TITLE = "Chess Puzzle Book"
BOOK_SUBTITLE = "Mate in 1"
BOOK_AUTHOR = "by Joel Cato"

VERSO_TEXT = r"""
Copyright © 2026 Joel Cato

All rights reserved.

No part of this publication may be reproduced, stored in a retrieval system,
or transmitted in any form or by any means, electronic, mechanical,
photocopying, recording, or otherwise, without prior written permission.
""".strip()

SECTION_TITLE = "Mate in 1"
START_PAGE = 1
MAX_BOOK_PUZZLES = 400

BOARD_ROW_SHIFT = "-0.08in"
SOLUTIONS_INDENT = "0.12in"

FIGURINE_MAP = {
    "K": r"\symking{}",
    "Q": r"\symqueen{}",
    "R": r"\symrook{}",
    "B": r"\symbishop{}",
    "N": r"\symknight{}",
}


def chunked(seq: list[dict[str, Any]], size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def san_to_latex_figurines(san: str) -> str:
    san = re.sub(r"[KQRBN]", lambda m: FIGURINE_MAP[m.group()], san)
    san = san.replace("#", r"\#")
    return san


def format_solution_from_fen_and_moves(fen: str, moves: list[str]) -> str:
    board = chess.Board(fen)
    starting_turn = board.turn

    san_moves: list[str] = []

    for uci in moves:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            return f"[ILLEGAL MOVE {uci}]"

        san = board.san(move)
        san_moves.append(san_to_latex_figurines(san))
        board.push(move)

    parts: list[str] = []

    if starting_turn == chess.WHITE:
        move_no = 1
        i = 0
        while i < len(san_moves):
            white_move = san_moves[i]
            black_move = san_moves[i + 1] if i + 1 < len(san_moves) else None

            if black_move:
                parts.append(f"{move_no}.{white_move} {black_move}")
            else:
                parts.append(f"{move_no}.{white_move}")

            move_no += 1
            i += 2
    else:
        if san_moves:
            parts.append(rf"1\ldots {san_moves[0]}")

        move_no = 2
        i = 1
        while i < len(san_moves):
            white_move = san_moves[i]
            black_move = san_moves[i + 1] if i + 1 < len(san_moves) else None

            if black_move:
                parts.append(f"{move_no}.{white_move} {black_move}")
            else:
                parts.append(f"{move_no}.{white_move}")

            move_no += 1
            i += 2

    return " ".join(parts)


def front_matter_block(
    book_title: str,
    book_subtitle: str,
    book_author: str,
    verso_text: str,
) -> str:
    verso_body = (
        f"""
\\begin{{center}}
\\small
{verso_text}
\\end{{center}}
""".strip()
        if verso_text.strip()
        else r"\null"
    )

    return f"""
\\thispagestyle{{empty}}

\\vspace*{{0.22\\textheight}}

\\begin{{center}}
{{\\Huge\\bfseries {book_title}\\par}}
\\vspace{{1.5em}}
{{\\Large {book_subtitle}\\par}}
\\vspace{{2em}}
{{\\Large {book_author}\\par}}
\\end{{center}}

\\vfill

\\newpage

\\thispagestyle{{empty}}

\\vspace*{{0.72\\textheight}}

{verso_body}

\\newpage
""".strip()


def puzzle_cell(puzzle_id: str, fen: str) -> str:
    return rf"\PuzzleCell{{{puzzle_id}}}{{{fen}}}"


def blank_cell() -> str:
    return r"\begin{minipage}[t]{0.46\textwidth}\mbox{}\end{minipage}"


def solutions_block(puzzles: list[dict[str, Any]]) -> str:
    lines = []

    for p in puzzles:
        puzzle_id = p["display_id"]
        fen = p["fen"]
        moves = p["moves"]

        solution = format_solution_from_fen_and_moves(fen, moves)
        lines.append(rf"\noindent \textbf{{{puzzle_id}.}} {solution}")

    if not lines:
        return (
            "{\\footnotesize\\sloppy\n"
            + f"\\begin{{adjustwidth}}{{{SOLUTIONS_INDENT}}}{{0in}}\n"
            + "\\noindent \\textbf{Solutions will go here later.}\n"
            + "\\end{adjustwidth}\n"
            + "}"
        )

    body = " \\\\\n[0.2em]\n".join(lines)
    return (
        "{\\footnotesize\\sloppy\n"
        + f"\\begin{{adjustwidth}}{{{SOLUTIONS_INDENT}}}{{0in}}\n"
        + body
        + "\n\\end{adjustwidth}\n}"
    )


def page_block(puzzles: list[dict[str, Any]], title: str) -> str:
    padded = puzzles + [None] * (4 - len(puzzles))

    c1 = puzzle_cell(padded[0]["display_id"], padded[0]["fen"]) if padded[0] else blank_cell()
    c2 = puzzle_cell(padded[1]["display_id"], padded[1]["fen"]) if padded[1] else blank_cell()
    c3 = puzzle_cell(padded[2]["display_id"], padded[2]["fen"]) if padded[2] else blank_cell()
    c4 = puzzle_cell(padded[3]["display_id"], padded[3]["fen"]) if padded[3] else blank_cell()

    solutions_tex = solutions_block(puzzles)

    return f"""
\\begin{{center}}
\\Large\\bfseries {title}
\\end{{center}}

\\vspace{{0.35em}}

\\noindent\\hspace*{{{BOARD_ROW_SHIFT}}}
{c1}
\\hspace{{0.02\\textwidth}}
{c2}

\\vspace{{0.1em}}

\\noindent\\hspace*{{{BOARD_ROW_SHIFT}}}
{c3}
\\hspace{{0.02\\textwidth}}
{c4}

\\vspace{{0.8em}}

\\hspace*{{{SOLUTIONS_INDENT}}}\\rule{{\\dimexpr\\textwidth-{SOLUTIONS_INDENT}\\relax}}{{0.4pt}}

\\vspace{{0.1em}}

\\begin{{center}}
\\small\\bfseries Solutions
\\end{{center}}

\\vspace{{-0.35em}}

{solutions_tex}
""".strip()


def build_document(puzzles: list[dict[str, Any]], title: str, start_page: int) -> str:
    preamble = f"""
\\documentclass[12pt,twoside]{{article}}
\\usepackage[
  paperwidth=6in,
  paperheight=9in,
  inner=0.45in,
  outer=0.40in,
  top=0.45in,
  bottom=0.50in
]{{geometry}}
\\usepackage[LSB,T1]{{fontenc}}
\\usepackage{{xcolor}}
\\usepackage{{chessboard}}
\\usepackage{{chessfss}}
\\usepackage{{fancyhdr}}
\\usepackage{{changepage}}

\\setcounter{{page}}{{{start_page}}}
\\setlength{{\\footskip}}{{18pt}}

\\pagestyle{{fancy}}
\\fancyhf{{}}
\\cfoot{{\\thepage}}
\\renewcommand{{\\headrulewidth}}{{0pt}}

\\newcommand{{\\coordfont}}{{\\rmfamily\\bfseries}}
\\setfigfontfamily{{merida}}

\\setchessboard{{
  boardfontsize=18pt,
  boardfontfamily=merida,
  boardfontencoding=LSB,
  blackfieldmaskcolor=white,
  blackfieldcolor=black!75,
  borderwidth=0.35pt,
  bordercolor=black,
  labelleft=true,
  labelbottom=true,
  labelfont=\\coordfont,
  labelfontsize=6pt
}}

\\newcommand{{\\PuzzleCell}}[2]{{%
  \\begin{{minipage}}[t]{{0.46\\textwidth}}
    \\centering
    \\chessboard[setfen={{#2}}]

    \\vspace{{0.15em}}
    {{\\small\\bfseries Puzzle #1}}

    \\vspace{{0.45em}}
  \\end{{minipage}}
}}

\\begin{{document}}
""".strip()

    front_matter = front_matter_block(
        book_title=BOOK_TITLE,
        book_subtitle=BOOK_SUBTITLE,
        book_author=BOOK_AUTHOR,
        verso_text=VERSO_TEXT,
    )

    pages = []
    groups = list(chunked(puzzles, 4))

    for i, group in enumerate(groups):
        pages.append(page_block(group, title))
        if i < len(groups) - 1:
            pages.append(r"\newpage")

    ending = r"""
\end{document}
""".strip()

    return (
        preamble
        + "\n\n"
        + front_matter
        + "\n\n"
        + "\n\n".join(pages)
        + "\n\n"
        + ending
    )


def main():
    input_path = INPUT_JSON
    output_path = OUTPUT_TEX

    if not input_path.exists():
        raise FileNotFoundError(f"Could not find input JSON: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", encoding="utf-8") as f:
        puzzles = json.load(f)

    puzzles = puzzles[:MAX_BOOK_PUZZLES]

    for i, p in enumerate(puzzles, start=1):
        p["source_id"] = p.get("id")
        p["display_id"] = str(i)

    tex = build_document(
        puzzles=puzzles,
        title=SECTION_TITLE,
        start_page=START_PAGE,
    )

    output_path.write_text(tex, encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()