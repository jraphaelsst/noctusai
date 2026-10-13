"""Crude JS pretty-printer for reading minified bundles (static, read-only).
Usage: python3 -I pp.py <in.js> <out.js>
Breaks lines after ; { } outside strings/template literals; indents by brace depth."""
import sys

def pp(src):
    out = []
    depth = 0
    i = 0
    n = len(src)
    line = []
    tmpl_stack = []  # depth markers for ${ inside template
    def flush():
        s = ''.join(line).strip()
        if s:
            out.append('  ' * max(depth, 0) + s)
        line.clear()
    while i < n:
        c = src[i]
        if c in '"\'':
            j = i + 1
            while j < n and src[j] != c:
                if src[j] == '\\':
                    j += 1
                elif src[j] == '\n':
                    break
                j += 1
            line.append(src[i:j + 1]); i = j + 1; continue
        if c == '`':
            # template literal; copy raw until matching backtick, handling ${ } nesting simply
            j = i + 1; level = 0
            while j < n:
                ch = src[j]
                if ch == '\\': j += 2; continue
                if level == 0 and ch == '`': break
                if ch == '$' and j + 1 < n and src[j + 1] == '{': level += 1; j += 2; continue
                if level > 0 and ch == '{': level += 1
                elif level > 0 and ch == '}': level -= 1
                j += 1
            line.append(src[i:j + 1]); i = j + 1; continue
        if c == '{':
            line.append(c); flush(); depth += 1; i += 1; continue
        if c == '}':
            flush(); depth -= 1; line.append(c)
            # keep trailing ; , ) on same line
            i += 1
            while i < n and src[i] in ';,)':
                line.append(src[i]); i += 1
            flush(); continue
        if c == ';':
            line.append(c); flush(); i += 1; continue
        if c == '\n':
            flush(); i += 1; continue
        line.append(c); i += 1
    flush()
    return '\n'.join(out)

if __name__ == '__main__':
    src = open(sys.argv[1], encoding='utf-8', errors='replace').read()
    open(sys.argv[2], 'w', encoding='utf-8').write(pp(src))
