import { test, expect } from '../fixtures/auth.fixture';
import { mockProcessosAPIs } from '../fixtures/api-mocks';
import { mockSupabaseQueries } from '../fixtures/supabase-mocks';

test.describe('Processos de Venda (post-proposal execution board)', () => {
  test('displays all eight execution columns', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockProcessosAPIs(page);
    await page.goto('/processos-venda');

    for (const label of [
      'Elaboração do Contrato',
      'Análise das Partes',
      'Revisão do Contrato',
      'Assinatura',
      'Financiamento & Escritura',
      'Finalização',
      'Entrega das Chaves',
      'Nota Fiscal',
    ]) {
      await expect(page.getByRole('heading', { name: label })).toBeVisible();
    }
  });

  test('shows processo cards in their stage columns', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockProcessosAPIs(page);
    await page.goto('/processos-venda');

    await expect(page.getByText('Maria Ferreira')).toBeVisible();
    await expect(page.getByText('Pedro Almeida')).toBeVisible();
  });

  test('has no create button — processos arrive only via the Funil seam', async ({
    authenticatedPage: page,
  }) => {
    await mockSupabaseQueries(page);
    await mockProcessosAPIs(page);
    await page.goto('/processos-venda');

    await expect(page.getByRole('button', { name: /Novo Processo/i })).toHaveCount(0);
  });

  test('dragging a card to another stage persists via the move-etapa API', async ({
    authenticatedPage: page,
  }) => {
    await mockSupabaseQueries(page);
    await mockProcessosAPIs(page);
    await page.goto('/processos-venda');

    // proc-001 starts in "Elaboração do Contrato" (pstage-0); drop onto the
    // ADJACENT "Análise das Partes" (pstage-1). Columns are keyed by STAGE ID
    // now, not by slug — stages are user-editable rows since migration 042, so
    // an id is the only handle a rename cannot break.
    // Deliberately adjacent — dnd-kit auto-scrolls
    // the horizontally-scrollable board near its edges, and a farther column
    // drifts out from under a stationary pointer (the same flake documented
    // in funil.spec.ts).
    const card = page.locator('[data-kanban-card-id="proc-001"]');
    const targetColumn = page.locator('[data-kanban-column-id="pstage-1"]');

    await expect(card).toBeVisible();
    await expect(targetColumn).toBeVisible();

    const cardBox = await card.boundingBox();
    const targetBox = await targetColumn.boundingBox();
    if (!cardBox || !targetBox) throw new Error('Could not measure drag source/target');

    const moveRequest = page.waitForRequest(
      (req) =>
        req.url().includes('/api/processos-venda/proc-001/mover-etapa') &&
        req.method() === 'POST',
    );

    // dnd-kit's PointerSensor needs real incremental pointer moves past its
    // 8px activation distance — a single drag-to jump doesn't fire it.
    const startX = cardBox.x + cardBox.width / 2;
    const startY = cardBox.y + cardBox.height / 2;
    const endX = targetBox.x + targetBox.width / 2;
    const endY = targetBox.y + targetBox.height / 2;

    await page.mouse.move(startX, startY);
    await page.mouse.down();
    await page.mouse.move(startX + 20, startY + 20, { steps: 5 });
    await page.mouse.move(endX, endY, { steps: 15 });
    await page.mouse.up();

    const req = await moveRequest;
    // The payload must carry the stage ID. A slug here would mean the frontend
    // is still thinking in fixed vocabulary, and would 404 on any user-created
    // stage.
    expect(req.postDataJSON()).toMatchObject({ para_etapa_id: 'pstage-1' });
  });
});
