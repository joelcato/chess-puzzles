#!/usr/bin/env python3
from pathlib import Path
import csv, json, sys

BASE=Path('/Users/joeldic/Documents/chess-puzzles')
TSV=BASE/'output'/'all_puzzles_list.tsv'
BACK=BASE/'output'/'all_puzzles_list.bak.tsv'
JSON=BASE/'data'/'mating_patterns_100_by_theme.json'

# read existing TSV into dict by id
rows_by_id={}
header=None
if TSV.exists():
    with TSV.open('r', encoding='utf-8') as f:
        rdr=csv.DictReader(f, delimiter='\t')
        header=rdr.fieldnames
        for r in rdr:
            rows_by_id[r['id']]=r
else:
    print('TSV not found:', TSV)
    sys.exit(1)

# read JSON ordering
with JSON.open('r', encoding='utf-8') as f:
    data=json.load(f)

out_rows=[]
missing_ids=[]
chapter_count=0
for ch in data.get('chapters',[]):
    chapter_count+=1
    for p in ch.get('puzzles',[]):
        pid=p.get('id')
        if not pid:
            continue
        if pid in rows_by_id:
            row=rows_by_id[pid].copy()
            # update chapter_index and label to match JSON
            row['chapter_index']=str(ch.get('chapter_index', row.get('chapter_index','')))
            row['chapter_label']=ch.get('label', row.get('chapter_label',''))
            out_rows.append(row)
        else:
            # build minimal row from JSON
            missing_ids.append(pid)
            row={}
            # preserve header order
            for h in header:
                row[h]=''
            row['id']=pid
            row['chapter_index']=str(ch.get('chapter_index',''))
            row['chapter_label']=ch.get('label','')
            row['rating']=str(p.get('rating',''))
            row['side']=p.get('side_to_move','')
            moves=p.get('moves',[])
            row['moves_full']=' '.join(moves) if moves else ''
            # naive remaining moves: moves - 1
            try:
                row['remaining_moves']=str(max(0, len(moves)-1))
            except Exception:
                row['remaining_moves']=''
            out_rows.append(row)

# backup old TSV
BACK_written=False
if TSV.exists():
    TSV.replace(BACK)
    BACK_written=True

# write new TSV
with TSV.open('w', encoding='utf-8', newline='') as f:
    w=csv.DictWriter(f, fieldnames=header, delimiter='\t')
    w.writeheader()
    for r in out_rows:
        # ensure all header fields present
        out={h: r.get(h,'') for h in header}
        w.writerow(out)

print('Wrote', len(out_rows), 'rows to', TSV)
if BACK_written:
    print('Backup saved to', BACK)
if missing_ids:
    print('Missing metadata for', len(missing_ids), 'puzzles (IDs shown):')
    print(','.join(missing_ids[:50]))

# quick verification: check for each chapter whether first 4 rows are m1
from collections import defaultdict
chap_rows=defaultdict(list)
with TSV.open('r', encoding='utf-8') as f:
    rdr=csv.DictReader(f, delimiter='\t')
    for r in rdr:
        chap_rows[int(r['chapter_index'])].append(r)

bad_first4=[]
for ci,rs in chap_rows.items():
    first4=rs[:4]
    if len(first4)<4:
        bad_first4.append((ci,'too_few_rows',len(first4)))
        continue
    if not all(r.get('mate_tier','').startswith('m1') for r in first4):
        bad_first4.append((ci, 'first4_not_all_m1'))

print('Chapters with first-4 not all m1:', len(bad_first4))
if bad_first4:
    print(bad_first4[:10])

print('Done')
