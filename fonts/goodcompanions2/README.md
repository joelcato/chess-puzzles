# GoodCompanions2 — Type 1 chess font for the `chessboard` LaTeX package

This directory contains everything needed to use the **GoodCompanions** chess
font (by Armando H. Marroquin, 2004) with Ulrike Fischer's `chessboard` /
`chessfss` LaTeX packages using the `LSB1` encoding.

**The generated font files (`PFB`, `AFM`, `TFM`, `FD`) are ready to install
directly — no need to run the conversion script yourself.**

## Files

| File | Purpose |
|------|---------|
| `chess-goodcompanions2-board-fig-raw.pfb` | Type 1 font (binary) — **install this** |
| `chess-goodcompanions2-board-fig-raw.afm` | Adobe Font Metrics — **install this** |
| `chess-goodcompanions2-lsb.tfm` | TeX Font Metrics for pdflatex — **install this** |
| `lsb1goodcompanions2.fd` | LaTeX font definition file — **install this** |
| `chess-goodcompanions2.map` | dvips/pdftex map entries — **append to your map** |
| `goodcompanions.ttf` | Original TTF source (used by `make_gc_pfb.py` to regenerate) |

## Installation (macOS / TeX Live)

```bash
# 1. Copy font files into your local texmf tree
cp chess-goodcompanions2-board-fig-raw.pfb  ~/Library/texmf/fonts/type1/chess/enpassant/
cp chess-goodcompanions2-board-fig-raw.afm  ~/Library/texmf/fonts/type1/chess/enpassant/
cp chess-goodcompanions2-board-fig-raw.afm  ~/Library/texmf/fonts/afm/chess/enpassant/
cp chess-goodcompanions2-lsb.tfm            ~/Library/texmf/fonts/tfm/chess/enpassant/
cp lsb1goodcompanions2.fd                   ~/Library/texmf/tex/latex/chessfss/enpassant/

# 2. Append map entries to the enpassant map file
cat chess-goodcompanions2.map >> $(kpsewhich chess-enpassant.map)

# 3. Refresh the TeX database and font maps
mktexlsr
updmap --user
```

## Usage in LaTeX

```latex
\usepackage[LSB1,T1]{fontenc}
\usepackage{chessboard}
\usepackage{chessfss}

\setchessboard{
  boardfontfamily=goodcompanions2,
  boardfontencoding=LSB1,
  boardfontsize=24pt
}
\chessboard[setfen=rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1]
```

## How it was made

The PFB was generated from `goodcompanions.ttf` using `scripts/make_gc_pfb.py`
(requires FontForge). The key challenge was that the TTF contains Latin glyphs
at the same Unicode codepoints as the chess-board.enc target glyph names —
solved by renaming to temporary `chess__<name>` names before deletion, then
renaming to final names.

## TTF glyph layout

| Unicode | TTF name | Chess piece |
|---------|----------|-------------|
| U+0030 | zero | WKingOnWhite |
| U+0031 | one | WKingOnBlack |
| U+0032 | two | BKingOnWhite |
| U+0033 | three | BKingOnBlack |
| U+0047 | G | WQueenOnWhite |
| U+0048 | H | WQueenOnBlack |
| U+0049 | I | BQueenOnWhite |
| U+004A | J | BQueenOnBlack |
| U+0057 | W | WRookOnWhite |
| U+0058 | X | WRookOnBlack |
| U+0059 | Y | BRookOnWhite |
| U+005A | Z | BRookOnBlack |
| U+006D | m | WBishopOnWhite |
| U+006E | n | WBishopOnBlack |
| U+006F | o | BBishopOnWhite |
| U+0070 | p | BBishopOnBlack |
| U+00A3 | sterling | LightSquare |
| U+00A4 | currency | DarkSquare |
| U+00A9 | copyright | WKnightOnWhite |
| U+00AA | ordfeminine | WKnightOnBlack |
| U+00AB | guillemotleft | BKnightOnWhite |
| U+00AC | logicalnot | BKnightOnBlack |
| U+00B9 | onesuperior | WPawnOnWhite |
| U+00BA | ordmasculine | WPawnOnBlack |
| U+00BB | guillemotright | BPawnOnWhite |
| U+00BC | onequarter | BPawnOnBlack |
