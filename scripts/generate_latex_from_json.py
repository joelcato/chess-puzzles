import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Optional

import chess


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

# Legacy defaults — used only when a JSON does not supply the field
_DEFAULT_BOOK_TITLE = "Chess Puzzle Book"
_DEFAULT_BOOK_SUBTITLE = ""
_DEFAULT_BOOK_AUTHOR = "by Joel Cato"
_DEFAULT_BOOK_PUBLISHER = "Covington Press"

def _default_verso(author: str, publisher: str) -> str:
    year = 2026
    author_clean = author.lstrip("by ").strip() or "Joel Cato"
    return (
        f"Copyright © {year} {author_clean}\n\n"
        "All rights reserved.\n\n"
        "No part of this publication may be reproduced, stored in a retrieval system,\n"
        "or transmitted in any form or by any means, electronic, mechanical,\n"
        "photocopying, recording, or otherwise, without prior written permission."
    )

START_PAGE = 1
BOARD_ROW_SHIFT = "-0.08in"
SOLUTIONS_INDENT = "0.12in"
DRAFT_CHAPTERS_ENV = "PUZZLE_BOOK_DRAFT_CHAPTERS"
DRAFT_PAGES_PER_SIDE_ENV = "PUZZLE_BOOK_DRAFT_PAGES_PER_SIDE"

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


def env_int(name: str) -> Optional[int]:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return max(0, int(value))


def limit_section_pages(section_puzzles: list[dict[str, Any]], pages_per_side: Optional[int]) -> list[dict[str, Any]]:
    if pages_per_side is None:
        return section_puzzles
    return section_puzzles[: pages_per_side * 4]


