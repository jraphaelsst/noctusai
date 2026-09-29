/**
 * `/coleta` and `/coleta/:municipio` — the public "calendário de coleta por
 * município" (seed `publicRoutes` slot, same as `/o-projeto`).
 *
 * Answer-first: the search box sits in the hero, and a hit reads as one line
 * per kind of coleta ("Lixo comum: Seg · Qua · Sex, de dia"). A city view
 * groups its schedule by DAY PATTERN (2–4 per city) rather than by the
 * source's 30+ setores; bairros sit behind each pattern, and everything
 * secondary — ecopontos, phones, sources and caveats — is collapsed.
 * Condensing lives in `content/coleta/resumo.ts`; the data in `content/coleta/`.
 *
 * `/coleta/<slug>` is the shareable link (Instagram, WhatsApp, revista); an
 * unknown slug falls back to the city list rather than a blank page.
 */
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowRight, ChevronDown, ExternalLink, Search } from 'lucide-react';

import { SiteHeader } from '@/components/site/SiteHeader';
import { SiteFooter } from '@/components/site/SiteFooter';
import { InterestPopup } from '@/components/InterestPopup';
import { MUNICIPIOS, municipioPorSlug } from '@/content/coleta';
import { buscar, diaDeHoje, MIN_BUSCA, passaNoDia } from '@/content/coleta/busca';
import { agruparPorDias, agruparResultados, diasPorExtenso, resumoRota, type Grupo, type Local } from '@/content/coleta/resumo';
import { DIA_LONGO, type Dia, type Municipio, type PontoEntrega } from '@/content/coleta/tipos';
import './landing.css';

const EMAIL_CONTRIBUIR =
  'mailto:oi@academiadareciclagem.org.br?subject=' + encodeURIComponent('Dia de coleta no meu bairro');
const MAX_RESULTADOS = 12;

function formatarData(iso: string): string {
  const [ano, mes, dia] = iso.split('-');
  return dia ? `${dia}/${mes}/${ano}` : `${mes}/${ano}`;
}

function Hoje() {
  return <span className="coleta-hoje">hoje</span>;
}

function ResultadoCard({ local, hoje }: { local: Local; hoje: Dia }) {
  const passaHoje = [...local.comum, ...local.seletiva].some((r) => passaNoDia(r, hoje));
  return (
    <li className="coleta-card" data-testid="coleta-resultado">
      <div className="coleta-card-topo">
        <strong className="coleta-card-nome">{local.rua ?? local.nome}</strong>
        {passaHoje && <Hoje />}
      </div>
      <div className="coleta-card-onde">
        {local.rua ? `${local.nome} · ` : ''}
        <Link to={`/coleta/${local.municipio.slug}`}>{local.municipio.nome}</Link>
      </div>
      <dl className="coleta-linhas">
        {local.comum.length > 0 && (
          <div>
            <dt>Lixo comum</dt>
            <dd>{local.comum.map(resumoRota).join(' / ')}</dd>
          </div>
        )}
        {local.seletiva.length > 0 && (
          <div>
            <dt>Recicláveis</dt>
            <dd>{local.seletiva.map(resumoRota).join(' / ')}</dd>
          </div>
        )}
      </dl>
    </li>
  );
}

function GrupoLinha({ grupo, hoje }: { grupo: Grupo; hoje: Dia }) {
  const semDias = grupo.frequencia ?? 'dias não informados';
  const quando = grupo.dias.length ? diasPorExtenso(grupo.dias) : semDias[0].toUpperCase() + semDias.slice(1);
  return (
    <li>
      <details className="coleta-grupo" data-testid="coleta-grupo">
        <summary>
          <span className="coleta-grupo-quando">
            <span className="coleta-grupo-dias">{quando}</span>
            {grupo.periodo && <span className="coleta-grupo-periodo">{grupo.periodo}</span>}
          </span>
          {grupo.dias.includes(hoje) && <Hoje />}
          <span className="coleta-grupo-qtd">{grupo.bairros.length} {grupo.bairros.length === 1 ? 'local' : 'locais'}</span>
          <ChevronDown size={16} className="coleta-chevron" aria-hidden="true" />
        </summary>
        <p className="coleta-grupo-bairros">{grupo.bairros.join(' · ')}</p>
        {grupo.notas.map((n) => <p key={n} className="coleta-nota">{n}</p>)}
      </details>
    </li>
  );
}

