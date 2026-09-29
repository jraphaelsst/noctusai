/**
 * `/coleta` and `/coleta/:municipio` — the public "calendário de coleta por
 * município" (seed `publicRoutes` slot, same as `/o-projeto`).
 *
 * The first public-site feature that gives a visitor a reason to come back:
 * "que dia passa o lixo na minha rua?". Data is static, transcribed from each
 * prefeitura's own published schedule (`src/content/coleta/`) — every
 * município shows its source, the source's date and its known caveats, since
 * none of them publishes a machine-readable or reliably-dated schedule.
 *
 * `/coleta/<slug>` is the shareable link (Instagram, WhatsApp, revista); an
 * unknown slug falls back to the município list rather than a blank page.
 */
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowRight, CalendarDays, ExternalLink, MapPin, Phone, Recycle, Search, Trash2, TriangleAlert } from 'lucide-react';

import { SiteHeader } from '@/components/site/SiteHeader';
import { SiteFooter } from '@/components/site/SiteFooter';
import { InterestPopup } from '@/components/InterestPopup';
import { MUNICIPIOS, municipioPorSlug } from '@/content/coleta';
import { buscar, diaDeHoje, MIN_BUSCA, passaNoDia, type Resultado } from '@/content/coleta/busca';
import {
  DIA_CURTO, DIA_LONGO, type Cobertura, type Dia, type Municipio, type PontoEntrega, type Rota,
} from '@/content/coleta/tipos';
import './landing.css';

const SEMANA: Dia[] = ['seg', 'ter', 'qua', 'qui', 'sex', 'sab', 'dom'];

const COBERTURA_ROTULO: Record<Cobertura, string> = {
  completa: 'calendário completo',
  parcial: 'calendário parcial',
  'sem-calendario': 'sem calendário por bairro',
};

const EMAIL_CONTRIBUIR =
  'mailto:oi@academiadareciclagem.org.br?subject=' + encodeURIComponent('Dia de coleta no meu bairro');

function formatarData(iso: string): string {
  const [ano, mes, dia] = iso.split('-');
  return dia ? `${dia}/${mes}/${ano}` : `${mes}/${ano}`;
}

function DiasDaSemana({ dias, hoje, frequencia }: { dias: Dia[]; hoje: Dia; frequencia?: string }) {
  if (dias.length === 0) {
    return <span className="coleta-frequencia">{frequencia ?? 'dias não informados na fonte'}</span>;
  }
  return (
    <div className="coleta-dias" aria-label={`Dias: ${dias.map((d) => DIA_LONGO[d]).join(', ')}`}>
      {SEMANA.map((d) => (
        <span
          key={d}
          aria-hidden="true"
          className={`coleta-dia ${dias.includes(d) ? 'is-on' : ''} ${d === hoje ? 'is-hoje' : ''}`}
        >
          {DIA_CURTO[d]}
        </span>
      ))}
    </div>
  );
}

function TipoBadge({ tipo }: { tipo: Rota['tipo'] }) {
  return tipo === 'seletiva' ? (
    <span className="coleta-tipo is-seletiva"><Recycle size={13} /> recicláveis</span>
  ) : (
    <span className="coleta-tipo"><Trash2 size={13} /> coleta comum</span>
  );
}

function RotaLinha({ rota, hoje }: { rota: Rota; hoje: Dia }) {
  return (
    <li className="coleta-rota" data-testid="coleta-rota">
      <div className="coleta-rota-head">
        <div>
          {rota.setor && <div className="coleta-setor">{rota.setor}</div>}
          <div className="coleta-meta">
            <TipoBadge tipo={rota.tipo} />
            {rota.periodo && <span className="coleta-periodo">{rota.periodo}</span>}
            {passaNoDia(rota, hoje) && <span className="coleta-hoje" data-testid="coleta-hoje">passa hoje</span>}
          </div>
        </div>
        <DiasDaSemana dias={rota.dias} hoje={hoje} frequencia={rota.frequencia} />
      </div>
      <p className="coleta-bairros">{rota.bairros.join(' · ')}</p>
      {rota.nota && <p className="coleta-nota">{rota.nota}</p>}
    </li>
  );
}

