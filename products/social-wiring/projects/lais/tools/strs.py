import sys,re
s=open(sys.argv[1],encoding='utf-8',errors='replace').read()
seen=set()
for m in re.finditer(r'([A-Za-z]{2,24}):"((?:[^"\\]|\\.){3,260})"',s):
    k,t=m.group(1),m.group(2)
    if k in('className','d','fill','stroke','viewBox','src','href','variant','size','side','align','type','id','key','color','value','name','htmlFor','role','autoComplete','inputMode','method'): continue
    if not re.search(r'\\x[a-f0-9]{2}|[A-ZÀ-Ú][a-zà-ú]+ [a-zà-ú]',t): continue
    t2=re.sub(r'\\x([0-9a-f]{2})',lambda x:chr(int(x.group(1),16)),t)
    if t2 in seen: continue
    seen.add(t2); print(f'{k}: {t2}')
