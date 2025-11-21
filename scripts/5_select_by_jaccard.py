#!/usr/bin/env python3
import sys, re, os, argparse
from pathlib import Path
from multiprocessing import Pool, cpu_count
from tqdm import tqdm
from datasketch import MinHash

K = 305       
NUM_PERM = 128
PROCS = 16    
BLOCK = 4096  
OUT_PATH = Path("selected_305.txt")
TOK_RE = re.compile(r"[A-Za-z_]\w+|==|!=|<=|>=|=>|&&|\|\||\d+|'[^']*'|\"[^\"]*\"")
READ_CAP = None

def read_text(p: str) -> str:
    try:
        if READ_CAP is None:
            with open(p, "rb") as f: data = f.read()
        else:
            sz = os.path.getsize(p)
            with open(p, "rb") as f: data = f.read(min(sz, READ_CAP))
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""

def tokenize(s: str):
    return TOK_RE.findall(s)

def build_sig(args):
    i, path, seed = args
    s = read_text(path)
    m = MinHash(num_perm=NUM_PERM, seed=seed)
    toks = tokenize(s)
    if toks:
        m.update_batch([t.encode("utf-8") for t in toks])
    return i, m

def blocks(n, b):
    for i0 in range(0, n, b):
        i1 = min(n, i0+b)
        for j0 in range(i0, n, b):
            j1 = min(n, j0+b)
            yield (i0, i1, j0, j1)

def score_block(args):
    i0, i1, j0, j1, sigs, w = args
    li = [0.0] * (i1 - i0)
    lj = [0.0] * (j1 - j0) if j0 != i0 else None
    processed = 0

    for ii, i in enumerate(range(i0, i1)):
        si = sigs[i]
        if si is None:
            continue
        start = 0 if j0 != i0 else ii + 1

        for jj, j in enumerate(range(j0, j1)):
            if j0 == i0 and jj < start:
                continue
            sj = sigs[j]
            if sj is None:
                continue

            s = si.jaccard(sj)
            processed += 1
            li[ii] += s
            if lj is not None:
                lj[jj] += s

    return i0, i1, li, j0, j1, lj, w, processed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src_dir")
    ap.add_argument("--seed", type=int, default=1, help="MinHash random seed")
    args = ap.parse_args()

    src = Path(args.src_dir)
    if not src.is_dir():
        print("not valiad.", file=sys.stderr); sys.exit(1)

    paths = [str(p) for p in src.rglob("*.js")]
    if not paths:
        print("no .js files.", file=sys.stderr); sys.exit(1)

    lens = [len(tokenize(read_text(p))) for p in paths]
    print(f"average tokens: {sum(lens)/len(lens):.2f}, empty files: {sum(l==0 for l in lens)}")

    n = len(paths)
    sigs = [None]*n
    with Pool(processes=PROCS, maxtasksperchild=1000) as pool:
        it = pool.imap_unordered(build_sig, [(i, p, args.seed) for i, p in enumerate(paths)], chunksize=128)
        for i, m in tqdm(it, total=n, desc="MinHash"):
            sigs[i] = m

    scores = [0.0] * n

    jobs, total_pairs = [], 0
    for (i0, i1, j0, j1) in blocks(n, BLOCK):
        wi, wj = (i1 - i0), (j1 - j0)
        w = wi*(wi-1)//2 if i0 == j0 else wi*wj
        total_pairs += w
        jobs.append((i0, i1, j0, j1, sigs, w))
    print(f"Expected pairs: {total_pairs:,}")

    done_pairs = 0
    with Pool(processes=PROCS, maxtasksperchild=500) as pool, \
         tqdm(total=total_pairs, desc="Pairwise pairs", unit="pairs") as pbar:
        it = pool.imap_unordered(score_block, jobs, chunksize=1)
        for i0, i1, li, j0, j1, lj, w, processed in it:
            for off, v in enumerate(li):
                scores[i0+off] += v
            if lj is not None:
                for off, v in enumerate(lj):
                    scores[j0+off] += v
            done_pairs += processed
            pbar.update(processed)

    print(f"Processed pairs: {done_pairs:,}")


    order = sorted(range(n), key=lambda i: (scores[i], paths[i]))
    sel = [paths[i] for i in order[:K]]
    OUT_PATH.write_text("\n".join(sel), encoding="utf-8")
    print(f"{n} out of {len(sel)} saved -> {OUT_PATH}")

if __name__ == "__main__":
    main()
