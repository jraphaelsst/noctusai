import { test, expect } from '../fixtures/auth.fixture';
import {
  mockMailchimpConnectionConnected,
  mockMailchimpCampaigns,
  mockMailchimpSegments,
  mockMailchimpTemplates,
} from '../fixtures/mailchimp';

test.describe('Campanhas', () => {
  test('table renders campaign titles and status badges', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpCampaigns(page);
    await mockMailchimpSegments(page);
    await mockMailchimpTemplates(page);
    await page.goto('/email-marketing/campanhas');

    await expect(page.getByTestId('campanhas-table')).toBeVisible();
    await expect(page.getByText('Campanha Junho')).toBeVisible();
    await expect(page.getByText('Newsletter Maio')).toBeVisible();
  });

  test('draft campaign shows status badge "Rascunho"', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpCampaigns(page);
    await mockMailchimpSegments(page);
    await mockMailchimpTemplates(page);
    await page.goto('/email-marketing/campanhas');

    await expect(page.getByTestId('status-badge-camp-001')).toContainText('Rascunho');
  });

  test('sent campaign shows status badge "Enviada"', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpCampaigns(page);
    await mockMailchimpSegments(page);
    await mockMailchimpTemplates(page);
    await page.goto('/email-marketing/campanhas');

    await expect(page.getByTestId('status-badge-camp-002')).toContainText('Enviada');
  });

  test('sent campaign shows archive link', async ({ authenticatedPage: page }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpCampaigns(page);
    await mockMailchimpSegments(page);
    await mockMailchimpTemplates(page);
    await page.goto('/email-marketing/campanhas');

    const archiveLink = page.getByTestId('archive-url-camp-002');
    await expect(archiveLink).toBeVisible();
    await expect(archiveLink).toHaveAttribute('href', 'https://mailchi.mp/exemplo/newsletter-maio');
  });

  test('draft campaign → Enviar confirm → action endpoint called', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpCampaigns(page);
    await mockMailchimpSegments(page);
    await mockMailchimpTemplates(page);
    await page.goto('/email-marketing/campanhas');

    await page.getByTestId('send-btn-camp-001').click();
    await expect(page.getByTestId('confirm-send-campanha')).toBeVisible();

    const requestPromise = page.waitForRequest(
      /\/api\/mailchimp\/campaigns\/camp-001\/actions\/send/,
    );
    await page.getByTestId('confirm-send-campanha').click();
    const req = await requestPromise;

    expect(req.method()).toBe('POST');
  });

  test('Agendar picker opens and fires schedule action', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpCampaigns(page);
    await mockMailchimpSegments(page);
    await mockMailchimpTemplates(page);
    await page.goto('/email-marketing/campanhas');

    await page.getByTestId('schedule-btn-camp-001').click();
    await expect(page.getByTestId('schedule-modal')).toBeVisible();
    await expect(page.getByTestId('schedule-time-input')).toBeVisible();

    const requestPromise = page.waitForRequest(
      /\/api\/mailchimp\/campaigns\/camp-001\/actions\/schedule/,
    );
    await page.getByTestId('schedule-submit').click();
    const req = await requestPromise;

    expect(req.method()).toBe('POST');
  });

  test('"Nova campanha" modal has required fields', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpCampaigns(page);
    await mockMailchimpSegments(page);
    await mockMailchimpTemplates(page);
    await page.goto('/email-marketing/campanhas');

    await page.getByTestId('btn-nova-campanha').click();
    await expect(page.getByTestId('create-campanha-modal')).toBeVisible();
    await expect(page.getByTestId('create-campanha-submit')).toBeDisabled();

    await page.getByTestId('campanha-title-input').fill('Minha Campanha');
    await page.getByTestId('campanha-subject-input').fill('Assunto da campanha');
    await page.getByTestId('campanha-from-input').fill('Social Wiring');
    await page.getByTestId('campanha-reply-input').fill('reply@social.com');

    await expect(page.getByTestId('create-campanha-submit')).toBeEnabled();
  });

  test('create campaign fires POST request', async ({ authenticatedPage: page }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpCampaigns(page);
    await mockMailchimpSegments(page);
    await mockMailchimpTemplates(page);
    await page.goto('/email-marketing/campanhas');

    await page.getByTestId('btn-nova-campanha').click();
    await page.getByTestId('campanha-title-input').fill('Test Campaign');
    await page.getByTestId('campanha-subject-input').fill('Test Subject');
    await page.getByTestId('campanha-from-input').fill('Social Wiring');
    await page.getByTestId('campanha-reply-input').fill('reply@social.com');

    const requestPromise = page.waitForRequest(/\/api\/mailchimp\/campaigns(\?.*)?$/);
    await page.getByTestId('create-campanha-submit').click();
    const req = await requestPromise;

    expect(req.method()).toBe('POST');
  });
});
