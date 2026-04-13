#!/usr/bin/env python3
"""
Book inspector: summarise a puzzle JSON and optionally validate a generated .tex file.

Usage:
    python3 scripts/inspect_book.py data/mate_in_one_400.json
    python3 scripts/inspect_book.py data/mate_in_one_400.json output/mate_in_one_400.tex
    python3 scripts/inspect_book.py data/mating_patterns_100_by_theme.json output/mating_patterns_100_by_theme.tex

JSON output: per-chapter stats (puzzle count, piece distribution, rating range) + TSV written
             to output/<stem>.inspect.tsv

TeX validation checks:
    1.  No \\tableofcontents when toc: false (and vice-versa)
    2.  No [ILLEGAL MOVE strings
    3.  Puzzle count in tex matches JSON total
    4.  No duplicate puzzle display IDs in \\PuzzleCell calls
    5.  Blank pages only in known-good positions
    6.  Chapter boundaries use \\cleardoublepage (when chapter_title_pages: true)
    7.  Chapter boundaries use a recto-forcing pattern (when chapter_title_pages: true)
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"

PIECE_ORDER = ["Q", "R", "B", "N", "P", "K"]


# ── JSON inspection ───────────────────────────────────────────────────────────

def inspect_json(data: dict) -> tuple[list[str], list[str]]:
    """Return (summary_lines, warning_lines)."""
    lines: list[str] = []
    warnings: list[str] = []

    title    = data.get("title", "(untitled)")
    chapters = data.get("chapters", [])
    json_total = data.get("total_puzzle_count") or sum(
        len(ch.get("puzzles", [])) for ch in chapters
    )

    lines.append(f"Book:                {title}")
    lines.append(f"Author:              {data.get('author', '')}")
    lines.append(f"TOC:                 {data.get('toc', True)}")
    lines.append(f"Chapter title pages: {data.get('chapter_title_pages', True)}")
    lines.append(f"Chapters:            {len(chapters)}")
    lines.append(f"Total puzzles:       {json_total}")
    lines.append("")

    all_ids: list[str] = []

    for ch_idx, ch in enumerate(chapters, 1):
        ch_title  = ch.get("title") or ch.get("label", f"Chapter {ch_idx}")
        puzzles   = ch.get("puzzles", [])
        ch_total  = len(puzzles)
        white_ct  = sum(1 for p in puzzles if p.get("side_to_move") in ("w", "white"))
        black_ct  = ch_total - white_ct
        ratings   = [p["rating"] for p in puzzles if "rating" in p]
        rating_str = (
            f"rating {min(ratings)}–{max(ratings)}, avg {sum(ratings) // len(ratings)}"
            if ratings else "no ratings"
        )

        pieces: dict[str, int] = defaultdict(int)
        for p in puzzles:
            pieces[p.get("first_move_piece", "?")] += 1

        piece_parts = [f"{pc}:{pieces[pc]}" for pc in PIECE_ORDER if pieces[pc]]
        if pieces.get("?"):
            piece_parts.append(f"?:{pieces['?']}")
        piece_str = "  ".join(piece_parts)

        lines.append(f"  Chapter {ch_idx}: {ch_title!r}")
        lines.append(f"    {ch_total} puzzles  (white: {white_ct}, black: {black_ct})  {rating_str}")
        lines.append(f"    {piece_str}")

        ids = [p.get("puzzle_id") or p.get("id", "") for p in puzzles]
        all_ids.extend(ids)

    # Duplicate puzzle ID check
    lines.append("")
    seen_ids: set[str] = set()
    dup_ids: list[str] = []
    for pid in all_ids:
        if pid in seen_ids:
            dup_ids.append(pid)
        seen_ids.add(pid)

    if dup_ids:
        warnings.append(f"Duplicate puzzle IDs: {dup_ids[:10]}")
    else:
        lines.append("  ✅  No duplicate puzzle IDs in JSON")

    # Actual count vs declared count
    actual_count = len(all_ids)
    if json_total != actual_count:
        warnings.append(
            f"total_puzzle_count field says {json_total} but {actual_count} puzzles found in chapters"
        )

    return lines, warnings


# ── TSV output ────────────────────────────────────────────────────────────────

TSV_FIELDS = [
    "chapter_num", "chapter_title", "puzzle_num", "puzzle_id",
    "side_to_move", "first_move_piece", "rating", "nb_plays",
    "popularity", "opening_tags",
]


def write_tsv(data: dict, tsv_path: Path) -> int:
    rows: list[dict] = []
    global_num = 1
    for ch_idx, ch in enumerate(data.get("chapters", []), 1):
        ch_title = ch.get("title") or ch.get("label", f"Chapter {ch_idx}")
        for p in ch.get("puzzles", []):
            rows.append({
                "chapter_num":      ch_idx,
                "chapter_title":    ch_title,
                "puzzle_num":       global_num,
                "puzzle_id":        p.get("puzzle_id") or p.get("id", ""),
                "side_to_move":     p.get("side_to_move", ""),
                "first_move_piece": p.get("first_move_piece", ""),
                "rating":           p.get("rating", ""),
                "nb_plays":         p.get("nb_plays", ""),
                "popularity":       p.get("popularity", ""),
                "opening_tags":     p.get("opening_tags", ""),
            })
            global_num += 1

    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    with tsv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TSV_FIELDS, delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    return len(rows)


# ── TeX validation ────────────────────────────────────────────────────────────

class Check:
    def __init__(self, name: str, passed: bool, detail: str = ""):
        self.name   = name
        self.passed = passed
        self.detail = detail

    def __str__(self) -> str:
        icon = "✅" if self.passed else "❌"
        s = f"  {icon}  {self.name}"
        if self.detail:
            s += f"\n       {self.detail}"
        return s


def _window(lines: list[str], idx: int, before: int = 4, after: int = 2) -> str:
    return "\n".join(lines[max(0, idx - before) : idx + after + 1])


def validate_tex(tex: str, data: dict) -> list[Check]:
    checks: list[Check] = []
    lines = tex.splitlines()

    show_toc               = data.get("toc", True)
    show_chapter_titles    = data.get("chapter_title_pages", True)
    json_total = data.get("total_puzzle_count") or sum(
        len(ch.get("puzzles", [])) for ch in data.get("chapters", [])
    )

    # ── 1. \tableofcontents presence matches toc setting ─────────────────────
    has_toc_cmd = r"\tableofcontents" in tex
    if not show_toc:
        checks.append(Check(
            r"No \tableofcontents (toc: false)",
            not has_toc_cmd,
            r"Found \tableofcontents but toc: false" if has_toc_cmd else "",
        ))
    else:
        checks.append(Check(
            r"\tableofcontents present (toc: true)",
            has_toc_cmd,
            r"Missing \tableofcontents but toc: true" if not has_toc_cmd else "",
        ))

    # ── 2. No [ILLEGAL MOVE strings ───────────────────────────────────────────
    illegal_lines = [i + 1 for i, l in enumerate(lines) if "[ILLEGAL MOVE" in l]
    checks.append(Check(
        "No [ILLEGAL MOVE errors",
        not illegal_lines,
        f"Found at lines: {illegal_lines[:5]}" if illegal_lines else "",
    ))

    # ── 3. Puzzle count matches JSON ──────────────────────────────────────────
    puzzle_cells = re.findall(r"\\PuzzleCell\{([^}]+)\}", tex)
    count_match  = len(puzzle_cells) == json_total
    checks.append(Check(
        f"Puzzle count: tex={len(puzzle_cells)}, json={json_total}",
        count_match,
        f"Mismatch: {len(puzzle_cells)} in tex vs {json_total} in json" if not count_match else "",
    ))

    # ── 4. No duplicate puzzle display IDs in tex ─────────────────────────────
    seen_cells: set[str] = set()
    dup_cells: list[str] = []
    for cid in puzzle_cells:
        if cid in seen_cells:
            dup_cells.append(cid)
        seen_cells.add(cid)
    checks.append(Check(
        "No duplicate puzzle display IDs in tex",
        not dup_cells,
        f"Duplicates: {dup_cells[:10]}" if dup_cells else "",
    ))

    # ── 4b. All JSON puzzles present in tex (no gaps in display IDs) ──────────
    # Display IDs are assigned 1..N sequentially, so the set in tex must be
    # exactly {"1", "2", ..., str(json_total)} — any gap means a puzzle was dropped.
    expected_ids = {str(i) for i in range(1, json_total + 1)}
    actual_ids   = set(puzzle_cells)
    missing_ids  = sorted(expected_ids - actual_ids, key=int)
    extra_ids    = sorted(actual_ids - expected_ids, key=int)
    all_present  = not missing_ids and not extra_ids
    detail_parts = []
    if missing_ids:
        detail_parts.append(f"missing display IDs: {missing_ids[:10]}")
    if extra_ids:
        detail_parts.append(f"unexpected display IDs: {extra_ids[:10]}")
    checks.append(Check(
        f"All {json_total} JSON puzzles present in tex (no gaps)",
        all_present,
        "  ".join(detail_parts),
    ))

    # ── 5. Blank pages only in known-good positions ───────────────────────────
    #
    # Known-good patterns for \null\thispagestyle{empty}:
    #   (a) Front matter copyright page  — appears right after opening \thispagestyle{empty}
    #   (b) After a chapter title page   — on same line as \newpage\null\thispagestyle{empty}\newpage
    #   (c) Inside an \ifoddpage block   — context contains \ifoddpage or \checkoddpage
    #
    # Pattern (b) always appears as a single line:
    #   \newpage\null\thispagestyle{empty}\newpage
    # Pattern (a) appears on its own line within the front matter block (before \begin{document}).
    #
    bad_blanks: list[int] = []
    for i, line in enumerate(lines):
        if r"\null\thispagestyle{empty}" not in line:
            continue
        lineno = i + 1
        ctx = _window(lines, i, before=4, after=2)

        # Pattern (b): whole line is \newpage\null...\newpage  (after chapter title)
        is_after_title = line.strip() == r"\newpage\null\thispagestyle{empty}\newpage"
        # Pattern (c): inside an odd-page conditional
        is_in_oddpage  = r"\ifoddpage" in ctx or r"\checkoddpage" in ctx
        # Pattern (a): in front matter (before \begin{document})
        begin_doc_pos  = tex.find(r"\begin{document}")
        is_front_matter = begin_doc_pos > 0 and tex.find(line, 0, begin_doc_pos) != -1

        if not (is_after_title or is_in_oddpage or is_front_matter):
            bad_blanks.append(lineno)

    checks.append(Check(
        "Blank pages only in expected positions",
        not bad_blanks,
        f"Unexpected blank pages at lines: {bad_blanks}" if bad_blanks else "",
    ))

    # ── 6. Chapter boundaries use \cleardoublepage (chapter_title_pages: true) ─
    #       or a recto-forcing pattern (chapter_title_pages: false, advisory)
    #
    # Identify chapter starts by \addcontentsline{toc}{section}{...}
    chapter_start_lines = [
        i for i, l in enumerate(lines)
        if r"\addcontentsline{toc}{section}" in l
    ]

    if show_chapter_titles:
        # \cleardoublepage must appear before \addcontentsline.
        # The chapter_title_page() block is ~12 lines, so look back 20 to be safe.
        bad_starts: list[int] = []
        for idx in chapter_start_lines:
            lookback = _window(lines, idx, before=20, after=0)
            if r"\cleardoublepage" not in lookback:
                bad_starts.append(idx + 1)
        checks.append(Check(
            r"Chapter boundaries use \cleardoublepage (chapter_title_pages: true)",
            not bad_starts,
            f"Missing at lines: {bad_starts}" if bad_starts else "",
        ))

        # \newpage\null\thispagestyle{empty}\newpage must appear within 5 lines
        # AFTER each \addcontentsline (blank verso so puzzles land on recto)
        bad_verso: list[int] = []
        for idx in chapter_start_lines:
            lookahead = _window(lines, idx, before=0, after=5)
            if r"\null\thispagestyle{empty}" not in lookahead:
                bad_verso.append(idx + 1)
        checks.append(Check(
            "Chapter title pages followed by blank verso (puzzles start on recto)",
            not bad_verso,
            f"Missing blank verso after chapter at lines: {bad_verso}" if bad_verso else "",
        ))

    else:
        # chapter_title_pages: false — sections are invisible, content flows continuously.
        # Recto placement is not enforced in the current implementation; note if missing.
        recto_forced: list[int] = []
        for idx in chapter_start_lines:
            lookback = _window(lines, idx, before=4, after=0)
            if r"\checkoddpage" in lookback or r"\ifoddpage" in lookback:
                recto_forced.append(idx + 1)
        all_forced = len(recto_forced) == len(chapter_start_lines)
        checks.append(Check(
            "Chapter sections have recto-forcing (chapter_title_pages: false)",
            all_forced,
            (
                f"Sections at lines {[i + 1 for i in chapter_start_lines if i + 1 not in recto_forced]} "
                f"use plain \\newpage — content may start on verso. "
                f"Use force_next_content_to_recto() to enforce recto placement."
            ) if not all_forced else "",
        ))

    return checks


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect a puzzle book JSON and optionally validate its .tex output."
    )
    parser.add_argument("json_file", help="Path to the book JSON (e.g. data/mate_in_one_400.json)")
    parser.add_argument("tex_file", nargs="?", help="Path to the generated .tex (optional)")
    args = parser.parse_args()

    json_path = Path(args.json_file)
    if not json_path.is_absolute():
        json_path = BASE_DIR / json_path
    if not json_path.exists():
        print(f"Error: JSON not found: {json_path}", file=sys.stderr)
        sys.exit(1)

    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # ── JSON summary ─────────────────────────────────────────────────────────
    print("=" * 60)
    print("JSON SUMMARY")
    print("=" * 60)
    summary_lines, warnings = inspect_json(data)
    print("\n".join(summary_lines))
    for w in warnings:
        print(f"  ⚠️   {w}")

    # ── TSV ──────────────────────────────────────────────────────────────────
    tsv_path = OUTPUT_DIR / f"{json_path.stem}.inspect.tsv"
    row_count = write_tsv(data, tsv_path)
    print(f"\n  TSV written: {tsv_path.relative_to(BASE_DIR)}  ({row_count} rows)")

    # ── TeX validation ────────────────────────────────────────────────────────
    if args.tex_file:
        tex_path = Path(args.tex_file)
        if not tex_path.is_absolute():
            tex_path = BASE_DIR / tex_path
        if not tex_path.exists():
            print(f"\nError: tex file not found: {tex_path}", file=sys.stderr)
            sys.exit(1)

        tex = tex_path.read_text(encoding="utf-8")
        checks = validate_tex(tex, data)

        print()
        print("=" * 60)
        print("TEX VALIDATION")
        print("=" * 60)
        all_passed = True
        for c in checks:
            print(c)
            if not c.passed:
                all_passed = False

        print()
        if all_passed:
            print("All checks passed. ✅")
        else:
            print("Some checks FAILED. ❌")
            sys.exit(1)


if __name__ == "__main__":
    main()
