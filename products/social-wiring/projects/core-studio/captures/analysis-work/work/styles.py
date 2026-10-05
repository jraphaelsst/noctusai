import re,sys
s=open(sys.argv[1],encoding='utf-8',errors='replace').read()
out=[]
for i,m in enumerate(re.finditer(r'<style([^>]*)>(.*?)</style>',s,re.S)):
    out.append(f'/* ===== STYLE #{i} @{m.start()} len={len(m.group(2))} */\n'+m.group(2))
open(sys.argv[2],'w').write('\n'.join(out))