function Grupos({ titulo, grupos, vazio, hoje }: { titulo: string; grupos: Grupo[]; vazio: string; hoje: Dia }) {
  return (
    <div className="coleta-bloco">
      <h3 className="coleta-bloco-titulo">{titulo}</h3>
      {grupos.length > 0 ? (
        <ul className="coleta-grupos">{grupos.map((g, i) => <GrupoLinha key={i} grupo={g} hoje={hoje} />)}</ul>
      ) : (
        <p className="coleta-vazio">{vazio}</p>
      )}
    </div>
  );
}

function Recolhivel({ titulo, children, testid }: { titulo: string; children: ReactNode; testid?: string }) {
  return (
    <details className="coleta-extra" data-testid={testid}>
      <summary>
        {titulo}
        <ChevronDown size={16} className="coleta-chevron" aria-hidden="true" />
      </summary>
      <div className="coleta-extra-corpo">{children}</div>
    </details>
  );
}

function Pontos({ pontos }: { pontos: PontoEntrega[] }) {
  return (
    <ul className="coleta-pontos">
      {pontos.map((p) => (
        <li key={`${p.nome}|${p.endereco}`}>
          <strong>{p.nome}</strong>
          <span>{p.endereco}</span>
          {p.horario && <span className="coleta-muted">{p.horario}</span>}
          {p.aceita && <span className="coleta-muted">{p.aceita}</span>}
        </li>
      ))}
    </ul>
  );
}

function CidadePainel({ municipio, hoje }: { municipio: Municipio; hoje: Dia }) {
  const comum = agruparPorDias(municipio.rotas, 'comum');
  const seletiva = agruparPorDias(municipio.rotas, 'seletiva');
  const principal = municipio.fontes[0];
  const pontos = [...municipio.ecopontos, ...municipio.outros];

  return (
    <article className="coleta-cidade-painel" data-testid={`coleta-municipio-${municipio.slug}`}>
      <header className="coleta-cidade-topo">
        <h2 className="coleta-cidade-titulo">{municipio.nome}</h2>
        <p className="coleta-muted">
          {principal?.data ? `Calendário da prefeitura de ${formatarData(principal.data)}` : 'Calendário da prefeitura'}
          {municipio.avisos.length > 0 && ' · pode estar desatualizado, veja abaixo'}
        </p>
      </header>

      {municipio.rotas.length === 0 ? (
        <p className="coleta-resumo">{municipio.resumo}</p>
      ) : (
        <>
          <Grupos titulo="Lixo comum" grupos={comum} hoje={hoje} vazio="A prefeitura não publica os dias." />
          <Grupos
            titulo="Recicláveis"
            grupos={seletiva}
            hoje={hoje}
            vazio="A prefeitura não publica os dias da coleta seletiva por bairro."
          />
        </>
      )}

      <div className="coleta-extras">
        {pontos.length > 0 && (
          <Recolhivel titulo={`Ecopontos e descarte (${pontos.length})`} testid="coleta-ecopontos">
            <Pontos pontos={pontos} />
          </Recolhivel>
        )}
        {municipio.contatos.length > 0 && (
          <Recolhivel titulo="Telefones">
            <ul className="coleta-contatos">
              {municipio.contatos.map((c) => (
                <li key={c.rotulo}>
                  <span className="coleta-muted">{c.rotulo}</span>
                  {c.href ? <a href={c.href}>{c.valor}</a> : <span>{c.valor}</span>}
                </li>
              ))}
            </ul>
          </Recolhivel>
        )}
        <Recolhivel titulo="Sobre estes dados" testid="coleta-sobre">
          {municipio.rotas.length > 0 && <p>{municipio.resumo}</p>}
          {municipio.operador && <p className="coleta-muted">Operação: {municipio.operador}</p>}
          {municipio.avisos.length > 0 && (
            <ul className="coleta-avisos">{municipio.avisos.map((a) => <li key={a}>{a}</li>)}</ul>
          )}
          <ul className="coleta-fontes">
            {municipio.fontes.map((f) => (
              <li key={f.url}>
                <a href={f.url} target="_blank" rel="noreferrer">
                  {f.titulo} <ExternalLink size={11} />
                </a>
                <span className="coleta-muted">
                  {' '}· {f.oficial ? 'oficial' : 'imprensa'}{f.data ? ` · ${formatarData(f.data)}` : ''}
                </span>
              </li>
            ))}
          </ul>
        </Recolhivel>
      </div>
    </article>
  );
}

