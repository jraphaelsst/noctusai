# DECISIONS — clinical tools + área do paciente (nome a definir) in Nós no Limiar

## Decided (owner)

### Round 1 — 2026-11-02

| # | Topic | Decision |
|---|---|---|
| D1 | Home | A feature **inside Nós no Limiar**. Nós no Limiar's patient records (`clients` organ) are the data source. Not a new product. |
| D2 | Posture | The reference app is a reference for *what the feature needs*, not a template. We design our own model, properly: few orthogonal concepts (`ENGINE.md`). No copied content, wording or structure. |
| D3 | Engine | **Seed organ**, consumed by Nós no Limiar. the native patient app and therapy-platform reuse it later without a fork. |
| D4 | Patient side | **área do paciente (nome a definir) web area inside Nós no Limiar**: tools now, diary next. The native app comes later on the same organ API. *(Amended by D9: patients log in; it is no longer "no login".)* |
| D5 | Pause | Progress is saved on the server after every step. The patient resumes at the same step. |
| D6 | Quick exit | Instant neutral screen, Back doesn't return, the patient is signed out, and our own traces on the device are cleared. On the next sign-in **the patient chooses** keep or discard. *(Reworded per the LGPD review: we cannot promise "nothing on the device"; see S-QE.)* |
| D7 | Tools as data | A tool is a versioned document (5 question kinds · 3 modifiers · 6 result blocks). Choices are stored by stable ids, pinned to the tool version. |
| D8 | First release content | **6 pilot tools**, one per theme, in our own words, covering every kind, modifier and block plus one sensitive tool. |

### Round 2 — 2026-11-02

