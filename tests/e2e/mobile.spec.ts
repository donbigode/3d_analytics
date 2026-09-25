import { test, expect, type Page } from "@playwright/test";

/**
 * Responsivo em telefone: nenhuma rota principal deve rolar horizontalmente
 * num viewport de 390px (telefone comum em pé). A conferência de bancada
 * acontece aqui — quem tira dúvida no balcão olha o celular, não o desktop.
 */
test.use({ viewport: { width: 390, height: 844 } });

// Mesmas credenciais e seletores de tests/e2e/happy_path.spec.ts — reaproveitados
// em vez de reinventados, para não divergir do fluxo de login já validado.
const EMAIL = "t@t.com";
const PASSWORD = "pw";

async function login(page: Page) {
  await page.goto("/login");
  await page.fill('input[type="email"]', EMAIL);
  await page.fill('input[type="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/$/);
}

for (const rota of ["/quotes", "/accounting", "/spools", "/clients"]) {
  test(`${rota} não rola horizontalmente em 390px`, async ({ page }) => {
    await login(page);
    await page.goto(rota);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
}
