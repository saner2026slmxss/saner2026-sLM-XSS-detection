#!/usr/bin/env python3
import os, sys, subprocess, signal, time
from threading import Timer
import esprima

DEFAULT_EXCLUDE = {"node_modules", ".git", "__pycache__"}

def is_invalid_js(content: str) -> bool:
    result = [None]

    def _parse():
        try:
            esprima.parseScript(content)
            result[0] = False
        except:
            result[0] = True

    t = Timer(1.5, lambda: result.__setitem__(0, True))
    t.start()
    _parse()
    t.cancel()

    return result[0] in (True, None)

def clean(root: str, ext=".js"):
    deleted_count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in DEFAULT_EXCLUDE]
        for fn in filenames:
            if not fn.lower().endswith(ext):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    code = f.read()
            except:
                print(f"[DELETE] {path}")
                os.remove(path)
                deleted_count += 1
                continue

            if is_invalid_js(code):
                print(f"[DELETE] {path}")
                os.remove(path)
                deleted_count += 1
            print(f"Processed: {fn}", end="\r", flush=True)

    print(f"\nTotal deleted: {deleted_count}")

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 js_syntax_cleaner.py <target_dir>")
        sys.exit(1)

    signal.signal(signal.SIGINT, lambda s, f: sys.exit(130))

    target = sys.argv[1]
    if not os.path.isdir(target):
        print("Not directory:", target)
        sys.exit(2)

    clean(target)

if __name__ == "__main__":
    main()
