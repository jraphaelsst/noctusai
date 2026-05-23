import { test, expect } from '../fixtures/auth.fixture';
import { mockTeamAPIs } from '../fixtures/api-mocks';

/**
 * TeamManagement was rewritten to a real <table> + Tailwind modals in the seed
 * migration. The bespoke `.team-page-title` / `.team-page-subtitle` /
 * `.admin-table` / `.badge` / `.modal-content` classes are gone. We use
 * table/role/text semantics. Modals are `fixed inset-0` overlays whose dialog
 * box carries a heading + the action buttons.
 */
test.describe('Team Management', () => {
  test('displays members list with table headers', async ({ authenticatedPage: page }) => {
    await mockTeamAPIs(page);
    await page.goto('/team');

    await expect(page.getByRole('heading', { name: 'Equipe' })).toBeVisible();
    await expect(page.getByText('2 membros na organização')).toBeVisible();

    // Members table (first table on the page) + its column headers.
    const membersTable = page.locator('table').first();
    await expect(membersTable.getByRole('columnheader', { name: 'Nome' })).toBeVisible();
    await expect(membersTable.getByRole('columnheader', { name: 'E-mail' })).toBeVisible();
    await expect(membersTable.getByRole('columnheader', { name: 'Papel' })).toBeVisible();

    await expect(membersTable.getByText('Rafael Oliveira')).toBeVisible();
    await expect(membersTable.getByText('Mariana Lima')).toBeVisible();
  });

  test('shows "Você" badge next to current user', async ({ authenticatedPage: page }) => {
    await mockTeamAPIs(page);
    await page.goto('/team');

    // The current user's row (Rafael, id user-001) carries the "Você" badge.
    const ownerRow = page.getByRole('row', { name: /Rafael Oliveira/ });
    await expect(ownerRow.getByText('Você')).toBeVisible();
  });

  test('opens invite modal and submits invite', async ({ authenticatedPage: page }) => {
    await mockTeamAPIs(page);
    await page.goto('/team');

    await page.getByRole('button', { name: 'Convidar' }).click();

    // Modal heading + email field.
    await expect(page.getByRole('heading', { name: 'Convidar membro' })).toBeVisible();
    await page.locator('input[type="email"]').fill('novo@empresa.com');

    await page.getByRole('button', { name: 'Enviar convite' }).click();

    // Modal closes — its heading is gone.
    await expect(page.getByRole('heading', { name: 'Convidar membro' })).toHaveCount(0);
  });

  test('shows pending invitations section', async ({ authenticatedPage: page }) => {
    await mockTeamAPIs(page);
    await page.goto('/team');

    await expect(page.getByText('Convites pendentes')).toBeVisible();
    await expect(page.getByText('joao@imobiliaria.com')).toBeVisible();
  });

  test('shows remove confirmation modal for non-owner members', async ({ authenticatedPage: page }) => {
    await mockTeamAPIs(page);
    await page.route('**/api/team/*', (route) => {
      if (route.request().method() === 'DELETE') {
        return route.fulfill({ status: 200, contentType: 'application/json', body: '{"message":"OK"}' });
      }
      return route.continue();
    });
    await page.goto('/team');

    // Mariana (org_role member, not the current user) has a "Remover" action.
    const marianaRow = page.getByRole('row', { name: /Mariana Lima/ });
    await marianaRow.getByRole('button', { name: 'Remover' }).click();

    // Confirm modal heading + name (the modal renders it in a <strong>,
    // distinct from the table cell) + confirm button.
    await expect(page.getByRole('heading', { name: 'Remover membro' })).toBeVisible();
    await expect(page.locator('strong', { hasText: 'Mariana Lima' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Confirmar remoção' })).toBeVisible();
  });
});
