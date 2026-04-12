#!/usr/bin/env python3
"""
Convert goodcompanions.ttf to a Type 1 .pfb suitable for use with
the chessboard LaTeX package (chess-board.enc encoding).

GoodCompanions TTF glyph layout (confirmed via fontforge + visual inspection):
  U+0030 (zero)           = WKingOnWhite
  U+0031 (one)            = WKingOnBlack
  U+0032 (two)            = BKingOnWhite
  U+0033 (three)          = BKingOnBlack
  U+0047 (G)              = WQueenOnWhite
  U+0048 (H)              = WQueenOnBlack
  U+0049 (I)              = BQueenOnWhite
  U+004A (J)              = BQueenOnBlack
  U+0057 (W)              = WRookOnWhite
  U+0058 (X)              = WRookOnBlack
  U+0059 (Y)              = BRookOnWhite
  U+005A (Z)              = BRookOnBlack
  U+006D (m)              = WBishopOnWhite
  U+006E (n)              = WBishopOnBlack
  U+006F (o)              = BBishopOnWhite
  U+0070 (p)              = BBishopOnBlack
  U+00A3 (sterling)       = LightSquare (empty)
  U+00A4 (currency)       = DarkSquare (striped)
  U+00A9 (copyright)      = WKnightOnWhite
  U+00AA (ordfeminine)    = WKnightOnBlack
  U+00AB (guillemotleft)  = BKnightOnWhite
  U+00AC (logicalnot)     = BKnightOnBlack
  U+00B9 (onesuperior)    = WPawnOnWhite
  U+00BA (ordmasculine)   = WPawnOnBlack
  U+00BB (guillemotright) = BPawnOnWhite
  U+00BC (onequarter)     = BPawnOnBlack

  Note: the font also contains rotated/flipped variants of each piece at
  nearby codepoints (e.g. K,M,S,U = right/upside-down/left queen variants)
  — those are not needed by chessboard and are discarded.

chess-board.enc target glyph names:
  asterisk=LightSq  plus=DarkSq
  k=WKingOnWhite    K=WKingOnBlack    l=BKingOnWhite    L=BKingOnBlack
  q=WQueenOnWhite   Q=WQueenOnBlack   w=BQueenOnWhite   W=BQueenOnBlack
  r=WRookOnWhite    R=WRookOnBlack    t=BRookOnWhite    T=BRookOnBlack
  b=WBishopOnWhite  B=WBishopOnBlack  v=BBishopOnWhite  V=BBishopOnBlack
  n=WKnightOnWhite  N=WKnightOnBlack  m=BKnightOnWhite  M=BKnightOnBlack
  p=WPawnOnWhite    P=WPawnOnBlack    o=BPawnOnWhite    O=BPawnOnBlack

chess-board.enc slot -> glyph name mapping:
  0x30 ( 48)  asterisk   = white/light square  (TTF: zero)
  0x41 ( 65)  B          = WBishopOnBlack
  0x42 ( 66)  b          = WBishopOnWhite
  0x4A ( 74)  K          = WKingOnBlack
  0x4B ( 75)  k          = WKingOnWhite
  0x4C ( 76)  Q          = WQueenOnBlack
  0x4D ( 77)  N          = WKnightOnBlack
  0x4E ( 78)  n          = WKnightOnWhite
  0x4F ( 79)  P          = WPawnOnBlack
  0x50 ( 80)  p          = WPawnOnWhite
  0x51 ( 81)  q          = WQueenOnWhite
  0x52 ( 82)  r          = WRookOnWhite
  0x53 ( 83)  R          = WRookOnBlack
  0x5A ( 90)  plus       = black/dark square   (TTF: two)
  0x61 ( 97)  V          = BBishopOnBlack
  0x62 ( 98)  v          = BBishopOnWhite
  0x6A (106)  L          = BKingOnBlack
  0x6B (107)  l          = BKingOnWhite
  0x6C (108)  W          = BQueenOnBlack
  0x6D (109)  M          = BKnightOnBlack
  0x6E (110)  m          = BKnightOnWhite
  0x6F (111)  O          = BPawnOnBlack
  0x70 (112)  o          = BPawnOnWhite
  0x71 (113)  w          = BQueenOnWhite
  0x72 (114)  t          = BRookOnWhite
  0x73 (115)  T          = BRookOnBlack

Strategy: open the TTF, rename/re-unicode glyphs so each lands at its target
slot, strip everything else, then export as Type 1.
"""
import fontforge
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TTF = os.path.join(SCRIPT_DIR, "../fonts/goodcompanions2/goodcompanions.ttf")
OUT_DIR = "/Users/joeldic/Library/texmf/fonts/type1/chess/enpassant"
OUT_NAME = "chess-goodcompanions2-board-fig-raw"