def apply_draft_limits(document: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    chapter_limit = env_int(DRAFT_CHAPTERS_ENV)
    pages_per_side = env_int(DRAFT_PAGES_PER_SIDE_ENV)

    if chapter_limit is None and pages_per_side is None:
        return document, False

    limited_document = dict(document)
    original_chapters = document.get("chapters", [])
    chapters = original_chapters[:chapter_limit] if chapter_limit is not None else original_chapters

    limited_chapters: list[dict[str, Any]] = []
    for chapter in chapters:
        limited_chapter = dict(chapter)
        chapter_groups = chapter.get("groups") or {}
        white = limit_section_pages(chapter_groups.get("white_to_move", []), pages_per_side)
        black = limit_section_pages(chapter_groups.get("black_to_move", []), pages_per_side)
        puzzles = white + black

        limited_chapter["puzzles"] = puzzles
        limited_chapter["groups"] = {
            "white_to_move": white,
            "black_to_move": black,
        }
        limited_chapter["puzzle_count"] = len(puzzles)
        limited_chapter["white_to_move_count"] = len(white)
        limited_chapter["black_to_move_count"] = len(black)
        limited_chapters.append(limited_chapter)

    limited_document["chapters"] = limited_chapters
    return limited_document, True


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
            parts.append(f"{move_no}.{white_move}" + (f" {black_move}" if black_move else ""))
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
            parts.append(f"{move_no}.{white_move}" + (f" {black_move}" if black_move else ""))
            move_no += 1
            i += 2
    return " ".join(parts)


def front_matter_block(book_title: str, book_subtitle: str, book_author: str, book_publisher: str, verso_text: str) -> str:
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

    subtitle_block = (
        f"""
\\vspace{{1.8em}}
\\begin{{minipage}}{{0.82\\textwidth}}
\\centering
\\large {book_subtitle}\\par
\\end{{minipage}}"""
        if book_subtitle and book_subtitle.strip()
        else ""
    )

    return f"""
\\thispagestyle{{empty}}

\\vspace*{{0.16\\textheight}}

\\begin{{center}}
{{\\Huge\\bfseries {book_title}\\par}}
{subtitle_block}
\\end{{center}}

\\vspace*{{0.14\\textheight}}

\\begin{{center}}
\\begin{{minipage}}{{0.52\\textwidth}}
\\centering
{{\\LARGE\\bfseries {book_author}\\par}}
\\end{{minipage}}
\\end{{center}}

\\vfill

\\begin{{center}}
{{\\normalsize {book_publisher}\\par}}
\\end{{center}}

\\newpage

\\thispagestyle{{empty}}

\\vspace*{{0.72\\textheight}}

{verso_body}

\\newpage
""".strip()


def table_of_contents_block() -> str:
    return """
\\thispagestyle{empty}

\\vspace*{0.05\\textheight}

\\begingroup
\\renewcommand{\\contentsname}{Contents}
\\setlength{\\cftbeforesecskip}{0pt}
\\setlength{\\cftaftertoctitleskip}{1.2em}
\\begin{center}
\\begin{minipage}[t][0.82\\textheight][s]{0.92\\textwidth}
\\centering
\\normalsize
\\renewcommand{\\baselinestretch}{1.18}\\selectfont
\\tableofcontents
\\vspace*{0pt plus 1fill}
\\end{minipage}
\\end{center}
\\endgroup

\\newpage
""".strip()


def puzzle_cell(puzzle_id: str, fen: str) -> str:
    return rf"\PuzzleCell{{{puzzle_id}}}{{{fen}}}"


def blank_cell() -> str:
    return r"\begin{minipage}[t]{0.46\textwidth}\mbox{}\end{minipage}"


def solutions_block(puzzles: list[dict[str, Any]]) -> str:
    padded = puzzles + [None] * (4 - len(puzzles))

    def solution_entry(puzzle: Optional[dict[str, Any]]) -> str:
        if not puzzle:
            return ""
        display_fen = puzzle.get("display_fen") or puzzle["fen"]
        solver_moves = puzzle["moves"][1:]  # strip opponent's first half-move
        solution = format_solution_from_fen_and_moves(display_fen, solver_moves)
        return rf"{{\bfseries {puzzle['display_id']}.}} {solution}"

    left_top = solution_entry(padded[0])
    right_top = solution_entry(padded[1])
    left_bottom = solution_entry(padded[2])
    right_bottom = solution_entry(padded[3])

    return rf"""
{{\footnotesize\sloppy
\noindent
% Parent solutions container
\begin{{minipage}}[t]{{\textwidth}}
  % Left solutions
    \begin{{minipage}}[c]{{0.47\textwidth}}
        {left_top}

        \vspace{{0.45em}}

        {left_bottom}
    \end{{minipage}}
        \hfill
  % Vertical divider
    \begin{{minipage}}[c][4.9\baselineskip][c]{{0.02\textwidth}}
        \centering\rule{{0.4pt}}{{4.7\baselineskip}}
    \end{{minipage}}
    \hfill
  % Right solutions
    \begin{{minipage}}[c]{{0.47\textwidth}}
        {right_top}

        \vspace{{0.45em}}

        {right_bottom}
    \end{{minipage}}
\end{{minipage}}
}}
""".strip()


def page_block(puzzles: list[dict[str, Any]], title: str, subtitle: str) -> str:
    padded = puzzles + [None] * (4 - len(puzzles))

    c1 = puzzle_cell(padded[0]["display_id"], padded[0].get("display_fen") or padded[0]["fen"]) if padded[0] else blank_cell()
    c2 = puzzle_cell(padded[1]["display_id"], padded[1].get("display_fen") or padded[1]["fen"]) if padded[1] else blank_cell()
    c3 = puzzle_cell(padded[2]["display_id"], padded[2].get("display_fen") or padded[2]["fen"]) if padded[2] else blank_cell()
    c4 = puzzle_cell(padded[3]["display_id"], padded[3].get("display_fen") or padded[3]["fen"]) if padded[3] else blank_cell()

    return rf"""
\begin{{center}}
\Large\bfseries {title}

\vspace{{0.15em}}
\normalsize {subtitle}
\end{{center}}

\vspace{{0.35em}}

\noindent\hspace*{{-0.08in}}
{c1}
\hspace{{0.02\textwidth}}
{c2}

\vspace{{0.1em}}

\noindent\hspace*{{-0.08in}}
{c3}
\hspace{{0.02\textwidth}}
{c4}

\vfill

\noindent\rule{{\textwidth}}{{0.4pt}}

\vspace{{0.15em}}

\noindent\makebox[\textwidth][c]{{\small\bfseries Solutions}}

\vspace{{0.75em}}

{solutions_block(puzzles)}
""".strip()


def chapter_title_page(chapter_label: str) -> str:
    return f"""
\\thispagestyle{{empty}}
\\phantomsection

\\vspace*{{0.34\\textheight}}

\\begin{{center}}
{{\\Huge\\bfseries {chapter_label}\\par}}
\\end{{center}}

\\vfill
""".strip()


def end_on_verso_then_next_on_recto(blocks: list[str]) -> None:
    blocks.append(r"\newpage")
    blocks.append(r"\checkoddpage\ifoddpage\null\thispagestyle{empty}\newpage\fi")


def force_next_content_to_recto(blocks: list[str]) -> None:
    blocks.append(r"\checkoddpage\ifoddpage\else\null\thispagestyle{empty}\newpage\fi")


def build_document(document: dict, start_page: int) -> str:
    document_name = document.get("_output_name", "puzzle_book")
    preamble = rf"""
% !TEX program = pdflatex
% !TEX jobname = {document_name}
\documentclass[12pt,twoside]{{article}}
\usepackage[
    paperwidth=6in,
    paperheight=9in,
    includefoot,
    twoside,
    inner=0.75in,     % gutter (binding) for ~550 pages per KDP guidance
    outer=0.25in,     % outside margin
    top=0.25in,
    bottom=0.50in
]{{geometry}}
\usepackage[LSB1,T1]{{fontenc}}
\usepackage{{xcolor}}
\usepackage{{chessboard}}
\usepackage{{chessfss}}
\usepackage{{fancyhdr}}
\usepackage{{ifoddpage}}
\usepackage{{hyperref}}
\usepackage{{ragged2e}}
\usepackage{{tocloft}}

\setcounter{{tocdepth}}{{1}}
\hfuzz=20pt
\hbadness=10000

\setcounter{{page}}{{{start_page}}}
\setlength{{\footskip}}{{30pt}}

\pagestyle{{fancy}}
\fancyhf{{}}
\cfoot{{\thepage}}
\renewcommand{{\headrulewidth}}{{0pt}}

\newcommand{{\coordfont}}{{\rmfamily\bfseries}}
\setfigfontfamily{{goodcompanions2}}

\setboardfontcolors{{
    blackfield=black!60
}}

\setchessboard{{
    boardfontsize=18pt,
    boardfontfamily=goodcompanions2,
    boardfontencoding=LSB1,
    borderwidth=0.5pt,
    bordercolor=black,
    showmover=false,
    labelleft=true,
    labelbottom=true,
    labelleftwidth=1.2ex,
    labelbottomlift=1.2\baselineskip,
    labelfont=\coordfont,
    labelfontsize=7pt
}}

\def\SideToMoveFromFEN#1 #2 #3\relax{{#2}}

\newcommand{{\RenderPuzzleBoard}}[1]{{%
    \edef\PuzzleSideToMove{{\expandafter\SideToMoveFromFEN#1 \relax}}%
    \if b\PuzzleSideToMove
        \chessboard[setfen={{#1}},inverse=true]%
    \else
        \chessboard[setfen={{#1}}]%
    \fi
}}

\newcommand{{\PuzzleCell}}[2]{{%
    \begin{{minipage}}[t]{{0.46\textwidth}}
        \centering
        \RenderPuzzleBoard{{#2}}

        \vspace{{0.15em}}
        {{\small\bfseries Puzzle #1}}

        \vspace{{0.45em}}
    \end{{minipage}}
}}

\begin{{document}}
""".strip()

    book_title = document.get("title", _DEFAULT_BOOK_TITLE)
    book_subtitle = document.get("subtitle", _DEFAULT_BOOK_SUBTITLE)
    book_author = document.get("author", _DEFAULT_BOOK_AUTHOR)
    book_publisher = document.get("publisher", _DEFAULT_BOOK_PUBLISHER)
    verso_text = document.get("verso_text") or _default_verso(book_author, book_publisher)

    show_toc = document.get("toc", True)

    blocks = [
        front_matter_block(
            book_title=book_title,
            book_subtitle=book_subtitle,
            book_author=book_author,
            book_publisher=book_publisher,
            verso_text=verso_text,
        ),
    ]
    if show_toc:
        blocks.append(table_of_contents_block())

    global_display_id = 1
    chapters = document.get("chapters", [])
    for chapter_index, chapter in enumerate(chapters):
        # Support both old ("label") and new ("title") JSON key
        chapter_label = chapter.get("title") or chapter.get("label", "")

        # Ensure chapter title is always on recto using LaTeX's standard double-page clear
        blocks.append(r"\cleardoublepage")
        blocks.append(chapter_title_page(chapter_label))
        blocks.append(rf"\addcontentsline{{toc}}{{section}}{{{chapter_label}}}")
        # Insert a single blank verso page after the title so puzzles start on the following recto
        blocks.append(r"\newpage\null\thispagestyle{empty}\newpage")

        puzzles = chapter.get("puzzles", [])
        puzzle_by_id: dict[str, dict[str, Any]] = {}
        for puzzle in puzzles:
            # Support both old ("id") and new ("puzzle_id") JSON key
            pid = puzzle.get("puzzle_id") or puzzle.get("id", "")
            puzzle["source_id"] = pid
            puzzle["display_id"] = str(global_display_id)
            puzzle_by_id[pid] = puzzle
            global_display_id += 1

        chapter_groups = chapter.get("groups") or {
            "white_to_move": [p for p in puzzles if chess.Board(p["fen"]).turn == chess.WHITE],
            "black_to_move": [p for p in puzzles if chess.Board(p["fen"]).turn == chess.BLACK],
        }

        for grouped_puzzles in chapter_groups.values():
            for grouped_puzzle in grouped_puzzles:
                pid = grouped_puzzle.get("puzzle_id") or grouped_puzzle.get("id", "")
                source = puzzle_by_id.get(pid)
                if source is not None:
                    grouped_puzzle["source_id"] = source["source_id"]
                    grouped_puzzle["display_id"] = source["display_id"]

        ordered_sections = [
            ("White to Move", chapter_groups.get("white_to_move", [])),
            ("Black to Move", chapter_groups.get("black_to_move", [])),
        ]
        nonempty_section_titles = [title for title, section_puzzles in ordered_sections if section_puzzles]

        rendered_any = False
        for subtitle, section_puzzles in ordered_sections:
            if not section_puzzles:
                continue

            groups = list(chunked(section_puzzles, 4))
            for group_index, group in enumerate(groups):
                blocks.append(page_block(group, chapter_label, subtitle))
                rendered_any = True

                is_last_group_in_section = group_index == len(groups) - 1
                is_last_nonempty_section = subtitle == nonempty_section_titles[-1]
                is_last_group = is_last_group_in_section and is_last_nonempty_section
                is_last_chapter = chapter_index == len(chapters) - 1
                if not (is_last_group and is_last_chapter):
                    blocks.append(r"\newpage")

        if not rendered_any:
            blocks.append(page_block([], chapter["label"], "White to Move"))
            is_last_chapter = chapter_index == len(chapters) - 1
            if not is_last_chapter:
                blocks.append(r"\newpage")

    ending = r"""
\end{document}
""".strip()
    return preamble + "\n\n" + "\n\n".join(blocks) + "\n\n" + ending


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a LaTeX puzzle book from a JSON file."
    )
    parser.add_argument(
        "input_json",
        nargs="?",
        default=None,
        help="Path to the input JSON file (default: data/mating_patterns_100_by_theme.json)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Override the output .tex path (default: output/<stem>.tex)",
    )
    args = parser.parse_args()

    # Resolve input JSON
    if args.input_json:
        input_json = Path(args.input_json)
        if not input_json.is_absolute():
            input_json = BASE_DIR / input_json
    else:
        input_json = DATA_DIR / "mating_patterns_100_by_theme.json"

    if not input_json.exists():
        raise FileNotFoundError(f"Could not find input JSON: {input_json}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with input_json.open("r", encoding="utf-8") as f:
        document = json.load(f)

    document, is_draft = apply_draft_limits(document)

    # Derive output filenames from the JSON stem
    stem = input_json.stem
    output_tex = OUTPUT_DIR / f"{stem}.tex"
    output_tex_draft = OUTPUT_DIR / f"{stem}_preview.tex"

    if args.output:
        output_tex = Path(args.output)
        if not output_tex.is_absolute():
            output_tex = BASE_DIR / output_tex
        output_tex_draft = output_tex.with_name(output_tex.stem + "_preview" + output_tex.suffix)

    document["_output_name"] = output_tex_draft.stem if is_draft else output_tex.stem

    tex = build_document(document=document, start_page=START_PAGE)
    output_path = output_tex_draft if is_draft else output_tex
    output_path.write_text(tex, encoding="utf-8")
    if is_draft:
        print(
            f"Wrote draft preview to {output_path} "
            f"(chapters env: {os.getenv(DRAFT_CHAPTERS_ENV)!r}, pages/side env: {os.getenv(DRAFT_PAGES_PER_SIDE_ENV)!r})"
        )
    else:
        print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
