"""Large-scale matching assessment: 400 imóveis + 80 permutas.
Builds on the original 100+30 seed by generating realistic variations.
Usage: python -m tests.test_mock_matching_large
"""
import sys, os, random, copy
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_mock_matching_local import (
    imv, pm, au, OA, OB, OC, nid,
    I as I_BASE, P as P_BASE, PA as PA_BASE,
)

random.seed(42)

# ── City/region pools ──
SP_BAIRROS_ZS = [
    ("Moema", "Zona Sul"), ("Vila Mariana", "Zona Sul"), ("Saúde", "Zona Sul"),
    ("Brooklin", "Zona Sul"), ("Jabaquara", "Zona Sul"), ("Campo Belo", "Zona Sul"),
    ("Santo Amaro", "Zona Sul"), ("Chácara Klabin", "Zona Sul"), ("Ipiranga", "Zona Sul"),
    ("Vila Clementino", "Zona Sul"), ("Itaim Bibi", "Zona Sul"), ("Cursino", "Zona Sul"),
    ("Granja Julieta", "Zona Sul"), ("Vila Mascote", "Zona Sul"), ("Sacomã", "Zona Sul"),
]
SP_BAIRROS_ZO = [
    ("Pinheiros", "Zona Oeste"), ("Vila Madalena", "Zona Oeste"), ("Perdizes", "Zona Oeste"),
    ("Alto de Pinheiros", "Zona Oeste"), ("Lapa", "Zona Oeste"), ("Pompeia", "Zona Oeste"),
    ("Barra Funda", "Zona Oeste"), ("Sumaré", "Zona Oeste"), ("Vila Leopoldina", "Zona Oeste"),
    ("Butantã", "Zona Oeste"), ("Vila Romana", "Zona Oeste"), ("Água Branca", "Zona Oeste"),
]
SP_BAIRROS_ZN = [
    ("Santana", "Zona Norte"), ("Tucuruvi", "Zona Norte"), ("Mandaqui", "Zona Norte"),
    ("Vila Maria", "Zona Norte"), ("Tremembé", "Zona Norte"), ("Casa Verde", "Zona Norte"),
    ("Freguesia do Ó", "Zona Norte"), ("Vila Guilherme", "Zona Norte"),
]
SP_BAIRROS_ZL = [
    ("Tatuapé", "Zona Leste"), ("Anália Franco", "Zona Leste"), ("Penha", "Zona Leste"),
    ("Mooca", "Zona Leste"), ("Vila Formosa", "Zona Leste"), ("Belém", "Zona Leste"),
    ("Vila Prudente", "Zona Leste"), ("Carrão", "Zona Leste"),
]
ABC_CIDADES = [
    ("Santo André", "Centro"), ("São Bernardo do Campo", "Centro"),
    ("São Caetano do Sul", "Santa Paula"), ("Diadema", "Centro"),
    ("Mauá", "Centro"), ("Ribeirão Pires", "Centro"),
    ("Santo André", "Jardim"), ("São Bernardo do Campo", "Rudge Ramos"),
    ("São Caetano do Sul", "Barcelona"), ("São Bernardo do Campo", "Baeta Neves"),
]
CPS_CIDADES = [
    ("Campinas", "Cambuí"), ("Campinas", "Taquaral"), ("Campinas", "Barão Geraldo"),
    ("Campinas", "Sousas"), ("Campinas", "Nova Campinas"), ("Campinas", "Swift"),
    ("Valinhos", "Centro"), ("Indaiatuba", "Centro"), ("Sumaré", "Centro"),
    ("Vinhedo", "Centro"),
]
LIT_CIDADES = [
    ("Santos", "Gonzaga"), ("Santos", "Ponta da Praia"), ("Guarujá", "Pitangueiras"),
    ("Santos", "Boqueirão"), ("Praia Grande", "Boqueirão"), ("Santos", "Embaré"),
    ("São Vicente", "Itararé"), ("Guarujá", "Enseada"),
]
CWB_CIDADES = [
    ("Curitiba", "Batel"), ("Curitiba", "Água Verde"), ("Curitiba", "Centro Cívico"),
    ("Curitiba", "Santa Felicidade"), ("Curitiba", "Portão"), ("Curitiba", "Ecoville"),
]
INT_CIDADES = [
    ("Sorocaba", "Campolim"), ("Jundiaí", "Centro"), ("Ribeirão Preto", "Jardim Botânico"),
    ("São José dos Campos", "Jardim Aquarius"), ("Piracicaba", "Centro"),
    ("São José dos Campos", "Vila Adyana"), ("Bauru", "Centro"), ("Marília", "Centro"),
]

