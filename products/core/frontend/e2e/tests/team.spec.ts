import { test, expect } from '../fixtures/auth.fixture';
import { mockTeamAPIs } from '../fixtures/api-mocks';

test.describe('Team Management', () => {
  test('displays members list with table headers', async ({ authenticatedPage: page }) => {
    await mockTeamAPIs(page);
    await page.goto('/team');

    await expect(page.locator('.team-page-title')).toContainText('Equipe');
    await expect(page.locator('.team-page-subtitle')).toContainText('2 membros');

    // Table headers (first table = members table)
    const membersTable = page.locator('.admin-table').first();
    await expect(membersTable.getByRole('columnheader', { name: 'Nome' })).toBeVisible();
    await expect(membersTable.getByRole('columnheader', { name: 'E-mail' })).toBeVisible();
    await expect(membersTable.getByRole('columnheader', { name: 'Papel' })).toBeVisible();

    // Member rows (scope to table body)
    await expect(membersTable.getByText('Rafael Oliveira')).toBeVisible();
    await expect(membersTable.getByText('Mariana Lima')).toBeVisible();
  });

  test('shows "Você" badge next to current user', async ({ authenticatedPage: page }) => {
    await mockTeamAPIs(page);
    await page.goto('/team');

    const ownerRow = page.locator('tr', { hasText: 'Rafael Oliveira' });
    await expect(ownerRow.locator('.badge', { hasText: 'Você' })).toBeVisible();
  });

  test('opens invite modal and submits invite', async ({ authenticatedPage: page }) => {
    await mockTeamAPIs(page);
    await page.goto('/team');

    await page.getByText('Convidar').click();

    // Modal should be visible
    await expect(page.locator('.modal-content')).toBeVisible();
    await expect(page.locator('.modal-content h2')).toContainText('Convidar membro');

    // Fill in the email
    await page.locator('.modal-content input[type="email"]').fill('novo@empresa.com');

    // Submit
    await page.getByText('Enviar convite').click();

    // Modal should close
    await expect(page.locator('.modal-content')).toHaveCount(0);
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

    // The remove button should be present for Mariana (non-owner, not current user)
    const marianaRow = page.locator('tr', { hasText: 'Mariana Lima' });
    await marianaRow.getByText('Remover').click();

    // Confirm modal
    await expect(page.locator('.modal-content')).toBeVisible();
    await expect(page.locator('.modal-content h2')).toContainText('Remover membro');
    await expect(page.locator('.modal-content strong')).toContainText('Mariana Lima');
    await expect(page.getByText('Confirmar remoção')).toBeVisible();
  });
});
