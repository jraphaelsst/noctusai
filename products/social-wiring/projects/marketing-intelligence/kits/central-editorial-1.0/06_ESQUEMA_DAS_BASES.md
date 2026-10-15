# Como preencher as bases CSV de cada perfil

Os CSVs foram preparados para abrir no Excel, Numbers ou Google Sheets (UTF-8). Eles são independentes e contêm apenas o cabeçalho, sem inventar planejamentos ou resultados. Trabalhar com cinco arquivos por perfil:

- **CALENDARIO.csv**: cada linha acompanha uma publicação da pauta até a análise. Informe `id_conteudo`, datas, plataforma, objetivo, status e, após publicação, URL e `id_simec`.
- **PAUTAS.csv**: pesquisa e banco de ideias com fonte, hipótese editorial, prioridade e decisão.
- **COMUNIDADE.csv**: temas agregados de comentários e respostas, sem nomes ou informações sensíveis de seguidoras.
- **CAMPANHAS.csv**: orçamento planejado e gasto realizado. O ChatGPT pode calcular desvios ao receber a base; o CSV não executa fórmulas sozinho.
- **DECISOES.csv**: transfira aqui os testes e resultados validados pelo SIMEC, sem copiar o painel bruto nem misturar plataformas.

**Estados sugeridos do calendário**: Ideia; Selecionada; Roteiro; Aprovação; Gravação; Edição; Programado; Publicado; Análise SIMEC; Aprendizado registrado.

**Códigos sugeridos**: MON-2026-001, GIL-2026-001, ISA-2026-001. Use apenas como convenção interna e não suponha haver publicações reais com esses códigos.

**Integração operacional**: ao terminar um roteiro, passe o status para Aprovação; após a postagem, registre URL e data real; depois de 7 a 10 dias, colete indicadores no SIMEC e registre aqui o ID da análise; na próxima reunião editorial, use DECISOES para construir testes que podem ser avaliados.

**Regra de confiabilidade**: um valor em branco significa indisponível; zero apenas para uma observação efetiva de zero. Os registros novos ficam no computador/plataforma onde foram salvos até serem enviados novamente ao Projeto.