ALL_SP = [("São Paulo", b, "SP", z) for b, z in SP_BAIRROS_ZS + SP_BAIRROS_ZO + SP_BAIRROS_ZN + SP_BAIRROS_ZL]
for c, b in ABC_CIDADES:
    ALL_SP.append((c, b, "SP", None))
for c, b in CPS_CIDADES:
    ALL_SP.append((c, b, "SP", None))
for c, b in LIT_CIDADES:
    ALL_SP.append((c, b, "SP", None))
for c, b in INT_CIDADES:
    ALL_SP.append((c, b, "SP", None))

ALL_LOCATIONS = ALL_SP + [(c, b, "PR", None) for c, b in CWB_CIDADES]

# Out-of-state for LOW permutas
OUT_OF_STATE = [
    ("Rio de Janeiro", "Copacabana", "RJ"), ("Belo Horizonte", "Savassi", "MG"),
    ("Florianópolis", "Centro", "SC"), ("Porto Alegre", "Moinhos de Vento", "RS"),
    ("Recife", "Boa Viagem", "PE"), ("Salvador", "Barra", "BA"),
    ("Brasília", "Asa Sul", "DF"), ("Goiânia", "Setor Bueno", "GO"),
    ("Fortaleza", "Meireles", "CE"), ("Cuiabá", "Centro", "MT"),
]

TIPOS_IMOVEL = ["apartamento", "apartamento", "apartamento", "casa", "cobertura", "studio"]
OWNERS = [OA, OB, OC]
MARCAS_AUTO = [
    ("BMW", "X3", "suv"), ("Mercedes-Benz", "C200", "sedan"), ("Porsche", "Macan", "suv"),
    ("Porsche", "Cayenne", "suv"), ("Toyota", "Corolla Cross", "hatch"),
    ("Audi", "Q5", "suv"), ("Volvo", "XC60", "suv"), ("Land Rover", "Evoque", "suv"),
    ("BMW", "320i", "sedan"), ("Mercedes-Benz", "GLC", "suv"),
]


def _rand_valor(base_min, base_max):
    return round(random.randint(base_min, base_max) / 10000) * 10000


def _rand_fotos():
    n = random.choice([1, 2, 3, 3, 4, 5])
    return [f"f{i}" for i in range(1, n + 1)]


def _generate_imovel(idx, loc=None):
    """Generate a realistic imóvel with random but plausible attributes."""
    if loc is None:
        cidade, bairro, estado, zona = random.choice(ALL_LOCATIONS)
    else:
        cidade, bairro, estado, zona = loc

    tipo = random.choice(TIPOS_IMOVEL)
    owner = random.choice([OA, OC])  # OB is reserved for permutas

    if tipo == "studio":
        valor = _rand_valor(180000, 450000)
        q, su, vg = 1, 0, 1
        ap = random.randint(25, 42)
    elif tipo == "apartamento":
        valor = _rand_valor(250000, 1200000)
        q = random.choice([1, 2, 2, 3, 3, 4])
        su = min(q - 1, random.randint(0, 2))
        vg = random.choice([1, 1, 2, 2, 3])
        ap = random.randint(40, 140)
    elif tipo == "cobertura":
        valor = _rand_valor(500000, 1500000)
        q = random.choice([3, 3, 4])
        su = random.choice([1, 2, 3])
        vg = random.choice([2, 3, 4])
        ap = random.randint(120, 250)
    else:  # casa
        valor = _rand_valor(400000, 2000000)
        q = random.choice([3, 3, 4, 4, 5])
        su = random.choice([1, 2, 3])
        vg = random.choice([2, 3, 4])
        ap = random.randint(130, 350)

    at = ap + random.randint(5, 30)
    an = random.randint(1, 25) if tipo != "casa" else None

    # Interesses — what this imóvel owner wants in return
    interesses = []
    # Most want imóvel back
    want_tipo = random.choice(TIPOS_IMOVEL[:4])  # apt/casa/cob
    val_min = int(valor * random.uniform(0.5, 0.8))
    val_max = int(valor * random.uniform(1.2, 1.8))
    interesses.append({
        "tipo": "imovel", "tipo_imovel": want_tipo,
        "cidade": cidade,  # usually same city
        "valor_min": val_min, "valor_max": val_max,
    })
    # Some also want auto
    if random.random() < 0.08 and valor > 800000:
        marca_info = random.choice(MARCAS_AUTO)
        interesses.append({
            "tipo": "automovel", "marca": marca_info[0],
            "valor_min": 100000, "valor_max": 500000,
        })

    ob = f"GEN-{idx:03d}"
    return imv(
        owner, valor, tipo, cidade, estado, bairro, zona,
        q, su, random.randint(1, 4), vg, ap, at, an,
        f"{tipo.title()} {bairro}", f"D-{idx}", _rand_fotos(),
        ["M"] if random.random() < 0.5 else None,
        ob, interesses,
    )


