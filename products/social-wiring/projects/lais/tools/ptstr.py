import re,sys
s=open(sys.argv[1],encoding='utf-8',errors='replace').read()
lo=int(sys.argv[2]) if len(sys.argv)>2 else 0; hi=int(sys.argv[3]) if len(sys.argv)>3 else len(s)
seen=set()
for m in re.finditer(r'"((?:[^"\\]|\\.){2,400})"',s[lo:hi]):
    t=m.group(1)
    if re.search(r'(^| )(flex|text-|bg-|px-|py-|mt-|mb-|w-|h-|rounded|border|items-|gap-|font-|size-|grid|absolute|relative|shrink|min-|max-)',t): continue
    if not (re.search(r'\\x[c-f][0-9a-f]',t) or re.search(r'^[A-ZÁ-Ú][a-zà-ú]+( |$)',t) or re.search(r' [a-zà-ú]{2,} ',t)): continue
    if t in seen: continue
    seen.add(t)
    try: t2=t.encode('latin-1','backslashreplace').decode('unicode_escape')
    except Exception: t2=t
    print(lo+m.start(), t2[:200])
