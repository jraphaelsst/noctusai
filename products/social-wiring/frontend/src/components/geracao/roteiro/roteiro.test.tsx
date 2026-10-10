/**
 * RoteiroAvancadoModal + EditarRoteiroModal + Roteiros page (contract §7.8).
 * API hooks are mocked; no network. VideoPicker is FE-2's component — mocked
 * here with the agreed props `{marcaId, value, onChange}`.
 */
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

afterEach(cleanup);

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/hooks/geracao/useEsteira", () => ({
  useCriarPost: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useVincularRoteiro: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock("@/components/geracao/biblioteca/VideoPicker", () => ({
  VideoPicker: (p: { marcaId: string; value: string | null; onChange: (v: string | null) => void }) => (
    <button type="button" data-testid="video-picker" onClick={() => p.onChange("viral-9")}>
      Abrir biblioteca e escolher vídeo ({p.marcaId}/{String(p.value)})
    </button>
  ),
}));

const m = {
  marcas: vi.fn(),
  brains: vi.fn(),
  lista: vi.fn(),
  roteiro: vi.fn(),
  criar: vi.fn(),
  responder: vi.fn(),
  gerar: vi.fn(),
  salvar: vi.fn(),
  feedback: vi.fn(),
  reprocessar: vi.fn(),
  excluir: vi.fn(),
};

vi.mock("@/hooks/useMarcas", () => ({ useMarcas: () => m.marcas() }));
vi.mock("@/hooks/useCerebro", () => ({ useCerebroBrains: (id: unknown) => m.brains(id) }));
vi.mock("@/hooks/geracao/useRoteiros", () => ({
  ROTEIROS_PAGE_SIZE: 20,
  useRoteiros: (...a: unknown[]) => m.lista(...a),
  useRoteiro: (id: unknown) => m.roteiro(id),
  useCriarRoteiro: () => ({ mutateAsync: m.criar, isPending: false }),
  useResponderPerguntas: () => ({ mutateAsync: m.responder, isPending: false }),
  useGerarRoteiro: () => ({ mutateAsync: m.gerar, isPending: false }),
  useSalvarRoteiro: () => ({ mutateAsync: m.salvar, isPending: false }),
  useFeedbackRoteiro: () => ({ mutateAsync: m.feedback, isPending: false }),
  useReprocessarRoteiro: () => ({ mutateAsync: m.reprocessar, isPending: false }),
  useExcluirRoteiros: () => ({ mutateAsync: m.excluir, isPending: false }),
}));

import { EditarRoteiroModal } from "./EditarRoteiroModal";
import { RoteiroAvancadoModal } from "./RoteiroAvancadoModal";
import Roteiros from "@/pages/geracao/Roteiros";

const base = {
  id: "r1",
  nome: "Roteiro: 3 alimentos",
  headline_texto: "3 alimentos",
  headline_id: "h1",
  status: "completo",
  created_at: "2026-10-01T12:00:00Z",
  instrucoes: "",
  fonte: "ia",
  duracao: "auto",
  brain_id: null,
  viral: null,
  perguntas: [],
  etapa: null,
  conteudo: "# Roteiro\ntexto",
  fontes: null,
  versao: 1,
  feedback: null,
  feedback_motivo: null,
  erro: null,
};
const q = (data: unknown, extra: Record<string, unknown> = {}) => ({
  data,
  showSkeleton: false,
  isRefreshing: false,
  isError: false,
  refetch: vi.fn(),
  ...extra,
});

beforeEach(() => {
  Object.values(m).forEach((f) => f.mockReset());
  m.marcas.mockReturnValue({ data: [{ id: "m1", name: "Marca 1" }] });
  m.brains.mockReturnValue(
    q([
      { id: "b1", name: "Método", content_chars: 500 },
      { id: "b2", name: "Vazio", content_chars: 0 },
    ]),
  );
  m.roteiro.mockReturnValue(q(undefined));
});

