"""Static taxonomies for the Geração pages (Meu Perfil, Biblioteca, Headlines, Treinamentos).

Migration ``*_cs_geracao.sql`` seeds ``cs_nichos``, ``cs_profissoes``,
``cs_formatos_video`` and ``cs_treinamentos`` from this module (the SQL is generated
by :func:`seed_sql`; a test asserts the migration file carries exactly that text),
and the services validate ids against the same constants -- so each list is written
ONCE (same idiom as ``cerebro_templates.py`` / ``pesquisa_variables.py``).

Origin (``projects/core-studio/specs/geracao-contract.md`` section 2.2):

* nichos / profissoes: ids and labels verbatim from ``biblioteca-roteiros-analysis.md``
  section 1.4 (CoreStudio's ids; the gaps are deliberate, they are not renumbered);
* formatos: names from the same section; ``definicao`` is the *Definition* column of the
  15-format rubric in ``docs/platform-study.md``;
* treinamentos: the 5 lessons, titles and descriptions verbatim from
  ``biblioteca-roteiros-analysis.md`` section 4 (``video_url`` stays NULL until a
  platform admin sets it; re-seeding never overwrites it);
* gatilhos / tons / criatividade are Python-only (stored as text with a CHECK where
  persisted). The gatilho FORMULAS stay in ``prompts/methodology.METODO_TRIGGERS``.
"""
from __future__ import annotations

# (id, nome) -- 28 rows, CoreStudio ids.
NICHOS: tuple[tuple[int, str], ...] = (
    (1, 'Saúde e Bem-Estar'),
    (2, 'Relacionamentos'),
    (3, 'Finanças'),
    (4, 'Educação'),
    (5, 'Empreendedorismo/Business'),
    (6, 'Espiritualidade'),
    (7, 'Beleza & Estética'),
    (8, 'Moda & Estilo'),
    (9, 'Desenvolvimento Pessoal'),
    (13, 'Emagrecimento e Dieta'),
    (14, 'Saúde Mental'),
    (17, 'Tech & IA'),
    (18, 'Cripto'),
    (19, 'Marketing Digital'),
    (20, 'Direito'),
    (21, 'Comunicação & Liderança'),
    (22, 'Criação de Filhos'),
    (23, 'Vendas'),
    (24, 'Trends do Momento'),
    (25, 'Casa & Decoração'),
    (26, 'Imobiliário'),
    (27, 'Culinária'),
    (28, 'Emagrecimento'),
    (29, 'Imigração'),
    (30, 'Turismo & Viagem'),
    (31, 'Pets & Animais'),
    (32, 'Tributação Fiscal'),
    (33, 'Construção Civil'),
)

