"""Monta o app: substitui os marcadores {{...}} do template pelas imagens em base64.
Uso: python3 build.py [template.html]   (padrão: template.html)
Gera diario-entre-sessoes.html e check.js (para: node --check check.js)."""
import re, base64, sys, os
aqui = os.path.dirname(os.path.abspath(__file__))
tpl = sys.argv[1] if len(sys.argv) > 1 else 'template.html'
t = open(os.path.join(aqui, tpl), encoding='utf-8').read()
A = lambda n: base64.b64encode(open(os.path.join(aqui, 'assets', n + '.webp'), 'rb').read()).decode()
mapa = {'LOGO':'glogo','G1':'g1','G2':'g2','G3':'g3','G4':'g4','G5':'g5','G6':'g6','G7':'g7',
        'GROD':'grod','W23':'w23','C25':'c25','C28':'c28','ARR':'arranjo','PA':'pa','PB':'pb','PC':'pc'}
t = t.replace('{{TORN}}', open(os.path.join(aqui, 'assets', 'torn.txt'), encoding='utf-8').read())
for k, v in mapa.items():
    if '{{%s}}' % k in t: t = t.replace('{{%s}}' % k, A(v))
faltam = re.findall(r'\{\{\w+\}\}', t)
assert not faltam, faltam
open(os.path.join(aqui, 'diario-entre-sessoes.html'), 'w', encoding='utf-8').write(t)
open(os.path.join(aqui, 'check.js'), 'w', encoding='utf-8').write(re.findall(r'<script>(.*?)</script>', t, re.S)[-1])
print(tpl, '->', len(t) // 1024, 'KB')
