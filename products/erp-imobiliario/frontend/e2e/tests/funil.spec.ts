import { test, expect } from '../fixtures/auth.fixture';
import { mockFunilAPIs, mockClientesAPIs } from '../fixtures/api-mocks';
import { mockSupabaseQueries } from '../fixtures/supabase-mocks';

test.describe('Funil (Sales Pipeline)', () => {
  test('displays kanban columns', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockFunilAPIs(page);
    await mockClientesAPIs(page);
    await page.goto('/funil');

    // ETAPAS_CONFIG labels: Qualificação, Visitas, Proposta, Negociação, Fechado
    await expect(page.getByRole('heading', { name: 'Qualificação' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Proposta' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Negociação' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Visitas' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Fechado' })).toBeVisible();
  });

  test('shows client cards in correct columns', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockFunilAPIs(page);
    await mockClientesAPIs(page);
    await page.goto('/funil');

    await expect(page.getByText('João Santos')).toBeVisible();
    await expect(page.getByText('Maria Ferreira')).toBeVisible();
    await expect(page.getByText('Pedro Almeida')).toBeVisible();
  });

  test('has "Novo Cliente" button', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockFunilAPIs(page);
    await mockClientesAPIs(page);
    await page.goto('/funil');

    await expect(page.getByText('Novo Cliente')).toBeVisible();
  });

  test('"Novo Cliente" button opens dialog', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockFunilAPIs(page);
    await mockClientesAPIs(page);
    await page.goto('/funil');

    await page.getByText('Novo Cliente').click();
    await expect(page.getByRole('dialog')).toBeVisible();
  });

  test('dragging a card to another stage persists via the move-etapa API', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockFunilAPIs(page);
    await mockClientesAPIs(page);
    await page.goto('/funil');

    // neg-001 (João Santos) starts in "qualificacao"; drop it onto the
    // immediately-ADJACENT "proposta" column (mockFunilColunas in
    // e2e/fixtures/mock-data.ts) — a real cross-column move, the KanbanBoard
    // organ's core behavior guarantee. Deliberately NOT targeting a farther
    // column: dnd-kit auto-scrolls the horizontally-scrollable board when the
    // pointer nears the container's edge, and a column near that edge
    // (e.g. "negociacao") drifts out from under a stationary pointer while
    // the container auto-scrolls — an observed flake unrelated to the organ
    // repoint itself, worth a `NOC-REMEDIATE` note if this pattern recurs in
    // other kanban-consumer e2e specs.
    const card = page.locator('[data-kanban-card-id="neg-001"]');
    const targetColumn = page.locator('[data-kanban-column-id="proposta"]');

    await expect(card).toBeVisible();
    await expect(targetColumn).toBeVisible();

    const cardBox = await card.boundingBox();
    const targetBox = await targetColumn.boundingBox();
    if (!cardBox || !targetBox) throw new Error('Could not measure drag source/target');

    const moveRequest = page.waitForRequest(
      (req) => req.url().includes('/api/negociacoes-venda/neg-001/mover-etapa') && req.method() === 'POST',
    );

    // dnd-kit's PointerSensor needs real incremental pointer moves past its
    // activation distance (8px) — a single drag-to jump doesn't fire it.
    const startX = cardBox.x + cardBox.width / 2;
    const startY = cardBox.y + cardBox.height / 2;
    const endX = targetBox.x + targetBox.width / 2;
    const endY = targetBox.y + targetBox.height / 2;

    await page.mouse.move(startX, startY);
    await page.mouse.down();
    await page.mouse.move(startX + 20, startY + 20, { steps: 5 });
    await page.mouse.move(endX, endY, { steps: 15 });
    await page.mouse.up();

    const request = await moveRequest;
    const body = request.postDataJSON();
    expect(body.para_etapa).toBe('proposta');
  });
});

test.describe('Funil — Aceitar Proposta seam', () => {
  test('the button appears ONLY on cards in the proposta column', async ({
    authenticatedPage: page,
  }) => {
    await mockSupabaseQueries(page);
    await mockFunilAPIs(page);
    await mockClientesAPIs(page);
    await page.goto('/funil');

    // neg-002 (Maria Ferreira) sits in "proposta" — it gets the button.
    const propostaCard = page.locator('[data-kanban-card-id="neg-002"]');
    await expect(propostaCard.getByRole('button', { name: /Aceitar Proposta/i })).toBeVisible();

    // neg-001 sits in "qualificacao" — accepting is what ENDS a negotiation,
    // so it must not be offered where no proposal is on the table.
    const qualificacaoCard = page.locator('[data-kanban-card-id="neg-001"]');
    await expect(
      qualificacaoCard.getByRole('button', { name: /Aceitar Proposta/i }),
    ).toHaveCount(0);

    // `fechado` is a Funil-INTERNAL terminal column, explicitly NOT the trigger.
    const fechadoCard = page.locator('[data-kanban-card-id="neg-003"]');
    await expect(
      fechadoCard.getByRole('button', { name: /Aceitar Proposta/i }),
    ).toHaveCount(0);
  });

  test('clicking Aceitar Proposta calls the seam and does not start a drag', async ({
    authenticatedPage: page,
  }) => {
    await mockSupabaseQueries(page);
    await mockFunilAPIs(page);
    await mockClientesAPIs(page);
    await page.goto('/funil');

    const acceptRequest = page.waitForRequest(
      (req) =>
        req.url().includes('/api/negociacoes-venda/neg-002/aceitar-proposta') &&
        req.method() === 'POST',
    );

    // The card body carries the organ's dnd-kit drag listeners; without
    // `e.stopPropagation()` in the handler this click is swallowed as a drag
    // start and no request is ever made. This test is that guarantee.
    await page
      .locator('[data-kanban-card-id="neg-002"]')
      .getByRole('button', { name: /Aceitar Proposta/i })
      .click();

    await acceptRequest;
  });
});