# (id, nome) -- 102 rows, CoreStudio ids.
PROFISSOES: tuple[tuple[int, str], ...] = (
    (25, 'Acupunturista'),
    (70, 'Advogado Administrativo'),
    (72, 'Advogado Ambiental'),
    (64, 'Advogado Civil'),
    (74, 'Advogado Constitucional'),
    (75, 'Advogado de Consumidor'),
    (67, 'Advogado de Família'),
    (76, 'Advogado Digital'),
    (68, 'Advogado Empresarial'),
    (71, 'Advogado Imobiliário'),
    (73, 'Advogado Internacional'),
    (65, 'Advogado Penal'),
    (77, 'Advogado Previdenciário'),
    (66, 'Advogado Trabalhista'),
    (69, 'Advogado Tributário'),
    (85, 'Agente de Turismo'),
    (20, 'Arquiteto(a)'),
    (102, 'Auditor Fiscal'),
    (3, 'Autor(a)'),
    (95, 'Breathwork'),
    (18, 'Cabeleireiro(a)'),
    (56, 'Chef de Cozinha'),
    (105, 'Cirurgião Plástico'),
    (27, 'Coach'),
    (57, 'Confeiteiro'),
    (54, 'Consultor de Imagem'),
    (49, 'Contador(a)'),
    (62, 'Copywriter'),
    (82, 'Corretor de Imóveis'),
    (90, 'Corretor de seguro de vida'),
    (21, 'Dentista'),
    (79, 'Designer de Interiores'),
    (100, 'Designer de joias'),
    (52, 'Designer de Sobrancelhas'),
    (60, 'Designer Gráfico'),
    (28, 'Economista'),
    (23, 'Empreendedor(a)'),
    (92, 'Enfermagem'),
    (80, 'Engenheiro'),
    (15, 'Esteticista'),
    (32, 'Estrategista de Marca'),
    (2, 'Farmacêutico(a)'),
    (14, 'Fisioterapeuta'),
    (47, 'Fisioterapeuta Pélvico'),
    (106, 'Fonoaudiólogo'),
    (55, 'Fotógrafo'),
    (61, 'Gestor de Tráfego/Media Buyer'),
    (22, 'Gestor(a)'),
    (83, 'Higienista Ocupacional'),
    (30, 'Influenciador(a)'),
    (31, 'Investidor(a)'),
    (99, 'Joalheira'),
    (84, 'Jornalista'),
    (78, 'Juiz'),
    (51, 'Líder Religioso'),
    (53, 'Maquiador(a)'),
    (26, 'Marketeiro(a)'),
    (98, 'Medicina Regenerativa'),
    (37, 'Médico Cardiologista'),
    (12, 'Médico Cirurgião'),
    (33, 'Médico Dermatologista'),
    (38, 'Médico Endocrinologista'),
    (101, 'Médico geral'),
    (89, 'Médico Geriatra'),
    (36, 'Médico Ginecologista'),
    (43, 'Médico Integrativo'),
    (39, 'Médico Neurologista'),
    (87, 'Médico Nutrólogo'),
    (104, 'Médico Obstetra'),
    (40, 'Médico Oftalmologista'),
    (34, 'Médico Ortopedista'),
    (91, 'Medico Otorrinolaringologia'),
    (35, 'Médico Pediatra'),
    (8, 'Médico Psiquiatra'),
    (93, 'Medico Radiologia'),
    (103, 'Médico ultrassonografista'),
    (41, 'Médico Urologista'),
    (42, 'Médico Veterinário'),
    (50, 'Mentor(a)'),
    (24, 'Moda'),
    (97, 'Musculação'),
    (4, 'Neurocientista'),
    (16, 'Nutricionista'),
    (81, 'Paisagista'),
    (5, 'Pastor(a)'),
    (48, 'Personal Trainer'),
    (94, 'Professor de Yoga'),
    (29, 'Professor(a)'),
    (63, 'Programador(a)'),
    (46, 'Psicanalista'),
    (44, 'Psicólogo Infantil'),
    (7, 'Psicólogo(a)'),
    (45, 'Psicoterapeuta'),
    (86, 'Quiropraxista'),
    (59, 'Social Media'),
    (58, 'Sommelier'),
    (6, 'Teólogo(a)'),
    (9, 'Terapeuta'),
    (10, 'Terapeuta Holístico'),
    (96, 'Terapeuta Somatico'),
    (13, 'Vendedor(a)'),
    (19, 'Visagista'),
)

# (id, nome, definicao) -- 15 rows.
FORMATOS_VIDEO: tuple[tuple[int, str, str], ...] = (
    (1, 'Lista de Valor Prático', 'Dicas/passos/recomendações aplicáveis imediatamente.'),
    (2, 'Lista de Pontos de Identificação', 'Situações em que o público se reconhece.'),
    (3, 'Lista de Crenças', 'Valores ou princípios afirmados com clareza.'),
    (4, 'Mistério', 'Informação-chave retida até o final.'),
    (5, 'Comparação', 'Contrasta duas opções/ideias.'),
    (6, 'Tutorial', 'Passo a passo de COMO fazer.'),
    (7, 'Análise do Mundo e Novas Tendências', 'Mudanças sociais/leis/mercado e impactos.'),
    (8, 'Histórias Pessoais', 'Relato em 1ª pessoa com vulnerabilidade.'),
    (9, 'Histórias de Terceiros', 'Caso de cliente/paciente/figura pública.'),
    (10, 'Fatos Curiosos', 'Dados/estatísticas surpreendentes.'),
    (11, 'Metáforas e Analogias', 'Explica por comparação familiar.'),
    (12, 'Assunto do Momento', 'Trending (notícia, meme, evento).'),
    (13, 'Defesa de Crença Forte', 'Opinião polarizadora, linguagem absoluta.'),
    (14, 'Palavras de Motivação', 'Encorajamento curto.'),
    (15, 'Websérie', 'Conteúdo seriado.'),
)

