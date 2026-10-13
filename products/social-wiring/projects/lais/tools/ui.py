"""UI scan of a pretty-printed chunk: print lines carrying UI text / validation / query keys.
Usage: python3 -I ui.py <pp-file> [maxlen]"""
import re, sys
p = sys.argv[1]
ml = int(sys.argv[2]) if len(sys.argv) > 2 else 240
pat = re.compile(r'(title:|label:|children:"|placeholder:|description:"|message:"|errorMessage|queryKey|\.min\(|\.max\(|\.regex\(|refine\(|href:"/|track\("|"aria-label":|subtitle:|tooltip|emptyState|EmptyState|header:"|accessorKey|columnId|name:"[a-z])')
def dec(t):
    return re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), t)
for i, line in enumerate(open(p, encoding='utf-8', errors='replace'), 1):
    if pat.search(line):
        s = dec(line.strip())
        s = re.sub(r'className:"[^"]*",?', '', s)
        print(f"{i}: {s[:ml]}")
