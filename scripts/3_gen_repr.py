#!/usr/bin/env python3
"""
  python3 3_gen_repr.py --code "asdf.js" --label "$LABEL" --out ".asdf.slices.jsonl"
"""
import argparse, json, os, re
from pathlib import Path

CSEP = "\n/* ==== NEXT NODE ==== */\n"

re_line_comment = re.compile(r"(^|[^:])//.*?$", re.M)
re_block_comment = re.compile(r"/\*.*?\*/", re.S)


def strip_comments(code: str) -> str:
    code = re_block_comment.sub("", code)
    code = re_line_comment.sub(lambda m: m.group(1), code)
    return code


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--code', required=True)
    ap.add_argument('--pdg')
    ap.add_argument('--parts')
    ap.add_argument('--label', choices=['yes','no'], required=True)
    ap.add_argument('--out')
    ap.add_argument('--strip_comments', action='store_true')
    ap.add_argument('--max_chars', type=int, default=2000)
    args = ap.parse_args()

    base_path = Path(args.code)
    stem = base_path.stem
    parent = base_path.parent

    if not args.pdg:
        args.pdg = str(parent / f"{stem}.json")
    if not args.parts:
        args.parts = str(parent / f"{stem}.part.json")
    if not args.out:
        args.out = str(parent / f"{stem}.slices.jsonl")

    # print(f"[auto-path] pdg={args.pdg} parts={args.parts} out={args.out}")

    pdg = load_json(args.pdg)
    parts = load_json(args.parts)
    code = base_path.read_text(encoding='utf-8', errors='ignore')
    if args.strip_comments:
        code_nocom = strip_comments(code)
    else:
        code_nocom = code

    nodes = { n['id']: n for n in pdg['nodes'] }

    base = Path(args.code).stem
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, 'w', encoding='utf-8') as w:
        for p in parts:
            pid = p.get('part_id')
            nids = p.get('nodes') or p
            spans = []
            for nid in nids:
                n = nodes.get(nid)
                if not n:
                    continue
                s = int(n.get('start', 0)); e = int(n.get('end', 0))
                if e <= s:
                    continue
                spans.append((s, e, nid))
            spans.sort(key=lambda x: (x[0], x[1]))

            chunks = []
            ranges = []
            acc = 0
            for s, e, nid in spans:
                frag = code_nocom[s:e]
                if acc + len(frag) + len(CSEP) > args.max_chars:
                    remain = max(0, args.max_chars - acc)
                    if remain > 0:
                        chunks.append(frag[:remain])
                        ranges.append([s, min(e, s+remain)])
                        acc += remain
                    break
                chunks.append(frag)
                ranges.append([s, e])
                acc += len(frag) + len(CSEP)
            if not chunks:
                continue
            text = CSEP.join(chunks)

            ex = {
                'id': f"{base}-p{pid}",
                'part_id': pid,
                'label': args.label,
                'text': text,
                'nodes': [nid for _,_,nid in spans],
                'ranges': ranges,
                'meta': {
                    'file': str(Path(args.code).name),
                    'max_chars': args.max_chars,
                    'strip_comments': bool(args.strip_comments)
                }
            }
            w.write(json.dumps(ex, ensure_ascii=False) + "\n")

    # print(f"wrote slices: {out_path}")
    # print(f"wrote slices")

if __name__ == '__main__':
    main()