# (ordem, titulo, descricao) -- 5 rows.
TREINAMENTOS: tuple[tuple[int, str, str], ...] = (
    (1, 'Como preencher a Bio', 'Como preencher sua Bio do jeito certo para a IA entender seu contexto.'),
    (2, 'Como aprovar itens da Pesquisa (automático e manual)', 'Aprenda a aprovar itens gerados na Pesquisa, tanto no modo automático quanto no manual.'),
    (3, 'Como gerar roteiros Headlines Favoritas', 'Gere roteiros a partir das suas Headlines Favoritas com poucos cliques.'),
    (4, 'Como gerar roteiros Headlines Biblioteca de Virais', 'Use a Biblioteca de Virais para gerar roteiros prontos para produção.'),
    (5, 'Como gerar roteiros com Headlines Próprias', 'Crie seus próprios ganchos/headlines e gere roteiros a partir deles.'),
)

# The 7 Metodo Audience attention triggers: (slug, nome). Formulas: METODO_TRIGGERS.
GATILHOS: tuple[tuple[str, str], ...] = (
    ("recompensa", "Recompensa"),
    ("misterio", "Mistério"),
    ("reconhecimento", "Reconhecimento"),
    ("popularidade", "Popularidade"),
    ("crenca", "Crença"),
    ("autoridade", "Autoridade"),
    ("disrupcao", "Disrupção"),
)

# Tom de Comunicacao (CoreStudio ids 10-15, mechanisms.md section 5.5): (slug, nome).
TONS: tuple[tuple[str, str], ...] = (
    ("chocante-disruptiva", "Chocante e Disruptiva"),
    ("futuro-possibilidades", "Futuro e Possibilidades"),
    ("curiosidade-misterio", "Curiosidade e Mistério"),
    ("cultura-sociedade", "Cultura e Sociedade"),
    ("critica-denuncia", "Crítica e Denúncia"),
    ("reflexao-profundidade", "Reflexão e Profundidade"),
)

CRIATIVIDADE: tuple[str, ...] = ("essencial", "equilibrado", "explorador")

GATILHO_SLUGS = frozenset(s for s, _ in GATILHOS)
TOM_SLUGS = frozenset(s for s, _ in TONS)
NICHO_IDS = frozenset(i for i, _ in NICHOS)
PROFISSAO_IDS = frozenset(i for i, _ in PROFISSOES)
FORMATO_IDS = frozenset(i for i, _, _ in FORMATOS_VIDEO)


def _q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def seed_sql() -> str:
    """The four ``INSERT ... ON CONFLICT`` statements the geracao migration carries verbatim."""
    nichos = ",\n".join(
        f"    ({i}, {_q(nome)}, {n})" for n, (i, nome) in enumerate(NICHOS, start=1)
    )
    profs = ",\n".join(f"    ({i}, {_q(nome)})" for i, nome in sorted(PROFISSOES, key=lambda r: r[1].lower()))
    formatos = ",\n".join(f"    ({i}, {_q(nome)}, {_q(defn)})" for i, nome, defn in FORMATOS_VIDEO)
    treinos = ",\n".join(f"    ({o}, {_q(t)}, {_q(d)})" for o, t, d in TREINAMENTOS)
    return (
        "INSERT INTO social_wiring.cs_nichos (id, nome, sort_order)\n"
        "VALUES\n" + nichos + "\n"
        "ON CONFLICT (id) DO UPDATE SET nome = EXCLUDED.nome, sort_order = EXCLUDED.sort_order;\n"
        "\n"
        "INSERT INTO social_wiring.cs_profissoes (id, nome)\n"
        "VALUES\n" + profs + "\n"
        "ON CONFLICT (id) DO UPDATE SET nome = EXCLUDED.nome;\n"
        "\n"
        "INSERT INTO social_wiring.cs_formatos_video (id, nome, definicao)\n"
        "VALUES\n" + formatos + "\n"
        "ON CONFLICT (id) DO UPDATE SET nome = EXCLUDED.nome, definicao = EXCLUDED.definicao;\n"
        "\n"
        "-- video_url / ativo are deliberately NOT updated: a platform admin owns them.\n"
        "INSERT INTO social_wiring.cs_treinamentos (ordem, titulo, descricao)\n"
        "VALUES\n" + treinos + "\n"
        "ON CONFLICT (ordem) DO UPDATE SET titulo = EXCLUDED.titulo, descricao = EXCLUDED.descricao;\n"
    )


__all__ = [
    "CRIATIVIDADE",
    "FORMATOS_VIDEO",
    "FORMATO_IDS",
    "GATILHOS",
    "GATILHO_SLUGS",
    "NICHOS",
    "NICHO_IDS",
    "PROFISSAO_IDS",
    "PROFISSOES",
    "TONS",
    "TOM_SLUGS",
    "TREINAMENTOS",
    "seed_sql",
]
