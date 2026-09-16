/**
 * Edição de Fotos — SW wiring over the seed `createEdicaoFotosHooks` factory
 * (`@noctusai/lib/photo-editing/hooks`, `projects/edicao-fotos/
 * EDICAO-FOTOS-CONTRACT.md`). Same shape as `useNotificacoes.ts` wiring
 * `createNotificationHooks`: the seed factory owns every fetch/loading-state
 * rule, this file only supplies the product's own authenticated `api`
 * client (`@noctusai/seed/infra`) — zero feature logic lives here, so the
 * engine stays portable to the owner's phase-2 standalone rebuild.
 *
 * `pages/edicao-fotos/*` import hooks from HERE, never straight from the
 * seed module — keeps a single SW-local seam if the wiring ever needs a
 * product-specific addition (per `check_canonical_organ_consumption`, a
 * declared extension of the canonical organ, not a fork).
 */
import { createEdicaoFotosHooks } from '@noctusai/lib/photo-editing/hooks';
import { api } from '@noctusai/seed/infra';

export const {
  useCapacidades,
  useRevisao,
  useDecidirFoto,
  useRetentarFoto,
  useReferencias,
  useCriarReferencia,
  useArquivarReferencia,
  useGuias,
  useCriarGuia,
  useAtivarGuia,
  useRestaurarGuia,
  useRegenerarGuia,
  useRegras,
  useCriarRegra,
  useEditarRegra,
  useAprovarRegra,
  useRejeitarRegra,
  useProporRegrasAgora,
  useGuiaEfetivo,
  useConfiguracoesPlataforma,
  useAtualizarConfiguracoesPlataforma,
  useLotes,
  useLote,
  useCriarLote,
  useUploadFotos,
  useLoteVista,
  useSubmeterLote,
  useBaixarZip,
  useConfiguracoes,
  useAtualizarConfiguracoes,
  useModelos,
} = createEdicaoFotosHooks(api);

export type {
  Capacidades,
  EstadoFoto,
  DecisaoTipo,
  AvaliacaoIA,
  FotoRevisao,
  DecisaoBody,
  ReferenciaPar,
  NovaReferenciaBody,
  PoolReferencias,
  ReferenciasPage,
  GuiaStatus,
  GuiaOrigem,
  GuiaEstiloVersao,
  GuiasPage,
  NovoGuiaBody,
  RegenerarGuiaResposta,
  RegraStatus,
  RegraOrg,
  RegrasPage,
  NovaRegraBody,
  ProporRegrasResposta,
  GuiaEfetivo,
  GuiaEfetivoView,
  PlataformaConfiguracoes,
  LoteVelocidade,
  LoteImovelRef,
  EstadoLoteAgregado,
  LoteResumo,
  LotesPage,
  NovoLoteBody,
  LoteCriado,
  VistaLoteBody,
  LoteDetalhe,
  OrgConfiguracoes,
  ModeloCatalogoItem,
} from '@noctusai/lib/photo-editing/hooks';

export * as fotosPermissions from '@noctusai/lib/photo-editing/permissions';