describe("RoteiroAvancadoModal", () => {
  function abrir(props: Partial<React.ComponentProps<typeof RoteiroAvancadoModal>> = {}) {
    return render(<RoteiroAvancadoModal open onOpenChange={vi.fn()} marcaId="m1" {...props} />);
  }

  it("fontes: só 'Deixe a IA pensar' habilitada; web/link desabilitadas com 'Em breve'", () => {
    abrir();
    expect(screen.getByRole("button", { name: /Deixe a IA pensar/ })).not.toBeDisabled();
    expect(screen.getByRole("button", { name: /Pesquisar na web/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Link específico/ })).toBeDisabled();
    expect(screen.getAllByText("Em breve")).toHaveLength(2);
  });

  it("prefill da headline e envio com todos os campos (cérebro só com conteúdo, vídeo da biblioteca)", async () => {
    m.criar.mockResolvedValue({ ...base, status: "criando" });
    const onCriado = vi.fn();
    abrir({ headlineInicial: { id: "h1", texto: "3 alimentos" }, onCriado });
    expect(screen.getByLabelText("Headline")).toHaveValue("3 alimentos");
    expect(screen.queryByRole("option", { name: "Vazio" })).toBeNull();
    fireEvent.change(screen.getByLabelText(/Segundo Cérebro/), { target: { value: "b1" } });
    fireEvent.click(screen.getByRole("radio", { name: "~2 min" }));
    fireEvent.click(screen.getByTestId("video-picker"));
    fireEvent.change(screen.getByLabelText("Instruções"), { target: { value: "tom leve" } });
    fireEvent.click(screen.getByRole("button", { name: "Criar roteiro" }));
    await waitFor(() => expect(m.criar).toHaveBeenCalled());
    expect(m.criar).toHaveBeenCalledWith({
      marca_id: "m1",
      headline_id: "h1",
      headline_texto: "3 alimentos",
      instrucoes: "tom leve",
      fonte: "ia",
      duracao: "2",
      brain_id: "b1",
      viral_id: "viral-9",
      gerar_perguntas: true,
    });
    await waitFor(() => expect(onCriado).toHaveBeenCalled());
  });

  it("headline editada deixa de apontar para a headline original; vazio bloqueia o envio", () => {
    abrir({ headlineInicial: { id: "h1", texto: "3 alimentos" } });
    fireEvent.change(screen.getByLabelText("Headline"), { target: { value: "" } });
    expect(screen.getByRole("button", { name: "Criar roteiro" })).toBeDisabled();
  });

  it("usa o status real: criando mostra a etapa do servidor, sem barra de progresso", async () => {
    m.criar.mockResolvedValue({ ...base, status: "criando" });
    abrir({ headlineInicial: { texto: "x" } });
    m.roteiro.mockReturnValue(q({ ...base, status: "criando", etapa: "Analisando a headline" }));
    fireEvent.click(screen.getByRole("button", { name: "Criar roteiro" }));
    await screen.findByText("Analisando a headline");
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("perguntas: responde e gera; pular perguntas gera sem respostas", async () => {
    m.criar.mockResolvedValue({ ...base, status: "criando" });
    m.responder.mockResolvedValue({});
    m.gerar.mockResolvedValue({});
    abrir({ headlineInicial: { texto: "x" } });
    m.roteiro.mockReturnValue(
      q({ ...base, status: "perguntas", perguntas: [{ id: "p1", pergunta: "Qual o público?", resposta: null }] }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Criar roteiro" }));
    const campo = await screen.findByLabelText("Qual o público?");
    fireEvent.change(campo, { target: { value: "iniciantes" } });
    fireEvent.click(screen.getByRole("button", { name: "Gerar Roteiro" }));
    await waitFor(() => expect(m.gerar).toHaveBeenCalledWith({ id: "r1" }));
    expect(m.responder).toHaveBeenCalledWith({ id: "r1", respostas: [{ id: "p1", resposta: "iniciantes" }] });
    fireEvent.click(screen.getByRole("button", { name: "Pular perguntas" }));
    await waitFor(() => expect(m.gerar).toHaveBeenCalledWith({ id: "r1", pular_perguntas: true }));
  });

  it("falha: mostra o erro e 'Tentar novamente' volta ao formulário preservando os campos", async () => {
    m.criar.mockResolvedValue({ ...base, status: "criando" });
    abrir({ headlineInicial: { texto: "minha headline" } });
    m.roteiro.mockReturnValue(q({ ...base, status: "falha", erro: "Tempo esgotado — tente novamente." }));
    fireEvent.click(screen.getByRole("button", { name: "Criar roteiro" }));
    await screen.findByText("Tempo esgotado — tente novamente.");
    fireEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(await screen.findByLabelText("Headline")).toHaveValue("minha headline");
  });

  it("criado: sucesso, edição, Atualizar Roteiro (#37) e bloco Gostei/Não Gostei", async () => {
    m.criar.mockResolvedValue({ ...base, status: "criando" });
    m.salvar.mockResolvedValue({ ...base, versao: 2 });
    abrir({ headlineInicial: { texto: "x" } });
    m.roteiro.mockReturnValue(q({ ...base }));
    fireEvent.click(screen.getByRole("button", { name: "Criar roteiro" }));
    await screen.findByText("Roteiro criado com sucesso!");
    expect(screen.getByText("O que achou deste roteiro?")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /Fontes/ })).toBeNull();
    const atualizar = screen.getByRole("button", { name: "Atualizar Roteiro" });
    expect(atualizar).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Roteiro"), { target: { value: "editado" } });
    fireEvent.click(atualizar);
    await waitFor(() =>
      expect(m.salvar).toHaveBeenCalledWith({ id: "r1", nome: undefined, conteudo: "editado", expected_versao: 1 }),
    );
  });
});

describe("RoteiroAvancadoModal — postId (Esteira)", () => {
  it("envia post_id no create e mostra 'Vinculado ao post <título>' quando criado", async () => {
    m.criar.mockResolvedValue({ ...base, status: "criando" });
    render(<RoteiroAvancadoModal open onOpenChange={vi.fn()} marcaId="m1" headlineInicial={{ texto: "x" }} postId="p1" />);
    m.roteiro.mockReturnValue(
      q({ ...base, post: { id: "p1", titulo: "Reel do ap", etapa_label: "Roteiro" } }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Criar roteiro" }));
    await waitFor(() => expect(m.criar).toHaveBeenCalledWith(expect.objectContaining({ post_id: "p1" })));
    expect(await screen.findByTestId("roteiro-vinculado")).toHaveTextContent("Vinculado ao post Reel do ap");
  });

  it("sem postId não envia post_id nem mostra o vínculo", async () => {
    m.criar.mockResolvedValue({ ...base, status: "criando" });
    render(<RoteiroAvancadoModal open onOpenChange={vi.fn()} marcaId="m1" headlineInicial={{ texto: "x" }} />);
    m.roteiro.mockReturnValue(q({ ...base }));
    fireEvent.click(screen.getByRole("button", { name: "Criar roteiro" }));
    await screen.findByText("Roteiro criado com sucesso!");
    expect(m.criar.mock.calls[0][0]).not.toHaveProperty("post_id");
    expect(screen.queryByTestId("roteiro-vinculado")).toBeNull();
  });
});

describe("EditarRoteiroModal", () => {
  function abrir() {
    return render(<EditarRoteiroModal open onOpenChange={vi.fn()} roteiroId="r1" />);
  }

  it("skeleton enquanto carrega e erro com Tentar novamente", () => {
    m.roteiro.mockReturnValue(q(undefined, { showSkeleton: true }));
    abrir();
    expect(screen.getByTestId("editar-roteiro-skeleton")).toBeInTheDocument();
    cleanup();
    const refetch = vi.fn();
    m.roteiro.mockReturnValue(q(undefined, { isError: true, refetch }));
    abrir();
    fireEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(refetch).toHaveBeenCalled();
  });

  it("aba Fontes só aparece quando fontes não é NULL", () => {
    m.roteiro.mockReturnValue(q({ ...base, fontes: "Fonte A" }));
    abrir();
    expect(screen.getByRole("tab", { name: "Fontes da Pesquisa" })).toBeInTheDocument();
  });

  it("Atualizar com 409 mostra 'O roteiro mudou; recarregue'", async () => {
    m.roteiro.mockReturnValue(q({ ...base }));
    m.salvar.mockRejectedValue(Object.assign(new Error("[409] conflito"), { status: 409 }));
    abrir();
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Novo nome" } });
    fireEvent.click(screen.getByRole("button", { name: "Atualizar" }));
    await screen.findByText("O roteiro mudou; recarregue");
  });

  it("Gostei envia direto; Não Gostei pede o motivo e envia", async () => {
    m.roteiro.mockReturnValue(q({ ...base }));
    m.feedback.mockResolvedValue({});
    abrir();
    fireEvent.click(screen.getByRole("button", { name: /^Gostei/ }));
    await waitFor(() => expect(m.feedback).toHaveBeenCalledWith({ id: "r1", feedback: "gostei", motivo: undefined }));
    fireEvent.click(screen.getByRole("button", { name: /Não Gostei/ }));
    expect(screen.getByText("Não gostou do roteiro?")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Motivo"), { target: { value: "muito longo" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
    await waitFor(() =>
      expect(m.feedback).toHaveBeenCalledWith({ id: "r1", feedback: "nao_gostei", motivo: "muito longo" }),
    );
  });

  it("⋯ Reprocessar abre 'Informação Adicional:' e envia", async () => {
    m.roteiro.mockReturnValue(q({ ...base }));
    m.reprocessar.mockResolvedValue({ ...base, id: "r2" });
    abrir();
    fireEvent.click(screen.getByRole("button", { name: "Mais ações" }));
    fireEvent.click(screen.getByRole("button", { name: /Reprocessar/ }));
    fireEvent.change(await screen.findByLabelText("Informação Adicional:"), { target: { value: "mais curto" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Reprocessar" }).at(-1) as HTMLElement);
    await waitFor(() => expect(m.reprocessar).toHaveBeenCalledWith({ id: "r1", instrucoes_adicionais: "mais curto" }));
  });
});

describe("Roteiros (página)", () => {
  const itens = [
    { id: "r1", nome: "Roteiro A", headline_texto: "H A", headline_id: "h1", status: "completo", created_at: "2026-10-01T12:00:00Z" },
    { id: "r2", nome: "Roteiro B", headline_texto: "H B", headline_id: null, status: "processando", created_at: "2026-10-02T12:00:00Z" },
  ];
  function pagina(rota = "/media-creation/roteiros") {
    return render(
      <MemoryRouter initialEntries={[rota]}>
        <Roteiros />
      </MemoryRouter>,
    );
  }

  it("quatro estados: skeleton, erro, vazio e sucesso", () => {
    m.lista.mockReturnValue(q(undefined, { showSkeleton: true }));
    pagina();
    expect(screen.getByTestId("roteiros-skeleton")).toBeInTheDocument();
    cleanup();
    m.lista.mockReturnValue(q(undefined, { isError: true }));
    pagina();
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
    cleanup();
    m.lista.mockReturnValue(q({ items: [], total: 0 }));
    pagina();
    expect(screen.getByText(/ainda não tem roteiros/)).toBeInTheDocument();
    cleanup();
    m.lista.mockReturnValue(q({ items: itens, total: 2 }));
    pagina();
    expect(screen.getByText("Meus roteiros")).toBeInTheDocument();
    expect(screen.getByText("Completo")).toBeInTheDocument();
    expect(screen.getByText("Processando")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "H A" })).toHaveAttribute(
      "href",
      "/media-creation/headlines/favoritas?hid=h1",
    );
  });

  it("?open= abre o roteiro; Criar roteiro abre o modal avançado vazio", async () => {
    m.lista.mockReturnValue(q({ items: itens, total: 2 }));
    m.roteiro.mockReturnValue(q({ ...base }));
    pagina("/media-creation/roteiros?open=r1");
    expect(await screen.findByText("Editar Roteiro")).toBeInTheDocument();
    cleanup();
    m.roteiro.mockReturnValue(q(undefined));
    pagina();
    fireEvent.click(screen.getByRole("button", { name: /Criar roteiro/ }));
    expect(await screen.findByText("Crie um roteiro avançado em 3 passos")).toBeInTheDocument();
    expect(screen.getByLabelText("Headline")).toHaveValue("");
  });

  it("exclui selecionados após confirmação", async () => {
    m.lista.mockReturnValue(q({ items: itens, total: 2 }));
    m.excluir.mockResolvedValue({ excluidos: 2 });
    pagina();
    const excluirSel = screen.getByRole("button", { name: /Excluir Selecionados/ });
    expect(excluirSel).toBeDisabled();
    fireEvent.click(screen.getByLabelText("Selecionar todos"));
    fireEvent.click(excluirSel);
    fireEvent.click(await screen.findByRole("button", { name: "Excluir" }));
    await waitFor(() => expect(m.excluir).toHaveBeenCalledWith(["r1", "r2"]));
  });
});