def _generate_permuta_imovel(idx, quality="MED", loc=None):
    """Generate a permuta_imovel with given quality level."""
    if loc is None:
        if quality == "HIGH":
            cidade, bairro, estado, zona = random.choice(ALL_LOCATIONS)
        elif quality == "LOW":
            cidade, bairro, estado = random.choice(OUT_OF_STATE)
            zona = None
        else:
            cidade, bairro, estado, zona = random.choice(ALL_LOCATIONS)
    else:
        cidade, bairro, estado, zona = loc

    tipo = random.choice(TIPOS_IMOVEL[:4])
    valor = _rand_valor(200000, 1200000)

    # Faixa
    fmi = int(valor * random.uniform(0.7, 0.9))
    fma = int(valor * random.uniform(1.1, 1.4))

    qm = random.choice([0, 1, 2, 2, 3])
    vm = random.choice([0, 1, 1, 2])
    mm = random.randint(30, 80) if random.random() < 0.6 else None
    mx = mm + random.randint(30, 100) if mm else None
    ac = random.random() < 0.5

    # Regiao preferida
    rg = [cidade] if quality != "LOW" else [cidade]

    # What this permuta wants in return (interesses)
    want_tipo = random.choice(TIPOS_IMOVEL[:4])
    int_val_min = int(valor * random.uniform(0.6, 0.9))
    int_val_max = int(valor * random.uniform(1.1, 1.5))
    interesses = [{
        "tipo": "imovel", "tipo_imovel": want_tipo,
        "cidade": cidade,
        "valor_min": int_val_min, "valor_max": int_val_max,
    }]

    ob = f"PERM-{quality}-G{idx:02d}"
    return pm(
        OB, valor, tipo, cidade, estado, bairro, zona,
        fmi, fma, qm, vm, mm, mx, ac, rg, ob, interesses,
    )


def _generate_permuta_auto(idx):
    """Generate a permuta_automovel."""
    marca, modelo, tv = random.choice(MARCAS_AUTO)
    valor = _rand_valor(80000, 600000)
    # Auto permutas are in SP or Campinas
    cidade, estado = random.choice([("São Paulo", "SP"), ("Campinas", "SP"), ("Curitiba", "PR")])

    # What this auto permuta wants in return (always an imóvel)
    want_tipo = random.choice(["apartamento", "casa"])
    interesses = [{
        "tipo": "imovel", "tipo_imovel": want_tipo,
        "cidade": cidade,
        "valor_min": int(valor * 1.5), "valor_max": int(valor * 4.0),
    }]

    ob = f"PERM-AUTO-G{idx:02d}"
    return au(OB, valor, cidade, estado, marca, modelo, tv, ob, interesses)


# ── Configurable dataset size ──
TARGET_IMOVEIS = int(os.environ.get("MATCH_IMOVEIS", "400"))
TARGET_PERMUTAS = int(os.environ.get("MATCH_PERMUTAS", "80"))

# Permuta split: ~70% imovel permutas, ~15% auto, ~15% LOW (out-of-state)
_extra_imoveis = TARGET_IMOVEIS - len(I_BASE)  # beyond the base 100
_extra_permutas = TARGET_PERMUTAS - len(P_BASE) - len(PA_BASE)  # beyond the base 30

