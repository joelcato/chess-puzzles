import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Optional

import chess
import jinja2


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
TEMPLATES_DIR = BASE_DIR / "templates"

# Legacy defaults — used only when a JSON does not supply the field
_DEFAULT_BOOK_TITLE = "Chess Puzzle Book"
_DEFAULT_BOOK_SUBTITLE = ""
_DEFAULT_BOOK_AUTHOR = "by Joel Cato"
_DEFAULT_BOOK_PUBLISHER = "Covington Press"


def _default_verso(author: str, publisher: str) -> str:
    year = 2026
    author_clean = author.lstrip("by ").strip() or "Joel Cato"
    return (
        f"Copyright \\copyright\\ {year} {author_clean}\n\n"
        "All rights reserved.\n\n"
        "No part of this publication may be reproduced, stored in a retrieval system,\n"
        "or transmitted in any form or by any means, electronic, mechanical,\n"
        "photocopying, recording, or otherwise, without prior written permission."
    )


START_PAGE = 1
DRAFT_CHAPTERS_ENV = "PUZZLE_BOOK_DRAFT_CHAPTERS"
DRAFT_PAGES_PER_SIDE_ENV = "PUZZLE_BOOK_DRAFT_PAGES_PER_SIDE"

FIGURINE_MAP = {
    "K": r"\symking{}",
    "Q": r"\symqueen{}",
    "R": r"\symrook{}",
    "B": r"\symbishop{}",
    "N": r"\symknight{}",
}


def chunked(seq: list, size: int):
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


def format_solution(fen: str, moves: list[str]) -> str:
    """Convert a FEN + UCI move list into a LaTeX-formatted solution string."""
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


def _make_cell(puzzle: dict[str, Any]) -> dict[str, Any]:
    """Build the cell context dict passed to the template for one puzzle."""
    display_fen = puzzle.get("display_fen") or puzzle["fen"]
    solver_moves = puzzle["moves"][1:]  # strip opponent's first half-move
    return {
        "display_id": puzzle["display_id"],
        "fen": display_fen,
        "solution": format_solution(display_fen, solver_moves),
    }


def build_context(document: dict[str, Any], start_page: int) -> dict[str, Any]:
    """Pre-process the JSON document into a flat context dict for the Jinja2 template.

    All logic (display_id assignment, solution formatting, page chunking,
    is_last flags) lives here. The template is purely structural.
    """
    book_title = document.get("title", _DEFAULT_BOOK_TITLE)
    book_subtitle = document.get("subtitle", _DEFAULT_BOOK_SUBTITLE)
    book_author = document.get("author", _DEFAULT_BOOK_AUTHOR)
    book_publisher = document.get("publisher", _DEFAULT_BOOK_PUBLISHER)
    verso_text = document.get("verso_text") or _default_verso(book_author, book_publisher)

    show_toc = document.get("toc", True)
    show_chapter_title_pages = document.get("chapter_title_pages", True)

    global_display_id = 1
    chapters_ctx: list[dict[str, Any]] = []

    raw_chapters = document.get("chapters", [])
    for chapter in raw_chapters:
        chapter_label = chapter.get("title") or chapter.get("label", "")

        puzzles = chapter.get("puzzles", [])
        puzzle_by_id: dict[str, dict[str, Any]] = {}
        for puzzle in puzzles:
            pid = puzzle.get("puzzle_id") or puzzle.get("id", "")
            puzzle["source_id"] = pid
            puzzle_by_id[pid] = puzzle

        chapter_groups = chapter.get("groups") or {
            "white_to_move": [p for p in puzzles if chess.Board(p["fen"]).turn == chess.WHITE],
            "black_to_move": [p for p in puzzles if chess.Board(p["fen"]).turn == chess.BLACK],
        }

        raw_sections = [
            ("White to Move", chapter_groups.get("white_to_move", [])),
            ("Black to Move", chapter_groups.get("black_to_move", [])),
        ]
        nonempty = [(sub, pzls) for sub, pzls in raw_sections if pzls]

        # Assign display IDs in section render order (white before black) so
        # puzzle numbers in the TeX are sequential as they appear on the page.
        for _, section_puzzles in nonempty:
            for gp in section_puzzles:
                gp["display_id"] = str(global_display_id)
                global_display_id += 1

        sections_ctx: list[dict[str, Any]] = []
        for sec_idx, (subtitle, section_puzzles) in enumerate(nonempty):
            page_groups = list(chunked(section_puzzles, 4))
            pages_ctx: list[dict[str, Any]] = []
            for pg_idx, group in enumerate(page_groups):
                is_last_page_in_section = pg_idx == len(page_groups) - 1
                is_last_section = sec_idx == len(nonempty) - 1
                is_last_chapter = chapter is raw_chapters[-1]
                is_last = is_last_page_in_section and is_last_section and is_last_chapter

                cells = [_make_cell(p) for p in group]
                while len(cells) < 4:
                    cells.append(None)

                pages_ctx.append({
                    "cells": cells,
                    "is_last": is_last,
                })
            sections_ctx.append({
                "subtitle": subtitle,
                "pages": pages_ctx,
            })

        chapters_ctx.append({
            "label": chapter_label,
            "sections": sections_ctx,
        })

    return {
        "document_name": document.get("_output_name", "puzzle_book"),
        "start_page": start_page,
        "book_title": book_title,
        "book_subtitle": book_subtitle,
        "book_author": book_author,
        "book_publisher": book_publisher,
        "verso_text": verso_text,
        "show_toc": show_toc,
        "show_chapter_title_pages": show_chapter_title_pages,
        "chapters": chapters_ctx,
    }


def render_template(context: dict[str, Any]) -> str:
    """Render the Jinja2 template with LaTeX-safe delimiters.

    Delimiters chosen to avoid conflicts with LaTeX syntax:
      Variables:  <{  }>
      Blocks:     <%  %>
      Comments:   <#  #>
    """
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
        variable_start_string="<{",
        variable_end_string="}>",
        block_start_string="<%",
        block_end_string="%>",
        comment_start_string="<#",
        comment_end_string="#>",
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("puzzle_book.tex.j2")
    return template.render(**context)


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

    context = build_context(document=document, start_page=START_PAGE)
    tex = render_template(context)

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