# Maps: GoodCompanions Unicode codepoint -> target glyph name (per chess-board.enc)
# TTF viewer showed GLYPH INDEX; actual Unicode values = index offset by 4 non-Unicode glyphs
# Within each group of 4: [0]=BpieceOnWhite, [1]=BpieceOnBlack, [2]=WpieceOnWhite, [3]=WpieceOnBlack
#
# Index 4=U+0030(zero) .. 7=U+0033(three)           -> Kings
# Index 20=U+0047(G)   .. 23=U+004A(J)              -> Queens
# Index 36=U+0057(W)   .. 39=U+005A(Z)              -> Rooks
# Index 52=U+006D(m)   .. 55=U+0070(p)              -> Bishops
# Index 66=glyph66 (no unicode, blank)               -> LightSquare
# Index 69=U+00A3(sterling) full dark fill           -> DarkSquare
# Index 75=U+00A9(copyright) .. 78=U+00AC(logicalnot) -> Knights
# Index 91=U+00B9(onesuperior) .. 94=U+00BC(onequarter) -> Pawns
GLYPH_MAP = {
    # Kings: [0]=BKingOnWhite [1]=BKingOnBlack [2]=WKingOnWhite [3]=WKingOnBlack
    # But user reports white/black swapped -> actual order is W,W,B,B... 
    # Re-reading user: "black on white, black on black, white on white, white on black"
    # but pieces came out swapped -> swap W and B assignments
    0x0030: "k",          # zero          WKingOnWhite  (was reported as BKingOnWhite)
    0x0031: "K",          # one           WKingOnBlack
    0x0032: "l",          # two           BKingOnWhite
    0x0033: "L",          # three         BKingOnBlack
    0x0047: "q",          # G             WQueenOnWhite
    0x0048: "Q",          # H             WQueenOnBlack
    0x0049: "w",          # I             BQueenOnWhite
    0x004A: "W",          # J             BQueenOnBlack
    0x0057: "r",          # W             WRookOnWhite
    0x0058: "R",          # X             WRookOnBlack
    0x0059: "t",          # Y             BRookOnWhite
    0x005A: "T",          # Z             BRookOnBlack
    0x006D: "b",          # m             WBishopOnWhite
    0x006E: "B",          # n             WBishopOnBlack
    0x006F: "v",          # o             BBishopOnWhite
    0x0070: "V",          # p             BBishopOnBlack
    0x00A3: "asterisk",   # sterling      LightSquare (plain empty square)
    0x00A4: "plus",       # currency      DarkSquare (striped/dark fill)
    0x00A9: "n",          # copyright     WKnightOnWhite
    0x00AA: "N",          # ordfeminine   WKnightOnBlack
    0x00AB: "m",          # guillemotleft BKnightOnWhite
    0x00AC: "M",          # logicalnot    BKnightOnBlack
    0x00B9: "p",          # onesuperior   WPawnOnWhite
    0x00BA: "P",          # ordmasculine  WPawnOnBlack
    0x00BB: "o",          # guillemotright BPawnOnWhite
    0x00BC: "O",          # onequarter    BPawnOnBlack
}

font = fontforge.open(TTF)
font.fontname = "GC2004D2"
font.fullname = "GoodCompanions2"
font.familyname = "GoodCompanions2"

# Step 1: Rename each wanted glyph to a unique temp name (chess__<name>)
# so it can't collide with any existing glyph name during deletion.
temp_prefix = "chess__"
for src_unicode, dst_name in GLYPH_MAP.items():
    found = False
    for g in font.glyphs():
        if g.unicode == src_unicode:
            print(f"  U+{src_unicode:04X} ({g.glyphname}) -> temp '{temp_prefix}{dst_name}'")
            g.glyphname = temp_prefix + dst_name
            found = True
            break
    if not found:
        print(f"WARNING: no glyph at U+{src_unicode:04X}")

# Step 2: Delete every glyph that does NOT have the temp prefix.
keep_names = {temp_prefix + name for name in GLYPH_MAP.values()} | {".notdef"}
to_delete = [g.glyphname for g in font.glyphs() if g.glyphname not in keep_names]
for name in to_delete:
    if name in font:
        font[name].unlinkRef()
        font.removeGlyph(name)

# Step 3: Rename from temp names to final chess-board.enc names.
for dst_name in GLYPH_MAP.values():
    temp_name = temp_prefix + dst_name
    if temp_name in font:
        font[temp_name].glyphname = dst_name

print(f"\nKept {len(GLYPH_MAP)} glyphs, removed {len(to_delete)} others.")

out_path = os.path.join(OUT_DIR, OUT_NAME)
font.generate(out_path + ".pfb")
font.generate(out_path + ".afm")
print(f"Generated: {out_path}.pfb")
print(f"Generated: {out_path}.afm")
