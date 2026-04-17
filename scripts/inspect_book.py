#!/usr/bin/env python3
"""
Book inspector: summarise a puzzle JSON and optionally validate a generated .tex file.

Usage:
    python3 scripts/inspect_book.py data/mate_in_one_400.json
    python3 scripts/inspect_book.py data/mate_in_one_400.json output/mate_in_one_400.tex
    python3 scripts/inspect_book.py data/mate_in_one_400.json output/mate_in_one_400.tex --config configs/mate_in_one_400.yaml
    python3 scripts/inspect_book.py data/mating_patterns_100_by_theme.json output/mating_patterns_100_by_theme.tex

JSON output: per-chapter stats (puzzle count, piece distribution, rating range) + book
             profile (side/piece/rating distributions, top openings) + TSV written
             to output/<stem>.inspect.tsv

TeX validation checks:
    1.  No \\tableofcontents when toc: false (and vice-versa)
    2.  No [ILLEGAL MOVE strings
    3.  Puzzle count in tex matches JSON total
    4.  No duplicate puzzle display IDs in \\PuzzleCell calls
    5.  Blank pages only in known-good positions
    6.  Chapter boundaries use \\cleardoublepage (when chapter_title_pages: true)
    7.  Chapter title pages followed by blank verso (when chapter_title_pages: true)
    8b. Chapter sections use plain page break — no recto-forcing (when chapter_title_pages: false)

JSON extra checks:
    8.  No duplicate puzzle IDs across all chapters
    9.  No castling moves in King-piece puzzles (first_move_piece == K)
    10. (optional, --config) per-chapter puzzle counts match YAML config targets
"""

import argparse
import csv
import json
import re
import sys
import time
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
        # Iterate in render order (white first, then black) so puzzle_num and
        # side_to_move match the actual book layout.
        groups = ch.get("groups", {})
        if groups:
            ordered: list[dict] = []
            ordered.extend(groups.get("white_to_move", []))
            ordered.extend(groups.get("black_to_move", []))
        else:
            ordered = ch.get("puzzles", [])
        for p in ordered:
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


# ── Book profile ─────────────────────────────────────────────────────────────

