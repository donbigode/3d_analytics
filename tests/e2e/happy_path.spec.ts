import { test, expect } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";

const API = "http://localhost:8000";
const EMAIL = "t@t.com";
const PASSWORD = "pw";

/**
 * Happy path:
 *   1. Login through the UI (cookie set in browser).
 *   2. Seed PLA material via the API (re-using browser cookie).
 *   3. Create a commercial quote via the UI.
 *   4. Add a G-code item (upload).
 *   5. Finalize → quote moves to `orcado`.
 *   6. Open the PDF and assert HTTP 200 + `application/pdf`.
 */
test("login → seed material → criar orçamento → finalize → ver pdf", async ({
  page,
  request,
  context,
}) => {
  // ---- 1. Login through the UI
  await page.goto("/login");
  await page.fill('input[type="email"]', EMAIL);
  await page.fill('input[type="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/$/);

  // ---- 2. Seed PLA material via API. Reuse the browser cookie so we are authed.
  const cookies = await context.cookies();
  const cookieHeader = cookies
    .filter((c) => c.domain.includes("localhost") || c.domain.includes("127.0.0.1"))
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");

  await request.post(`${API}/materials`, {
    headers: { "content-type": "application/json", cookie: cookieHeader },
    data: {
      material_code: "PLA",
      name: "PLA",
      density_g_cm3: "1.24",
      price_per_kg_ref: "100",
      failure_rate_pct: "0",
    },
    failOnStatusCode: false, // ok if it already exists
  });

  // ---- 3. Create a commercial quote via the UI
  await page.goto("/quotes/new");
  await page.locator('input[type="radio"][value="commercial"]').check();
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(/\/quotes\/[0-9a-f-]+/);

  // Grab the quote id from the URL
  const url = new URL(page.url());
  const quoteId = url.pathname.split("/").pop();
  expect(quoteId).toBeTruthy();

  // ---- 4. Upload a g-code item
  const fixturePath = path.resolve(__dirname, "../fixtures/sample.gcode");
  expect(fs.existsSync(fixturePath)).toBe(true);
  await page.setInputFiles("#itemFile", fixturePath);
  await page.fill('input[placeholder="Ex.: porta-caneta"]', "Peça e2e");
  await page.locator('button[type="submit"]', { hasText: /adicionar peça/i }).click();

  await expect(page.locator("td", { hasText: "Peça e2e" })).toBeVisible({
    timeout: 15_000,
  });

  // ---- 5. Finalize the quote
  await page.locator("button", { hasText: /^Finalizar$/ }).click();
  await expect(page.locator(".tag.brand", { hasText: /orçado/i })).toBeVisible({
    timeout: 15_000,
  });

  // ---- 6. Open the PDF and verify
  const pdfRes = await request.get(`${API}/quotes/${quoteId}/pdf`, {
    headers: { cookie: cookieHeader },
  });
  expect(pdfRes.status()).toBe(200);
  expect(pdfRes.headers()["content-type"] ?? "").toContain("application/pdf");
  const body = await pdfRes.body();
  expect(body.byteLength).toBeGreaterThan(100);
});