| # | Topic | Decision |
|---|---|---|
| D9 | **Patient identity (model B)** | Patients are **noc users** (same Supabase Auth / SSO login system as everyone) but **NOT members of Mônica's org**. The account is linked to the patient record (`clients.user_id`). área do paciente (nome a definir) authorizes only "the record linked to this account". Staff surfaces never see patients, and existing "any org member" rules stay untouched. One account can link to records in several orgs. The identity link is a **seed organ** (generic "external user ↔ record" access, reusable by any product with end customers). |
| D10 | Onboarding | On the patient record, Mônica clicks **Convidar para a área do paciente**. The invite goes by WhatsApp (Nós no Limiar's connection) or e-mail, and the patient creates their account with the standard noc sign-in methods. Every tool link opens área do paciente (nome a definir), and **without a session nothing is shown**. |
| D11 | No PIN | Login replaces the PIN idea entirely. |
| D12 | Tool editor (Q1) | **Full editor from day one.** Mônica creates and edits tools: question kinds, modifiers, result blocks, texts, clinician guide. Draft → preview → publish creates a new version, and old results keep rendering with their version. The editor writes only what the engine validates. The 6 pilot tools ship as our starting content, editable by her. |
| D13 | Diary (Q2) | **Tools first, diary next.** Release 1 = tools + the área do paciente (nome a definir) shell (invite, sign-in, consent, home). Release 2 = the diary, with "levar à análise" landing on the record instead of a copied WhatsApp text. |
| D14 | Assignment life (Q4) | An assignment is open until completed. Unopened or idle assignments expire after **30 days** (every saved step resets the idle clock). Mônica can revoke or resend any time; resend reuses the assignment. |
| D15 | Patient's own results (Q5) | The patient keeps their results **in their patient area (name TBD), behind login**. **No PDF download.** |
| D16 | Vocabulary | **Fully gender-neutral everywhere**, Nós no Limiar's UI included. This supersedes the "analisanda (mulher)" rule of the área do paciente (nome a definir) spec. The neutral person term is to be chosen with Mônica (e.g. "pessoa em análise"); "análise"/"sessão" stay. The engine stays vocabulary-configurable per product. |
| D17 | Quick exit scope | **Every tool** has a discreet quick-exit control. `sensitive` tools additionally get the opening warning and Mônica's confirmation before sending. |

## Security & LGPD requirements (from the `security` advisor review, 2026-11-02)

MUST unless marked SHOULD. These are binding for the build contract.

| # | Requirement |
|---|---|
| S-LB | **Legal basis = art. 11 I (specific, highlighted consent)**. Do not rely on art. 11 II f: psychoanalysis is not a regulated health profession. **Lawyer to confirm** (owner action). |
| S-CO | Consent screen on first sign-in, **versioned and recorded** (`tool_consents`: `client_id`, `user_id`, `version`, `accepted_at`). It states: Mônica = controller, NoctusAI = operator, purpose (preparing sessions; no AI processing), retention, art. 18 rights, contact, hosting location. |
| S-DPA | Controller↔operator agreement (DPA) between Mônica and NoctusAI. **Owner action.** |
| S-RG | Check the Supabase region. If it is outside Brazil, the art. 33 international-transfer disclosure applies. |
| S-RT | Retention: completed answers = clinical record until treatment ends + **N years (lawyer; CFP Res. 01/2009 = 5 years if a CRP applies)**. Exited answers are **hidden from Mônica until the patient chooses keep**, and auto-discarded after 30 days without a choice. Expired or revoked assignments: answers deleted, metadata kept. |
| S-DEL | Discard and patient deletion are a **real DELETE**, cascading clients → assignments → responses → consents (identity link removed). The backup (PITR) window is disclosed in the consent. |
| S-ACL | Tool tables are service-role only (like `clients`). Reading answers requires the **clinician role** (not `membro`/staff). Patients reach only their linked record via the D9 access path. |
| S-ENC | SHOULD: app-level encryption (AES-GCM, key outside the DB) of `answers` and Mônica's private notes. |
| S-AUD | Append-only **read audit**: who, when, `assignment_id`, never content. Answers are never logged. |
| S-LNK | Links carry no name, tool slug or client id, only an opaque id that needs a session. The GET has no side effects (WhatsApp's preview crawler must not mark "opened"), and OG tags and page titles stay neutral. |
| S-QE | Quick exit: `sendBeacon` marks `exited` → server responds with `Clear-Site-Data` + sign-out → `location.replace` to a neutral site. área do paciente (nome a definir) uses `Cache-Control: no-store`, no service worker, no localStorage for answers, and `autocomplete=off`. The patient is told honestly what we **can't** erase: the WhatsApp message and its notifications, earlier history entries, keyboard learning, screenshots, synced browsers. |
| S-RES | On resume, earlier free-text answers are only re-shown after sign-in (D9 makes this automatic). |

**Previous-spec defects fixed in `ENGINE.md` v0.2:** answers also hold free text (not "ids only"); `org_id` added to every table; `expires_at`/`last_activity_at`/`exited_at` added; consents, audit and the identity link added; resend semantics stated; preview-crawler side effects addressed.

## Open

| # | Question | Who |
|---|---|---|
| Q3a | Legal basis confirmation + retention years | owner → lawyer |
| Q6 | Seed organ names: `guided-tools` (engine) + `client-portal` (external identity/access) | owner (proposal stands unless changed) |
| M1 | Themes (draft: Relação consigo · História · Vínculos · Corpo e rotina · Repetições · Desejo e futuro) | Mônica |
| M2 | The 6 pilot tools (below) | Mônica |
| M3 | Neutral term for the person in analysis (D16) | Mônica |

### The 6 pilot tools (concepts; content written with Mônica)

| Theme | Pilot concept | Kinds + modifiers | Result blocks |
|---|---|---|---|
| Relação consigo | **A voz que eu uso comigo**: how one speaks to oneself across everyday situations, and what one would say to someone dear | `choose`+`for_each` · `write`+`when` | `map` · `tally` · `quotes` |
| História *(sensitive)* | **O que eu perdi e o que ficou**: losses and what remains of them | `choose` (multi, `allow_other`) · `order` · `write` | `quotes` · `reflection` |
| Vínculos | **Quem está perto**: placing people in close / middle / far circles | `group` · `choose`+`options_from` | `chart:circles` · `quotes` |
| Corpo e rotina | **Minha semana de verdade**: a week as lived, and where energy goes | `choose`+`for_each`(days, `one_per_screen`) · `distribute` | `map` · `chart:share` |
| Repetições | **O que volta a acontecer**: recurring situations, ranked, and what precedes them | `choose` (multi) · `order` · `write`+`when` | `chart:bars` · `quotes` |
| Desejo e futuro | **O que eu quero e o que me segura**: wishes against what holds them back | `write` · `distribute` · `choose`+`options_from` | `chart:scale` · `session_questions` |