def build_profile(data: dict) -> list[str]:
    """Return formatted lines for the BOOK PROFILE section."""
    all_puzzles = [p for ch in data.get("chapters", []) for p in ch.get("puzzles", [])]
    n = len(all_puzzles)
    if n == 0:
        return ["  (no puzzles)"]

    lines: list[str] = []

    # ── Side distribution ─────────────────────────────────────────────────────
    side_counts: dict[str, int] = defaultdict(int)
    for p in all_puzzles:
        s = p.get("side_to_move", "?")
        label = "White" if s in ("w", "white") else "Black" if s in ("b", "black") else s.capitalize()
        side_counts[label] += 1

    lines.append("  Side to move:")
    for side in ["White", "Black"]:
        ct = side_counts.get(side, 0)
        lines.append(f"    {side:<8} {ct:>4}  ({100 * ct / n:4.1f}%)")
    lines.append("")

    # ── Piece distribution ────────────────────────────────────────────────────
    piece_counts: dict[str, int] = defaultdict(int)
    for p in all_puzzles:
        piece_counts[p.get("first_move_piece", "?").upper()] += 1

    lines.append("  Piece (first move):")
    for pc in PIECE_ORDER:
        ct = piece_counts.get(pc, 0)
        if ct:
            lines.append(f"    {pc}   {ct:>4}  ({100 * ct / n:4.1f}%)")
    if piece_counts.get("?"):
        lines.append(f"    ?   {piece_counts['?']:>4}  ({100 * piece_counts['?'] / n:4.1f}%)")
    lines.append("")

    # ── Rating distribution (200-pt bands) ────────────────────────────────────
    ratings = [p["rating"] for p in all_puzzles if isinstance(p.get("rating"), int)]
    if ratings:
        BAND = 200
        lo_band = (min(ratings) // BAND) * BAND
        hi_band = ((max(ratings) // BAND) + 1) * BAND
        band_counts: dict[int, int] = {b: 0 for b in range(lo_band, hi_band, BAND)}
        for r in ratings:
            band_counts[(r // BAND) * BAND] += 1

        max_ct = max(band_counts.values()) or 1
        BAR_WIDTH = 24
        lines.append(f"  Rating distribution (200-pt bands):")
        lines.append(f"    {'Band':<11}  {'Count':>5}  {'%':>5}   histogram")
        lines.append(f"    {'─' * 11}  {'─' * 5}  {'─' * 5}   {'─' * BAR_WIDTH}")
        for b, ct in sorted(band_counts.items()):
            if ct == 0:
                continue
            bar = "█" * max(1, round(BAR_WIDTH * ct / max_ct))
            lines.append(f"    {b:4d}–{b + BAND - 1:<4d}   {ct:>5}  {100 * ct / n:4.1f}%   {bar}")
        lines.append("")

    # ── Top openings ─────────────────────────────────────────────────────────
    opening_counts: dict[str, int] = defaultdict(int)
    for p in all_puzzles:
        tags = (p.get("opening_tags") or "").strip()
        if tags:
            # Take the first tag as the opening family
            opening_counts[tags.split()[0]] += 1
    if opening_counts:
        top = sorted(opening_counts.items(), key=lambda x: -x[1])[:10]
        lines.append("  Top openings (first tag, top 10):")
        for name, ct in top:
            lines.append(f"    {name:<45}  {ct:>4}  ({100 * ct / n:4.1f}%)")
        no_opening = n - sum(opening_counts.values())
        if no_opening:
            lines.append(f"    {'(no opening tag)':<45}  {no_opening:>4}  ({100 * no_opening / n:4.1f}%)")
        lines.append("")

    return lines


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

    # ── 3b. Puzzle numbering is sequential (1, 2, 3 … N) ─────────────────────
    out_of_order = [
        (i + 1, int(cid))
        for i, cid in enumerate(puzzle_cells)
        if not cid.isdigit() or int(cid) != i + 1
    ]
    sequential = not out_of_order
    if out_of_order:
        examples = ", ".join(
            f"pos {pos}: got {got}" for pos, got in out_of_order[:5]
        )
        seq_detail = f"Non-sequential IDs ({len(out_of_order)} total): {examples}"
    else:
        seq_detail = ""
    checks.append(Check(
        "Puzzle numbering is sequential (1 … N)",
        sequential,
        seq_detail,
    ))
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

    # ── 4c. Puzzle render order in TeX matches JSON group order ───────────────
    # Extract (display_id, fen) pairs from the TeX in document order.
    tex_ordered_fens = re.findall(r"\\PuzzleCell\{[^}]+\}\{([^}]+)\}", tex)
    # Build expected FEN order from JSON: white_to_move first, then black_to_move.
    json_ordered_fens: list[str] = []
    for ch in data.get("chapters", []):
        groups = ch.get("groups", {})
        if groups:
            for p in groups.get("white_to_move", []):
                json_ordered_fens.append(p.get("display_fen") or p.get("fen", ""))
            for p in groups.get("black_to_move", []):
                json_ordered_fens.append(p.get("display_fen") or p.get("fen", ""))
        else:
            for p in ch.get("puzzles", []):
                json_ordered_fens.append(p.get("display_fen") or p.get("fen", ""))
    order_mismatches = [
        i + 1
        for i, (tf, jf) in enumerate(zip(tex_ordered_fens, json_ordered_fens))
        if tf != jf
    ]
    order_ok = not order_mismatches and len(tex_ordered_fens) == len(json_ordered_fens)
    if order_mismatches:
        order_detail = f"FEN mismatch at positions: {order_mismatches[:5]}"
    elif len(tex_ordered_fens) != len(json_ordered_fens):
        order_detail = f"FEN count differs: tex={len(tex_ordered_fens)}, json={len(json_ordered_fens)}"
    else:
        order_detail = ""
    checks.append(Check(
        "TeX puzzle order matches JSON render order",
        order_ok,
        order_detail,
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
        # chapter_title_pages: false — chapters flow continuously; no recto-forcing expected.
        bad_recto: list[int] = []
        for idx in chapter_start_lines:
            lookback = _window(lines, idx, before=4, after=0)
            if r"\checkoddpage" in lookback or r"\ifoddpage" in lookback:
                bad_recto.append(idx + 1)
        checks.append(Check(
            "Chapter sections use plain page break (no recto-forcing)",
            not bad_recto,
            f"Unexpected recto-forcing at lines: {bad_recto}" if bad_recto else "",
        ))

    return checks


def check_config_counts(data: dict, config: dict) -> list[Check]:
    """Cross-check per-chapter puzzle counts and piece distributions against
    the YAML config's declared set counts."""
    checks: list[Check] = []
    chapters_spec = config.get("chapters", [])
    chapters_data = data.get("chapters", [])

    # ── Total puzzle count at a glance ────────────────────────────────────────
    expected_grand_total = sum(
        sum(s.get("count", 0) for s in ch.get("sets", []))
        for ch in chapters_spec
    )
    actual_grand_total = sum(len(ch.get("puzzles", [])) for ch in chapters_data)
    grand_ok = actual_grand_total == expected_grand_total
    grand_detail = (
        f"short by {expected_grand_total - actual_grand_total}"
        if not grand_ok else ""
    )
    checks.append(Check(
        f"Total puzzles: {actual_grand_total} / expected {expected_grand_total}",
        grand_ok,
        grand_detail,
    ))

    if len(chapters_spec) != len(chapters_data):
        checks.append(Check(
            "YAML chapter count matches JSON",
            False,
            f"YAML has {len(chapters_spec)} chapters, JSON has {len(chapters_data)}",
        ))
        return checks

    checks.append(Check("YAML chapter count matches JSON", True))

    for ch_idx, (ch_spec, ch_data) in enumerate(zip(chapters_spec, chapters_data), 1):
        sets = ch_spec.get("sets", [])
        expected_total = sum(s.get("count", 0) for s in sets)
        actual_total = len(ch_data.get("puzzles", []))

        # Per-piece expected counts from set specs
        piece_expected: dict[str, int] = defaultdict(int)
        for s in sets:
            piece = s.get("first_move_piece", "").upper()
            cnt = s.get("count", 0)
            if piece:
                piece_expected[piece] += cnt

        # Per-piece actual counts
        piece_actual: dict[str, int] = defaultdict(int)
        for p in ch_data.get("puzzles", []):
            pc = (p.get("first_move_piece") or "?").upper()
            piece_actual[pc] += 1

        ch_title = ch_spec.get("title", f"Chapter {ch_idx}")
        count_ok = actual_total == expected_total

        if count_ok:
            checks.append(Check(
                f"Ch{ch_idx} '{ch_title}': total count",
                True,
            ))
        else:
            # Build per-set breakdown using set_deliveries stored in JSON
            set_deliveries = ch_data.get("set_deliveries", [])
            _SIDE = {"white": "w", "black": "b", "w": "w", "b": "b"}
            failing_lines: list[str] = []
            n_pass = 0
            for si, s_spec in enumerate(sets):
                req = s_spec.get("count", 0)
                delivered = (
                    set_deliveries[si]["count_delivered"]
                    if si < len(set_deliveries) else "?"
                )
                if delivered == req:
                    n_pass += 1
                else:
                    side_abbr = _SIDE.get(str(s_spec.get("side_to_move", "")).lower(), "?")
                    rating = s_spec.get("rating")
                    rating_str = f"{rating[0]}\u2013{rating[1]}" if rating else "any"
                    piece = s_spec.get("first_move_piece", "")
                    piece_str = f"  {piece.upper()}" if piece else ""
                    failing_lines.append(
                        f"\u2717  Set {si:2d}  {side_abbr}  {rating_str:<11}{piece_str}  req {req}, got {delivered}"
                    )
            n_fail = len(sets) - n_pass
            header = (
                f"expected {expected_total}, got {actual_total}"
                f"  ({len(sets)} sets: {n_pass} \u2713, {n_fail} \u2717)"
            )
            detail = "\n       ".join([header] + failing_lines)
            checks.append(Check(
                f"Ch{ch_idx} '{ch_title}': total count",
                False,
                detail,
            ))

        # Per-piece count check
        for piece, exp_count in piece_expected.items():
            act_count = piece_actual.get(piece, 0)
            piece_ok = act_count == exp_count
            piece_detail = "" if piece_ok else f"expected {exp_count}, got {act_count}"
            checks.append(Check(
                f"Ch{ch_idx} '{ch_title}': {piece} count",
                piece_ok,
                piece_detail,
            ))

    return checks


# ── Tee stdout to file ───────────────────────────────────────────────────────

class _Tee:
    """Write to both a file and the original stdout simultaneously."""
    def __init__(self, file_path: Path, original):
        self._file = file_path.open("w", encoding="utf-8")
        self._orig = original

    def write(self, data: str) -> int:
        self._file.write(data)
        return self._orig.write(data)

    def flush(self) -> None:
        self._file.flush()
        self._orig.flush()

    def close(self) -> None:
        self._file.close()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect a puzzle book JSON and optionally validate its .tex output."
    )
    parser.add_argument("json_file", help="Path to the book JSON (e.g. data/mate_in_one_400.json)")
    parser.add_argument("tex_file", nargs="?", help="Path to the generated .tex (optional)")
    parser.add_argument(
        "--config", default=None,
        help="Path to the YAML config (e.g. configs/mate_in_one_400.yaml); enables count cross-checks",
    )
    args = parser.parse_args()

    json_path = Path(args.json_file)
    if not json_path.is_absolute():
        json_path = BASE_DIR / json_path
    if not json_path.exists():
        print(f"Error: JSON not found: {json_path}", file=sys.stderr)
        sys.exit(1)

    t_start = time.perf_counter()

    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # ── Tee stdout to report file ─────────────────────────────────────────────
    report_path = OUTPUT_DIR / f"{json_path.stem}.inspect.txt"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tee = _Tee(report_path, sys.stdout)
    sys.stdout = tee  # type: ignore

    try:
        passed = _run(args, data, json_path, t_start)
    finally:
        sys.stdout = tee._orig
        tee.close()

    print(f"  Report written: {report_path.relative_to(BASE_DIR)}")
    if not passed:
        sys.exit(1)


def _run(args, data: dict, json_path: Path, t_start: float) -> None:
    t0 = time.perf_counter()
    print("=" * 60)
    print("JSON SUMMARY")
    print("=" * 60)
    summary_lines, warnings = inspect_json(data)
    print("\n".join(summary_lines))
    for w in warnings:
        print(f"  \u26a0\ufe0f   {w}")
    print(f"\n  [JSON checks: {time.perf_counter() - t0:.3f}s]")

    # ── Book profile ─────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("BOOK PROFILE")
    print("=" * 60)
    print()
    for line in build_profile(data):
        print(line)

    # ── TSV ──────────────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    tsv_path = OUTPUT_DIR / f"{json_path.stem}.inspect.tsv"
    row_count = write_tsv(data, tsv_path)
    print(f"  TSV written: {tsv_path.relative_to(BASE_DIR)}  ({row_count} rows)  [{time.perf_counter() - t0:.3f}s]")

    all_passed = not warnings

    # ── YAML config cross-check ───────────────────────────────────────────────
    if args.config:
        try:
            import yaml  # type: ignore
        except ImportError:
            print("\n  [--config skipped: pyyaml not installed]", file=sys.stderr)
        else:
            config_path = Path(args.config)
            if not config_path.is_absolute():
                config_path = BASE_DIR / config_path
            if not config_path.exists():
                print(f"\nError: config not found: {config_path}", file=sys.stderr)
            else:
                t0 = time.perf_counter()
                with config_path.open() as f:
                    config = yaml.safe_load(f)
                config_checks = check_config_counts(data, config)
                print()
                print("=" * 60)
                print("CONFIG CROSS-CHECK")
                print("=" * 60)
                for c in config_checks:
                    print(c)
                    if not c.passed:
                        all_passed = False
                print(f"\n  [config checks: {time.perf_counter() - t0:.3f}s]")

    # ── TeX validation ────────────────────────────────────────────────────────
    if args.tex_file:
        tex_path = Path(args.tex_file)
        if not tex_path.is_absolute():
            tex_path = BASE_DIR / tex_path
        if not tex_path.exists():
            print(f"\nError: tex file not found: {tex_path}", file=sys.stderr)
            return False

        t0 = time.perf_counter()
        tex = tex_path.read_text(encoding="utf-8")
        checks = validate_tex(tex, data)

        print()
        print("=" * 60)
        print("TEX VALIDATION")
        print("=" * 60)
        for c in checks:
            print(c)
            if not c.passed:
                all_passed = False
        print(f"\n  [tex checks: {time.perf_counter() - t0:.3f}s]")

    print()
    print(f"Total time: {time.perf_counter() - t_start:.3f}s")
    print()
    if all_passed:
        print("All checks passed. \u2705")
        return True
    else:
        print("Some checks FAILED. \u274c")
        return False


if __name__ == "__main__":
    main()
