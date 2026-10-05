import re,sys
s=open(sys.argv[1],encoding='utf-8',errors='replace').read()
out=[]
for i,m in enumerate(re.finditer(r'<script([^>]*)>(.*?)</script>',s,re.S)):
    if len(m.group(2).strip())>int(sys.argv[3] if len(sys.argv)>3 else 0):
        out.append(f'/* ===== SCRIPT #{i} @{m.start()} attrs={m.group(1).strip()[:100]} len={len(m.group(2))} */\n'+m.group(2))
open(sys.argv[2],'w').write('\n'.join(out))