_extra_pm_high = max(0, int(_extra_permutas * 0.30))
_extra_pm_med = max(0, int(_extra_permutas * 0.25))
_extra_pm_low = max(0, int(_extra_permutas * 0.20))
_extra_pa = max(0, _extra_permutas - _extra_pm_high - _extra_pm_med - _extra_pm_low)

# ── Location pools for distribution ──
_SP_CITY_LOCS = ALL_SP[:len(SP_BAIRROS_ZS + SP_BAIRROS_ZO + SP_BAIRROS_ZN + SP_BAIRROS_ZL)]
_ABC_LOCS = [(c, b, "SP", None) for c, b in ABC_CIDADES]
_CPS_LOCS = [(c, b, "SP", None) for c, b in CPS_CIDADES]
_LIT_LOCS = [(c, b, "SP", None) for c, b in LIT_CIDADES]
_CWB_LOCS = [(c, b, "PR", None) for c, b in CWB_CIDADES]
_INT_LOCS = [(c, b, "SP", None) for c, b in INT_CIDADES]

def _build_imovel_distributions(n):
    """Distribute n extra imóveis: ~40% SP, ~15% ABC, ~15% CPS, ~10% LIT, ~10% CWB, ~10% INT."""
    return [
        (int(n * 0.40), _SP_CITY_LOCS),
        (int(n * 0.15), _ABC_LOCS),
        (int(n * 0.15), _CPS_LOCS),
        (int(n * 0.10), _LIT_LOCS),
        (int(n * 0.10), _CWB_LOCS),
        (n - int(n * 0.40) - int(n * 0.15) - int(n * 0.15) - int(n * 0.10) - int(n * 0.10), _INT_LOCS),
    ]

# ── Build imóveis ──
I = list(I_BASE)
gen_idx = 0
for count, locs in _build_imovel_distributions(_extra_imoveis):
    for _ in range(count):
        gen_idx += 1
        loc = random.choice(locs)
        I.append(_generate_imovel(gen_idx, loc))

assert len(I) == TARGET_IMOVEIS, f"Expected {TARGET_IMOVEIS} imóveis, got {len(I)}"

# ── Build permutas ──
P = list(P_BASE)
PA = list(PA_BASE)

for i in range(_extra_pm_high):
    P.append(_generate_permuta_imovel(i + 1, "HIGH"))
for i in range(_extra_pm_med):
    P.append(_generate_permuta_imovel(i + 1, "MED"))
for i in range(_extra_pm_low):
    P.append(_generate_permuta_imovel(i + 1, "LOW"))
for i in range(_extra_pa):
    PA.append(_generate_permuta_auto(i + 1))

ALL = P + PA

assert len(ALL) == TARGET_PERMUTAS, f"Expected {TARGET_PERMUTAS} permutas, got {len(ALL)}"


if __name__ == "__main__":
    from app.services.matching import gerar_matches_para_imovel

    print("=" * 80)
    print(f"LARGE-SCALE MATCHING ASSESSMENT — {len(I)} imóveis × {len(ALL)} permutas")
    print("=" * 80)

    all_m = []
    for im in I:
        all_m.extend(gerar_matches_para_imovel(im, ALL))

    possible = len(I) * len(ALL)
    print(f"\nTotal matches: {len(all_m)}")
    print(f"Possible pairs: {possible} | Match rate: {len(all_m)/possible*100:.1f}%")

    if all_m:
        scores = [m["score"] for m in all_m]
        print(f"Score range: {min(scores):.0f}–{max(scores):.0f} | Avg: {sum(scores)/len(scores):.1f}")

        gr = {"HIGH": 0, "MED": 0, "LOW": 0, "AUTO": 0}
        for m in all_m:
            ob = next((p["observacoes"] for p in ALL if p["id"] == m["ativo_destino_id"]), "")
            if "HIGH" in ob: gr["HIGH"] += 1
            elif "MED" in ob: gr["MED"] += 1
            elif "LOW" in ob: gr["LOW"] += 1
            elif "AUTO" in ob: gr["AUTO"] += 1
        print(f"\nBy group: HIGH={gr['HIGH']} MED={gr['MED']} LOW={gr['LOW']} AUTO={gr['AUTO']}")
