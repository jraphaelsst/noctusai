"""Extract HTTP call sites from minified chunks (static read-only).
Usage: python3 -I calls.py <jsdir> <regex> [before] [after]"""
import os, re, sys
root = sys.argv[1]
pat = re.compile(sys.argv[2])
b = int(sys.argv[3]) if len(sys.argv) > 3 else 120
a = int(sys.argv[4]) if len(sys.argv) > 4 else 200
for dp, _, fs in os.walk(root):
    for f in sorted(fs):
        p = os.path.join(dp, f)
        s = open(p, encoding='utf-8', errors='replace').read()
        for m in pat.finditer(s):
            w = s[max(0, m.start() - b): m.end() + a].replace('\n', ' ')
            print(f"{os.path.relpath(p, root)}@{m.start()}: {w}")
