#!/usr/bin/env python3
from pathlib import Path
import json, csv
BASE=Path('/Users/joeldic/Documents/chess-puzzles')
JSON=BASE/'data'/'mating_patterns_100_by_theme.json'
TSV=BASE/'output'/'all_puzzles_list.tsv'

with TSV.open('r', encoding='utf-8') as f:
    rdr=csv.DictReader(f, delimiter='\t')
    meta={r['id']:r for r in rdr}

with JSON.open('r', encoding='utf-8') as f:
    data=json.load(f)

side_order={'white':0,'black':1}
mate_order={'m1':0,'m2':1,'m3+':2}

changed=0
for ch in data.get('chapters',[]):
    puzzles=ch.get('puzzles',[])
    def key(p):
        pid=p.get('id')
        m=meta.get(pid,{})
        side=m.get('side', p.get('side_to_move','')).lower()
        mo=m.get('mate_tier','')
        # normalize mate tier
        if mo.startswith('m1'):
            mo_k='m1'
        elif mo.startswith('m2'):
            mo_k='m2'
        else:
            mo_k='m3+'
        # sort: side (white then black), mate-tier (m1->m2->m3+),
        # then rating easiest->hardest (ascending), then popularity highest->lowest
        pop=int(m.get('popularity') or 0)
        rating=int(m.get('rating') or p.get('rating') or 0)
        return (side_order.get(side,1), mate_order.get(mo_k,2), rating, -pop, pid)
    newp=sorted(puzzles, key=key)
    # if order changed, update
    if [p['id'] for p in newp] != [p['id'] for p in puzzles]:
        ch['puzzles']=newp
        changed+=1
    # update chapter_puzzle_index sequentially
    for i,p in enumerate(ch['puzzles'], start=1):
        p['chapter_puzzle_index']=i

if changed:
    JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')

print('Reordered', changed, 'chapters (updated JSON).')
