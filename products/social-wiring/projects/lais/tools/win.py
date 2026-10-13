import sys
f=sys.argv[1]; s=open(f,encoding='utf-8',errors='replace').read()
for spec in sys.argv[2:]:
    a,b=spec.split(':'); a=int(a); b=int(b)
    print(f"---- {a}..{b}"); print(s[a:b])
