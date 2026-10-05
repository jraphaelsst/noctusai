import sys,re
from html.parser import HTMLParser
KEEP=('id','class','name','type','value','placeholder','href','action','method','for','title','data-','x-','wire:','@',':','aria-label','selected','checked','disabled','required','accept','maxlength','min','max','step','multiple','role','src','style')
VOID={'br','hr','img','input','meta','link','source','area','base','col','embed','param','track','wbr'}
class P(HTMLParser):
    def __init__(s):
        super().__init__(convert_charrefs=True); s.d=0; s.out=[]; s.skip=0
    def handle_starttag(s,t,a):
        if s.skip:
            if t in('svg','script','style'): s.skip+=1
            return
        if t in('svg','script','style'):
            if t=='script':
                ad=dict(a); s.out.append('  '*s.d+f'<script {ad.get("src","") or ad.get("type","") or ad.get("id","inline")}>')
            s.skip=1
            return
        attrs=[]
        for k,v in a:
            if any(k==x or k.startswith(x) for x in KEEP):
                v=(v or '')
                if k in('class','style'): v=v[:90]
                if len(v)>400: v=v[:400]+'…'
                attrs.append(f'{k}="{v}"' if v else k)
        s.out.append('  '*s.d+'<'+t+(' '+' '.join(attrs) if attrs else '')+'>')
        if t not in VOID: s.d+=1
    def handle_endtag(s,t):
        if s.skip:
            if t in('svg','script','style'): s.skip-=1
            return
        if t in VOID: return
        s.d=max(0,s.d-1)
    def handle_data(s,d):
        if s.skip: return
        d=re.sub(r'\s+',' ',d).strip()
        if d: s.out.append('  '*s.d+'"'+d[:400]+'"')
p=P(); p.feed(open(sys.argv[1],encoding='utf-8',errors='replace').read())
open(sys.argv[2],'w').write('\n'.join(p.out))
print(sys.argv[2],len(p.out))