function Pontos({ titulo, pontos }: { titulo: string; pontos: PontoEntrega[] }) {
  if (pontos.length === 0) return null;
  return (
    <div className="coleta-bloco">
      <h3 className="coleta-bloco-titulo">{titulo}</h3>
      <ul className="coleta-pontos">
        {pontos.map((p) => (
          <li key={`${p.nome}|${p.endereco}`} className="coleta-ponto">
            <strong>{p.nome}</strong>
            <span className="coleta-ponto-linha"><MapPin size={13} /> {p.endereco}</span>
            {p.horario && <span className="coleta-ponto-linha"><CalendarDays size={13} /> {p.horario}</span>}
            {p.aceita && <span className="coleta-ponto-aceita">{p.aceita}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function MunicipioPainel({ municipio, hoje }: { municipio: Municipio; hoje: Dia }) {
  const comum = municipio.rotas.filter((r) => r.tipo === 'comum');
  const seletiva = municipio.rotas.filter((r) => r.tipo === 'seletiva');

  return (
    <article className="coleta-municipio" data-testid={`coleta-municipio-${municipio.slug}`}>
      <header className="coleta-municipio-head">
        <div className="eyebrow">{COBERTURA_ROTULO[municipio.cobertura]}</div>
        <h2 className="display coleta-municipio-nome">{municipio.nome}</h2>
        <p className="section-intro">{municipio.resumo}</p>
        {municipio.operador && <p className="coleta-operador">Operação: {municipio.operador}</p>}
      </header>

      {municipio.avisos.length > 0 && (
        <div className="coleta-aviso" role="note" data-testid="coleta-avisos">
          <TriangleAlert size={18} />
          <ul>{municipio.avisos.map((a) => <li key={a}>{a}</li>)}</ul>
        </div>
      )}

      {comum.length > 0 && (
        <div className="coleta-bloco">
          <h3 className="coleta-bloco-titulo">Coleta comum (lixo doméstico)</h3>
          <ul className="coleta-rotas">{comum.map((r, i) => <RotaLinha key={i} rota={r} hoje={hoje} />)}</ul>
        </div>
      )}

      {seletiva.length > 0 && (
        <div className="coleta-bloco">
          <h3 className="coleta-bloco-titulo">Coleta seletiva (recicláveis)</h3>
          <ul className="coleta-rotas">{seletiva.map((r, i) => <RotaLinha key={i} rota={r} hoje={hoje} />)}</ul>
        </div>
      )}

      <Pontos titulo="Ecopontos" pontos={municipio.ecopontos} />
      <Pontos titulo="Outros pontos e serviços" pontos={municipio.outros} />

      {municipio.contatos.length > 0 && (
        <div className="coleta-bloco">
          <h3 className="coleta-bloco-titulo">Dúvidas e reclamações</h3>
          <ul className="coleta-contatos">
            {municipio.contatos.map((c) => (
              <li key={c.rotulo}>
                <Phone size={13} /> {c.rotulo}:{' '}
                {c.href ? <a href={c.href}>{c.valor}</a> : c.valor}
              </li>
            ))}
          </ul>
        </div>
      )}

      <footer className="coleta-fontes">
        <div className="eyebrow">fontes</div>
        <ul>
          {municipio.fontes.map((f) => (
            <li key={f.url}>
              <a href={f.url} target="_blank" rel="noreferrer">
                {f.titulo} <ExternalLink size={12} />
              </a>{' '}
              <span className="coleta-fonte-meta">
                {f.oficial ? 'oficial' : 'imprensa'} · {f.data ? `documento de ${formatarData(f.data)}` : 'sem data na fonte'}
              </span>
            </li>
          ))}
        </ul>
      </footer>
    </article>
  );
}

function ResultadoLinha({ r, hoje }: { r: Resultado; hoje: Dia }) {
  return (
    <li className="coleta-resultado" data-testid="coleta-resultado">
      <div className="coleta-rota-head">
        <div>
          <div className="coleta-setor">
            {r.rua ? `${r.rua} — ${r.termo}` : r.termo}
          </div>
          <div className="coleta-meta">
            <Link to={`/coleta/${r.municipio.slug}`} className="coleta-resultado-municipio">{r.municipio.nome}</Link>
            <TipoBadge tipo={r.rota.tipo} />
            {r.rota.periodo && <span className="coleta-periodo">{r.rota.periodo}</span>}
            {passaNoDia(r.rota, hoje) && <span className="coleta-hoje">passa hoje</span>}
          </div>
        </div>
        <DiasDaSemana dias={r.rota.dias} hoje={hoje} frequencia={r.rota.frequencia} />
      </div>
      {r.rota.setor && r.rota.setor !== r.termo && <p className="coleta-nota">{r.rota.setor}</p>}
    </li>
  );
}

export default function Coleta() {
  const { municipio: slug } = useParams<{ municipio?: string }>();
  const selecionado = slug ? municipioPorSlug(slug) : undefined;
  const [consulta, setConsulta] = useState('');
  const hoje = diaDeHoje();

  const resultados = useMemo(() => buscar(MUNICIPIOS, consulta), [consulta]);
  const buscando = consulta.trim().length >= MIN_BUSCA;

  useEffect(() => {
    if (selecionado) document.getElementById('municipio')?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  }, [selecionado]);

  return (
    <div className="academia-landing">
      <SiteHeader />

      <section className="sub-hero">
        <div className="container-xl">
          <div className="eyebrow">coleta de lixo · região da Granja Viana</div>
          <h1 className="display section-title">
            Que dia passa a<br />coleta na sua rua?
          </h1>
          <p className="section-intro">
            Os dias da coleta comum e da coleta seletiva, os ecopontos e os telefones de cada cidade da região,
            reunidos a partir dos calendários publicados pelas prefeituras. Hoje é <strong>{DIA_LONGO[hoje]}</strong>.
          </p>
        </div>
      </section>

      <section className="section coleta-section">
        <div className="container-xl">
          <label className="coleta-busca" htmlFor="coleta-busca">
            <Search size={18} />
            <input
              id="coleta-busca"
              type="search"
              placeholder="Digite seu bairro, condomínio ou rua"
              value={consulta}
              onChange={(e) => setConsulta(e.target.value)}
              autoComplete="off"
              data-testid="coleta-busca"
            />
          </label>

          {buscando && (
            <div className="coleta-bloco" aria-live="polite">
              {resultados.length > 0 ? (
                <ul className="coleta-rotas">
                  {resultados.map((r, i) => <ResultadoLinha key={i} r={r} hoje={hoje} />)}
                </ul>
              ) : (
                <p className="coleta-vazio" data-testid="coleta-sem-resultado">
                  Não encontramos "{consulta.trim()}". Tente o nome do bairro como a prefeitura escreve, escolha a
                  cidade abaixo — ou <a href={EMAIL_CONTRIBUIR}>conte pra gente o dia da coleta aí</a>.
                </p>
              )}
            </div>
          )}

          <nav className="coleta-cidades" aria-label="Cidades">
            {MUNICIPIOS.map((m) => (
              <Link
                key={m.slug}
                to={`/coleta/${m.slug}`}
                className={`coleta-cidade ${m.slug === selecionado?.slug ? 'is-ativa' : ''}`}
                aria-current={m.slug === selecionado?.slug ? 'page' : undefined}
                data-testid={`coleta-cidade-${m.slug}`}
              >
                <span className="coleta-cidade-nome">{m.nome}</span>
                <span className="coleta-cidade-cobertura">{COBERTURA_ROTULO[m.cobertura]}</span>
              </Link>
            ))}
          </nav>

          <div id="municipio">
            {selecionado ? (
              <MunicipioPainel municipio={selecionado} hoje={hoje} />
            ) : (
              <p className="coleta-vazio">
                {slug ? `Ainda não temos "${slug}". ` : ''}Escolha uma cidade acima para ver o calendário completo.
              </p>
            )}
          </div>

          <div className="coleta-contribuir">
            <p>
              Os calendários mudam quando muda a empresa ou o contrato — e nem sempre a prefeitura avisa. Viu algo
              diferente na sua rua? Sua portaria sabe o dia?
            </p>
            <a className="join-link" href={EMAIL_CONTRIBUIR} data-testid="coleta-contribuir">
              Conte pra gente <ArrowRight size={16} />
            </a>
          </div>
        </div>
      </section>

      <SiteFooter />
      <InterestPopup />
    </div>
  );
}
