/**
 * Public sales page — a 1:1 React port of `projects/landing-reference/index.html`
 * (the approved design). Static copy lives in `landingContent.ts`; everything
 * deployment-specific comes from GET /api/public/settings (product name, price,
 * recap items + anchors + derived total, guarantee days, author).
 *
 * Loading rule: `showSkeleton = isPending && !data` — skeleton ONLY on the dynamic
 * spans; the rest of the page renders immediately. Error → page stays, prices hide,
 * CTA reads "Indisponível no momento". No login link anywhere (public page).
 */
import { useState, type CSSProperties } from "react";
import { CheckoutDialog } from "@/components/CheckoutDialog";
import { usePublicSettings } from "@/hooks/useStore";
import { assetUrl, formatBRLShort } from "@/lib/api";
import { CLAUSES, COMPARE, FEARS, KIT, STEPS, WHO, dias, faqItems } from "./landingContent";
import "./landing.css";

import aVista from "@/assets/landing/a-vista-p1.jpg";
import financiado from "@/assets/landing/financiado-p4.jpg";
import parcelado1 from "@/assets/landing/parcelado-direto-p1.jpg";
import parcelado2 from "@/assets/landing/parcelado-direto-p2.jpg";
import parcelado3 from "@/assets/landing/parcelado-direto-p3.jpg";
import postAluguel from "@/assets/landing/post-aluguel.jpg";
import postHabitos from "@/assets/landing/post-habitos.jpg";
import postJuros from "@/assets/landing/post-juros.jpg";
import postMudar from "@/assets/landing/post-mudar.jpg";
import postTijolos from "@/assets/landing/post-tijolos.jpg";

const KIT_IMG = { aVista, financiado, parcelado: parcelado2 };
const MT18: CSSProperties = { marginTop: 18 };
const MT14: CSSProperties = { marginTop: 14 };

const Tear = ({ down = false }: { down?: boolean }) => (
  <svg className={down ? "tear down" : "tear"} aria-hidden="true"><use href="#store-tear" /></svg>
);

/** Skeleton stand-in for a dynamic span while the settings are first loading. */
const Sk = ({ w = "6ch", block = false }: { w?: string; block?: boolean }) => (
  <span className={block ? "sk block" : "sk"} style={{ minWidth: w }} aria-hidden="true" />
);

