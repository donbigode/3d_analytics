import { test, expect, type Page, type BrowserContext } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";

const API = "http://localhost:8000";
const EMAIL = "t@t.com";
const PASSWORD = "pw";

// Mesmas credenciais e padrão de login de tests/e2e/happy_path.spec.ts e
// tests/e2e/mobile.spec.ts — reaproveitado em vez de reinventado.
async function login(page: Page) {
  await page.goto("/login");
  await page.fill('input[type="email"]', EMAIL);
  await page.fill('input[type="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/$/);
}

// Cookie do browser reaproveitado nas chamadas diretas à API (seed de
// material/bobina, transição "complete"), igual ao happy_path.
async function cookieHeader(context: BrowserContext): Promise<string> {
  const cookies = await context.cookies();
  return cookies
    .filter((c) => c.domain.includes("localhost") || c.domain.includes("127.0.0.1"))
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");
}

async function createCommercialQuote(page: Page): Promise<string> {
  await page.goto("/quotes/new");
  await page.locator('input[type="radio"][value="commercial"]').check();
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(/\/quotes\/[0-9a-f-]+/);
  return new URL(page.url()).pathname.split("/").pop()!;
}

async function addGcodeItem(page: Page, name: string) {
  const fixturePath = path.resolve(__dirname, "../fixtures/sample.gcode");
  expect(fs.existsSync(fixturePath)).toBe(true);
  await page.setInputFiles("#itemFile", fixturePath);
  await page.fill('input[placeholder="Ex.: porta-caneta"]', name);
  await page.locator('button[type="submit"]', { hasText: /adicionar peça/i }).click();
  await expect(page.locator("td", { hasText: name })).toBeVisible({ timeout: 15_000 });
}

test.describe("clone de orçamento e painel de filamento", () => {
  test("clonar da lista abre um rascunho com as mesmas peças e número diferente", async ({
    page,
  }) => {
    const runId = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
    const pieceName = `Peça clone ${runId}`;

    await login(page);

    // ---- Orçamento original: rascunho comercial com uma peça (gcode real,
    // pra provar que o clone também copia o arquivo, não só a linha).
    const originalId = await createCommercialQuote(page);
    await addGcodeItem(page, pieceName);

    const originalNumber = (
      await page.locator("header.page-head .page-eyebrow").textContent()
    )?.trim();
    expect(originalNumber).toBeTruthy();

    // ---- Clonar a partir da lista, não da tela do orçamento — é o
    // fluxo que o Otavio pediu ("clonar/replicar um orçamento já existente"
    // direto da lista).
    await page.goto("/quotes");
    const originalRow = page.locator("tr").filter({
      has: page.locator(`span[title="${originalId}"]`),
    });
    await expect(originalRow).toBeVisible();
    await originalRow.locator("button", { hasText: "clonar" }).click();

    // clonarEAbrir() navega pro clone assim que a clonagem termina —
    // copiar gcode/fotos leva um tempo perceptível, daí o timeout largo.
    await expect(page).toHaveURL(/\/quotes\/[0-9a-f-]+/, { timeout: 20_000 });
    const clonedId = new URL(page.url()).pathname.split("/").pop();

    // O que prova que estamos olhando o CLONE e não o original de volta:
    // id diferente e número humano diferente — um teste que só checasse
    // "algum orçamento abriu" passaria mesmo com um clone quebrado que
    // navegasse de volta pro original.
    expect(clonedId).toBeTruthy();
    expect(clonedId).not.toBe(originalId);

    const clonedNumber = (
      await page.locator("header.page-head .page-eyebrow").textContent()
    )?.trim();
    expect(clonedNumber).toBeTruthy();
    expect(clonedNumber).not.toBe(originalNumber);

    // Mesmas peças: a peça (com o gcode) foi copiada.
    await expect(page.locator("td", { hasText: pieceName })).toBeVisible();

    // Clone sempre nasce rascunho, nunca herda status/timeline do original.
    await expect(page.locator(".head-tags .tag", { hasText: /rascunho/i })).toBeVisible();
  });

  test('um orçamento produzido exibe o painel "Filamento consumido" com a bobina', async ({
    page,
    request,
    context,
  }) => {
    const runId = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
    const pieceName = `Peça filamento ${runId}`;
    const materialName = `PLA E2E ${runId}`;
    const spoolManufacturer = `Fábrica E2E ${runId}`;

    await login(page);
    const cookie = await cookieHeader(context);

    // ---- Seed: material PLA (pra resolver a pendência de material da
    // peça) e uma bobina de PLA com estoque, ambos com nome/fabricante
    // únicos pra este teste — a asserção final vai procurar exatamente
    // esse fabricante na tela, não um "PLA" genérico que poderia vir de
    // qualquer outra bobina já cadastrada no ambiente.
    const materialRes = await request.post(`${API}/materials`, {
      headers: { "content-type": "application/json", cookie },
      data: {
        material_type: "PLA",
        name: materialName,
        density_g_cm3: "1.24",
        price_per_kg_ref: "100",
        failure_rate_pct: "0",
      },
    });
    expect(materialRes.ok()).toBe(true);
    const material = await materialRes.json();

    const spoolRes = await request.post(`${API}/spools`, {
      headers: { "content-type": "application/json", cookie },
      data: {
        material_type: "PLA",
        manufacturer: spoolManufacturer,
        purchased_at: new Date().toISOString(),
        purchased_price: "100",
        initial_grams: "1000",
        remaining_grams: "1000",
      },
    });
    expect(spoolRes.ok()).toBe(true);
    const spool = await spoolRes.json();

    // ---- Orçamento comercial com uma peça de gcode (declara material PLA
    // — ver tests/fixtures/sample.gcode).
    const quoteId = await createCommercialQuote(page);
    await addGcodeItem(page, pieceName);

    // ---- Resolve a pendência de material escolhendo o material acima no
    // seletor inline da peça (funciona independente de o auto-resolve do
    // backend ter conseguido casar sozinho ou não — ver task-7-brief.md:
    // o guard de "material pendente" bloqueia finalize/produce e não é
    // desta tarefa consertar, só contornar no setup).
    const itemRow = page.locator("tr", { hasText: pieceName });
    await itemRow.locator("select.inline").selectOption(material.id);
    await expect(itemRow.locator(".badge.pending")).toHaveCount(0, { timeout: 10_000 });

    // ---- Finalizar → Aprovar → Produzir (atribuindo a bobina seedada).
    await page.locator("button", { hasText: /^Finalizar$/ }).click();
    await expect(page.locator(".head-tags .tag", { hasText: /orçado/i })).toBeVisible({
      timeout: 15_000,
    });

    await page.locator("button", { hasText: /^Aprovar$/ }).click();
    await expect(page.locator(".head-tags .tag", { hasText: /aprovado/i })).toBeVisible({
      timeout: 15_000,
    });

    await page.locator("button", { hasText: /^Produzir/ }).click();
    const modal = page.locator(".modal-backdrop .modal");
    await expect(modal).toBeVisible();
    await modal.locator("table select").selectOption(spool.id);
    await modal.locator("button", { hasText: /confirmar produção/i }).click();
    await expect(page.locator(".modal-backdrop")).toHaveCount(0, { timeout: 15_000 });
    await expect(page.locator(".head-tags .tag", { hasText: /em produção/i })).toBeVisible();

    // Fecha o ciclo de produção via API (tela de Capacidade não é o alvo
    // deste teste) pra chegar em "produzido" de verdade, o status que o
    // painel de filamento existe pra atender.
    const completeRes = await request.post(`${API}/quotes/${quoteId}/transitions/complete`, {
      headers: { "content-type": "application/json", cookie },
      data: {},
    });
    expect(completeRes.ok()).toBe(true);

    await page.reload();
    await expect(page.locator(".head-tags .tag", { hasText: /produzido/i })).toBeVisible();

    // ---- O ponto central do teste: o painel mostra a BOBINA de verdade
    // (fabricante que a gente seedou), não só o polímero que o slicer
    // chutou — era exatamente essa a reclamação original ("depois de
    // fechado, não dá pra ver qual foi o filamento exato usado").
    await expect(page.locator("h2", { hasText: /filamento consumido/i })).toBeVisible();
    const bobinaCell = page.locator("table.fil-table td[title]").first();
    await expect(bobinaCell).toBeVisible();
    await expect(bobinaCell).toContainText("PLA");
    await expect(bobinaCell).toContainText(spoolManufacturer);
  });
});
