"""For every this.<verb>( call site, print enclosing method header + body and nearest class/BASE_PATH context.
Static read-only. Usage: python3 -I methods.py <jsdir> > out.txt"""
import os, re, sys

root = sys.argv[1]
call = re.compile(r'this\.(get|post|put|patch|delete|request)\(')

def skip_str_back(s, i):
    return i

def enclosing_open(s, i):
    """Walk back from i to find the unmatched '{' (ignores strings crudely)."""
    depth = 0
    j = i
    while j > 0:
        j -= 1
        c = s[j]
        if c == '}':
            depth += 1
        elif c == '{':
            if depth == 0:
                return j
            depth -= 1
    return 0

def matching_close(s, i):
    depth = 0
    j = i
    n = len(s)
    instr = None
    while j < n:
        c = s[j]
        if instr:
            if c == '\\':
                j += 2; continue
            if c == instr:
                instr = None
        elif c in '"\'`':
            instr = c
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return n

seen = set()
for dp, _, fs in os.walk(root):
    for f in sorted(fs):
        p = os.path.join(dp, f)
        s = open(p, encoding='utf-8', errors='replace').read()
        for m in call.finditer(s):
            o = enclosing_open(s, m.start())
            # header: text between previous '}' or ',' or ';' or '{' and o
            h0 = max(s.rfind('}', 0, o), s.rfind(';', 0, o), s.rfind('{', 0, o))
            hdr = s[h0 + 1:o].strip()
            c = matching_close(s, o)
            body = s[o:c + 1]
            key = (p, o)
            if key in seen:
                continue
            seen.add(key)
            # class context
            k = s.rfind('class ', 0, o)
            bp = s.rfind('BASE_PATH', 0, o)
            ctx = ''
            if k >= 0:
                ctx = s[k:k + 80].split('{')[0]
            bps = ''
            if bp >= 0 and o - bp < 6000:
                bps = s[bp:bp + 60]
            print(f"### {os.path.relpath(p, root)} @{o} | {ctx} | {bps}")
            print(f"{hdr}{body[:700]}")
            print()