export default function Coleta() {
  const { municipio: slug } = useParams<{ municipio?: string }>();
  const selecionado = slug ? municipioPorSlug(slug) : undefined;
  const [consulta, setConsulta] = useState('');
  const hoje = diaDeHoje();

  const locais = useMemo(() => agruparResultados(buscar(MUNICIPIOS, consulta, 200)), [consulta]);
  const buscando = consulta.trim().length >= MIN_BUSCA;

  useEffect(() => {
    if (selecionado) document.getElementById('cidade')?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  }, [selecionado]);

  return (
    <div className="academia-landing">
      <SiteHeader />

      <section className="coleta-hero">
        <div className="container-xl coleta-coluna">
          <div className="eyebrow">coleta de lixo · região da Granja Viana</div>
          <h1 className="display coleta-titulo">Que dia passa a coleta?</h1>
          <p className="coleta-sub">Busque seu bairro, condomínio ou rua. Hoje é {DIA_LONGO[hoje]}.</p>
          <label className="coleta-busca" htmlFor="coleta-busca">
            <Search size={18} aria-hidden="true" />
            <input
              id="coleta-busca"
              type="search"
              placeholder="Ex.: Granja Viana, Fazendinha, Rua…"
              value={consulta}
              onChange={(e) => setConsulta(e.target.value)}
              autoComplete="off"
              data-testid="coleta-busca"
            />
          </label>
        </div>
      </section>

      <section className="coleta-corpo">
        <div className="container-xl coleta-coluna">
          {buscando && (
            <div className="coleta-resultados" aria-live="polite">
              {locais.length > 0 ? (
                <>
                  <ul className="coleta-cards">
                    {locais.slice(0, MAX_RESULTADOS).map((l) => (
                      <ResultadoCard key={`${l.municipio.slug}|${l.rua ?? ''}|${l.nome}`} local={l} hoje={hoje} />
                    ))}
                  </ul>
                  {locais.length > MAX_RESULTADOS && (
                    <p className="coleta-muted">Mais {locais.length - MAX_RESULTADOS} resultados — refine a busca.</p>
                  )}
                </>
              ) : (
                <p className="coleta-vazio" data-testid="coleta-sem-resultado">
                  Nada encontrado para "{consulta.trim()}". Escolha a cidade abaixo ou{' '}
                  <a href={EMAIL_CONTRIBUIR}>conte pra gente o dia da coleta aí</a>.
                </p>
              )}
            </div>
          )}

          <nav className="coleta-cidades" aria-label="Cidades">
            {MUNICIPIOS.map((m) => (
              <Link
                key={m.slug}
                to={`/coleta/${m.slug}`}
                className={`coleta-chip ${m.slug === selecionado?.slug ? 'is-ativa' : ''}`}
                aria-current={m.slug === selecionado?.slug ? 'page' : undefined}
                data-testid={`coleta-cidade-${m.slug}`}
              >
                {m.nome}
              </Link>
            ))}
          </nav>

          <div id="cidade">
            {selecionado ? (
              <CidadePainel municipio={selecionado} hoje={hoje} />
            ) : (
              <p className="coleta-vazio">
                {slug ? `Ainda não temos "${slug}". ` : ''}Ou escolha uma cidade para ver o calendário completo.
              </p>
            )}
          </div>

          <p className="coleta-rodape">
            Viu um dia diferente na sua rua?{' '}
            <a href={EMAIL_CONTRIBUIR} data-testid="coleta-contribuir">
              Conte pra gente <ArrowRight size={13} />
            </a>
          </p>
        </div>
      </section>

      <SiteFooter />
      <InterestPopup />
    </div>
  );
}