export default function Landing() {
  const { data, showSkeleton, isError } = usePublicSettings();
  const [open, setOpen] = useState(false);

  const unavailable = isError && !data;
  const paused = !!data && !data.checkout_enabled;
  const days = data && data.guarantee_days > 0 ? data.guarantee_days : null;
  const name = data?.product_name;
  const priceShort = data ? formatBRLShort(data.price_cents) : null;
  const priceNum = data
    ? data.price_cents % 100 === 0 ? String(data.price_cents / 100) : (data.price_cents / 100).toFixed(2).replace(".", ",")
    : null;
  const author = data?.author;

  const cta = (label = "Quero meu contrato") => (
    <button
      type="button"
      className="btn"
      disabled={unavailable || paused}
      onClick={() => setOpen(true)}
    >
      {unavailable ? "Indisponível no momento" : paused ? "Vendas pausadas no momento" : (
        <>{label} <svg><use href="#store-arrow" /></svg></>
      )}
    </button>
  );

  return (
    <div className="store-landing">
      <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true">
        <symbol id="store-tear" viewBox="0 0 1200 30" preserveAspectRatio="none"><path fill="currentColor" d="M0,30 L0,14 L23,16 L40,6 L60,15 L77,20 L104,5 L123,17 L163,6 L192,6 L233,5 L254,11 L271,22 L310,5 L338,5 L360,13 L400,8 L421,22 L454,21 L479,7 L505,15 L525,21 L543,22 L560,10 L605,21 L646,14 L689,22 L732,15 L765,11 L790,11 L809,22 L842,20 L887,14 L929,13 L947,7 L993,17 L1017,14 L1040,19 L1080,5 L1098,21 L1132,14 L1168,19 L1200,14 L1200,30 Z" /></symbol>
        <symbol id="store-arrow" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" strokeWidth="2.4" d="M4 12h15m-6-6 6 6-6 6" /></symbol>
      </svg>

      {/* 1 · HERO */}
      <header className="band hero">
        <div className="strip" aria-hidden="true" />
        <div className="in">
          <div className="copy">
            <p className="eyebrow">{showSkeleton ? <Sk w="18ch" /> : `${name ?? "Modelo pronto"} · Word editável + PDF`}</p>
            <h1 style={MT18}>Um contrato mal feito pode custar <span className="k">o imóvel inteiro</span>.</h1>
            <p className="deck">Copie o contrato de compra e venda construído a partir de negociações reais e feche negócio com cada risco previsto por escrito.</p>
            <ul className="pills">
              <li>3 modalidades de pagamento</li>
              <li>Até 15 cláusulas</li>
              <li>Campos destacados para preencher</li>
            </ul>
            <div className="actions">
              {cta()}
              <small>Acesso imediato no seu e-mail</small>
            </div>
          </div>
          <div className="collage" aria-label="Páginas do contrato sobre um disco dourado">
            <div className="disc" />
            <img className="page p3" src={parcelado3} alt="" />
            <img className="page p2" src={parcelado2} alt="" />
            <img className="page p1" src={parcelado1} alt="Primeira página do Instrumento Particular de Promessa de Venda e Compra de Bem Imóvel" />
            <svg className="orbit" viewBox="0 0 500 140" aria-hidden="true"><ellipse cx="250" cy="70" rx="236" ry="44" transform="rotate(-8 250 70)" /></svg>
            <div className="tag t2">[CAMPOS EM AMARELO] é só preencher</div>
            <div className="tag t1"><b>.docx + .pdf</b>abre no Word e no Google Docs</div>
          </div>
        </div>
      </header>

      {/* 2 · WHY IT EXISTS (Instagram) */}
      <section className="band night">
        <Tear />
        <div className="in center">
          <p className="eyebrow">Do Instagram do Gilson para a sua mesa</p>
          <h2 style={MT14}>Vocês pediram <span className="k">o contrato</span>.</h2>
          <p className="lead">Depois de muitos pedidos nos comentários e no direct, o contrato que o Gilson usa nas negociações virou um modelo genérico, sem nenhum dado de cliente, pronto para você usar.</p>
        </div>
        <div className="reels" aria-label="Posts do Instagram do Gilson">
          <div className="track">
            <img src={postAluguel} alt="Post: O que acontece com o dinheiro de alguém que paga aluguel por 10 anos é assustador" />
            <img src={postMudar} alt="Post: Você pode mudar quase tudo em um imóvel, menos o mais importante" />
            <img src={postHabitos} alt="Post: 3 hábitos que destroem sua performance como corretor" />
            <img src={postTijolos} alt="Post: os 3 hábitos escritos em tijolos" />
            <img src={postJuros} alt="Post: Esperar os juros baixarem pode fazer você pagar muito mais caro pelo imóvel" />
            {[postAluguel, postMudar, postHabitos, postTijolos, postJuros].map((src, i) => (
              <img key={i} src={src} alt="" aria-hidden="true" />
            ))}
          </div>
        </div>
        <Tear down />
      </section>

      {/* 3 · PAIN → CLAUSE */}
      <section className="band paper-band" id="medos">
        <div className="in">
          <p className="eyebrow">Eu sei o que tira o seu sono</p>
          <h2 style={MT14}>Cada medo da negociação tem <span className="k">uma cláusula</span> resolvendo.</h2>
          <p className="lead">Quem já comprou ou vendeu imóvel conhece essas perguntas. Um contrato improvisado deixa todas em aberto. Este deixa cada uma respondida por escrito, antes do sinal.</p>
          <div className="fears">
            {FEARS.map((f) => (
              <article className="fear" key={f.q}>
                <q>{f.q}</q>
                <div className="ans"><span className="cl">{f.cl}</span><p>{f.p}</p></div>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* 4 · YES QUESTION + COMPARE */}
      <section className="band navy">
        <Tear />
        <div className="in">
          <p className="eyebrow">Agora eu te pergunto</p>
          <h2 style={MT14}>Se você pudesse fechar o próximo negócio com <span className="k">um contrato completo</span> em minutos, faria sentido pra você?</h2>
          <p className="lead">Se a resposta for sim, olhe a diferença entre um contrato improvisado e este modelo.</p>
          <div className="compare">
            <table>
              <thead><tr><th>O que protege você</th><th>Modelo improvisado</th><th>Contrato Blindado</th></tr></thead>
              <tbody>
                {COMPARE.map(([a, b, c]) => (
                  <tr key={a}><td>{a}</td><td><span className="no">{b}</span></td><td><span className="yes">{c}</span></td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <Tear down />
      </section>

      {/* 5 · DELIVERABLES */}
      <section className="band paper-band" id="kit">
        <div className="in">
          <p className="eyebrow">Veja tudo que você recebe</p>
          <h2 style={MT14}>Três contratos, <span className="k">um para cada negócio</span>.</h2>
          <div className="kit">
            {KIT.map((k) => (
              <div className="item" key={k.title}>
                <div className="media"><div className="disc" /><img src={KIT_IMG[k.img]} alt={k.alt} /></div>
                <div>
                  <span className="badge">{k.badge}</span>
                  <h3 style={{ marginTop: 12 }}>{k.title}</h3>
                  <ul>{k.bullets.map((b) => <li key={b}>{b}</li>)}</ul>
                </div>
              </div>
            ))}
          </div>

          <div className="word" aria-label="Exemplo de como o contrato aparece no Word">
            <div className="bar"><i />Contrato-Compra-e-Venda-Imovel-Financiado.docx</div>
            <div className="doc">
              <p><span className="h">CLÁUSULA SEGUNDA</span> – DO PREÇO E CONDIÇÕES DE PAGAMENTO</p>
              <p>O(A) <b>VENDEDOR(A)</b> compromete-se a vender para o(a) <b>COMPRADOR(A)</b> e, este(a) a comprar-lhe o referido imóvel, descrito na Cláusula Primeira, pelo preço certo, firme e irreajustável de <b>R$ <mark>[VALOR TOTAL]</mark> (<mark>[valor total por extenso]</mark>)</b>, que deverá ser pago em moeda corrente nacional conforme a seguir estipulado:</p>
              <p><b>Parcela 01: Sinal e princípio de pagamento:</b> R$ <mark>[VALOR DO SINAL]</mark>, com vencimento em <mark>[data]</mark>, por meio de <mark>[PIX / transferência bancária]</mark>…</p>
            </div>
          </div>
          <p className="lead center" style={{ marginInline: "auto" }}>Tudo que você precisa trocar aparece em amarelo. O resto já está redigido.</p>
        </div>
      </section>

      {/* 6 · CLAUSE INDEX */}
      <section className="band paper-band" style={{ paddingTop: 0 }}>
        <div className="in">
          <p className="eyebrow">Ainda não acabou</p>
          <h2 style={MT14}>As 15 cláusulas do <span className="k">contrato parcelado</span>.</h2>
          <ol className="clauses">
            {CLAUSES.map(([t, d]) => <li key={t}><span>{t}<em>{d}</em></span></li>)}
          </ol>
        </div>
      </section>

      {/* 7 · FOR WHO */}
      <section className="band navy">
        <Tear />
        <div className="in">
          <p className="eyebrow">É para você que</p>
          <h2 style={MT14}>Vai assinar um negócio <span className="k">de seis dígitos</span> em breve.</h2>
          <div className="who">
            {WHO.map(([h, p]) => <div key={h}><h3>{h}</h3><p>{p}</p></div>)}
          </div>
        </div>
        <Tear down />
      </section>

      {/* 8 · OFFER */}
      <section className="band night" id="oferta">
        <Tear />
        <div className="in">
          <div className="center">
            <p className="eyebrow">Recapitulando</p>
            <h2 style={MT14}>
              {unavailable ? <>Tudo que você precisa <span className="k">em um só kit</span>.</> : (
                <>Tudo que você precisa por <span className="k">{showSkeleton ? <Sk w="4ch" /> : priceShort}</span>.</>
              )}
            </h2>
          </div>
          <div className="offer">
            <div className="art" aria-hidden="true">
              <div className="disc" />
              <img className="page p1" src={aVista} alt="" />
              <img className="page p2" src={financiado} alt="" />
              <img className="page p3" src={parcelado2} alt="" />
            </div>
            <div className="body">
              <p className="eyebrow">{showSkeleton ? <Sk w="24ch" /> : `${name ?? "Kit completo"} · kit completo`}</p>
              {showSkeleton && (
                <ul className="recap" aria-hidden="true">
                  {[0, 1, 2, 3].map((i) => <li key={i}><Sk w="70%" /><Sk w="5ch" /></li>)}
                </ul>
              )}
              {data && (
                <>
                  <ul className="recap">
                    {data.items.map((it, i) => (
                      <li key={`${it.label}-${i}`}><span>{it.label}</span><span className="strike">{formatBRLShort(it.anchor_cents)}</span></li>
                    ))}
                  </ul>
                  <div className="total"><span>Tudo isso deveria custar</span><span className="strike">{formatBRLShort(data.anchor_total_cents)}</span></div>
                </>
              )}
              {!unavailable && (
                <div className="price">
                  <span className="from">Hoje, você leva tudo por</span>
                  <span className="now"><small>R$</small>{showSkeleton ? <Sk w="2ch" /> : priceNum}</span>
                  <span className="how">à vista no PIX ou parcelado no cartão</span>
                </div>
              )}
              <div style={{ marginTop: 22 }}>{cta()}</div>
              <div className="safe">
                <span>Pagamento seguro</span>
                <span>Acesso imediato</span>
                {days ? <span>Garantia de {dias(days)}</span> : showSkeleton ? <span><Sk w="12ch" /></span> : null}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 9 · ACCESS STEPS */}
      <section className="band paper-band">
        <Tear />
        <div className="in">
          <p className="eyebrow">Como você recebe</p>
          <h2 style={MT14}>Do pagamento ao contrato pronto em <span className="k">três passos</span>.</h2>
          <ol className="steps">
            {STEPS.map(([h, p]) => <li key={h}><h3>{h}</h3><p>{p}</p></li>)}
          </ol>
        </div>
      </section>

      {/* 10 · GUARANTEE */}
      {(days || showSkeleton) && (
        <section className="band paper-band" style={{ paddingTop: 0 }}>
          <div className="in guarantee">
            <div className="seal"><div className="disc" /><b>{days ?? <Sk w="1ch" />}<small>{days === 1 ? "dia de garantia" : "dias de garantia"}</small></b></div>
            <div>
              <h2>Abriu e não gostou? <span className="k">Devolvemos tudo.</span></h2>
              <p className="lead">
                Você tem {days ? dias(days) : <Sk w="6ch" />} para baixar, ler cada cláusula e decidir. Se achar que não serve para você, peça o reembolso e recebe 100% do valor, sem precisar explicar.
              </p>
            </div>
          </div>
        </section>
      )}

      {/* 11 · TWO CHOICES */}
      <section className="band night">
        <Tear />
        <div className="in">
          <p className="eyebrow">Agora você tem duas opções</p>
          <h2 style={MT14}>O próximo contrato que você assinar vai <span className="k">proteger ou expor</span> você.</h2>
          <div className="choices">
            <div className="choice bad"><span className="lbl">Opção 1</span><h3>Improvisar</h3><p>Copiar um modelo qualquer, torcer para nada dar errado e descobrir a cláusula que faltou quando o problema já chegou.</p></div>
            <div className="choice good"><span className="lbl">Opção 2</span><h3>Assinar com tudo previsto</h3><p>Usar um contrato construído a partir de negociações reais, com cada risco já escrito, por menos de R$ 50.</p></div>
          </div>
          <p className="lead" style={{ marginTop: 28 }}>Eu sei, e você também sabe: a opção 2 é a mais inteligente.</p>
        </div>
        <Tear down />
      </section>

      {/* 12 · AUTHOR */}
      <section className="band paper-band">
        <div className="in author">
          {author?.photo_url ? (
            <div className="photo has"><div className="disc" /><img src={assetUrl(author.photo_url) ?? ""} alt={`Foto de ${author.name}`} /></div>
          ) : (
            <div className="photo"><div className="disc" /><span>{author ? `Foto de ${author.name} em preto e branco, recortada, sobre o disco dourado` : " "}</span></div>
          )}
          <div>
            <p className="eyebrow">Quem está por trás</p>
            <h2 style={MT14}>
              {showSkeleton ? <Sk w="12ch" /> : author ? <>{author.name}, <span className="k">{author.role}</span>.</> : null}
            </h2>
            <p className="lead">{showSkeleton ? <><Sk w="100%" block /><Sk w="100%" block /><Sk w="60%" block /></> : author?.bio}</p>
            <div className="rule" />
          </div>
        </div>
      </section>

      {/* 13 · OFFER REPEAT */}
      <section className="band night">
        <Tear />
        <div className="in center">
          <h2>Seu próximo negócio, <span className="k">blindado</span>.</h2>
          <p className="deck" style={{ marginInline: "auto" }}>
            3 contratos em Word e PDF, 14 certidões listadas{days ? `, garantia de ${dias(days)}` : ""}.
          </p>
          {!unavailable && (
            <div className="price" style={{ justifyItems: "center", color: "var(--paper)" }}>
              <span className="from" style={{ color: "var(--muted-night)" }}>
                De <span className="strike" style={{ color: "var(--muted-night)" }}>{data ? formatBRLShort(data.anchor_total_cents) : <Sk w="5ch" />}</span> por
              </span>
              <span className="now" style={{ color: "var(--paper)" }}><small>R$</small>{showSkeleton ? <Sk w="2ch" /> : priceNum}</span>
            </div>
          )}
          <p style={{ marginTop: 26 }}>{cta()}</p>
        </div>
        <Tear down />
      </section>

      {/* 14 · FAQ */}
      <section className="band paper-band">
        <div className="in">
          <p className="eyebrow">Perguntas frequentes</p>
          <h2 style={MT14}>Ainda com dúvida?</h2>
          <div className="faq">
            {faqItems(days).map(([q, a], i) => (
              <details key={q} open={i === 0}><summary>{q}</summary><p>{a}</p></details>
            ))}
          </div>
        </div>
      </section>

      <footer>
        <div className="in">
          <p>
            {name ?? "Este material"} é um modelo genérico de contrato e não constitui assessoria jurídica. Os modelos não contêm dados de nenhum cliente. Adapte o texto ao seu caso e, quando necessário, consulte um advogado.
          </p>
        </div>
      </footer>

      <CheckoutDialog open={open} onClose={() => setOpen(false)} productName={name} priceLabel={priceShort} />
    </div>
  );
}
