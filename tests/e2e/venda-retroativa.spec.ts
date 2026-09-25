import { test, expect } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";

// Sem porta fixa: a fixture `request` do Playwright resolve caminhos
// relativos contra `use.baseURL` do playwright.config.ts (o dev server do
// frontend), e o vite proxeia /api pro backend (ver frontend/vite.config.ts
// e src/lib/api.ts, que usa a mesma base "/api"). Uma versão anterior deste
// teste apontava direto pro backend com uma porta fixa (8001) que só existia
// num docker-compose.override.yml de bancada — nunca commitado — e por isso
// não rodava na máquina de ninguém além de quem escreveu o teste.
const API = "/api";
const EMAIL = "t@t.com";
const PASSWORD = "pw";

/**
 * Reclamação original: "no momento do clique da venda é que registra quando
 * foi vendido, o correto deveria ser poder colocar uma data para venda."
 * Marcar "Vendido" gravava a data de hoje em silêncio, então uma venda de
 * outro mês caía no mês errado do DRE sem nada na tela pra mostrar isso.
 *
 * Este teste prova o fluxo ponta a ponta:
 *   1. Login pela UI.
 *   2. Garante um material PLA cadastrado (necessário pro gcode resolver
 *      sozinho — reaproveita o padrão de seed via API do happy_path.spec.ts,
 *      mas com o campo certo do schema: `material_type`, não `material_code`.
 *      happy_path usa o nome errado, o POST falha 422 silenciosamente e a
 *      peça fica com material pendente, travando o botão Finalizar — é
 *      exatamente essa armadilha que este teste evita).
 *   3. Cria orçamento comercial, sobe um gcode PLA (resolve sozinho, sem
 *      precisar do modal "Resolver material pendente"), finaliza e aprova.
 *   4. Sincroniza o Contábil via POST /accounting/sync (a aba Vendas não
 *      dispara isso sozinha — só existe o botão "Atualizar", que é leitura).
 *   5. Registra a venda com uma data de dois meses atrás.
 *   6. Confere que a receita aparece no DRE daquele mês (delta bate com o
 *      total do orçamento) e que o DRE do mês corrente não muda nada.
 */
test("venda com data retroativa cai no DRE do mês certo, não no corrente", async ({
  page,
  request,
  context,
}) => {
  const itemName = `Peça retroativa e2e ${Date.now()}`;

  // ---- 1. Login pela UI
  await page.goto("/login");
  await page.fill('input[type="email"]', EMAIL);
  await page.fill('input[type="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/$/);

  const cookies = await context.cookies();
  const cookieHeader = cookies
    .filter((c) => c.domain.includes("localhost") || c.domain.includes("127.0.0.1"))
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");

  // ---- 2. Garante material PLA (o gcode fixture declara "Material Type: PLA")
  const materiaisRes = await request.get(`${API}/materials`, {
    headers: { cookie: cookieHeader },
  });
  const materiais = (await materiaisRes.json()) as { id: string; material_type: string }[];
  let materialPla = materiais.find((m) => m.material_type === "PLA");
  if (!materialPla) {
    const criado = await request.post(`${API}/materials`, {
      headers: { "content-type": "application/json", cookie: cookieHeader },
      data: {
        material_type: "PLA",
        name: "PLA",
        density_g_cm3: "1.24",
        price_per_kg_ref: "100",
        failure_rate_pct: "0",
      },
    });
    expect(criado.ok()).toBe(true);
    materialPla = (await criado.json()) as { id: string; material_type: string };
  }

  // ---- 3. Cria orçamento comercial e sobe o gcode
  await page.goto("/quotes/new");
  await page.locator('input[type="radio"][value="commercial"]').check();
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(/\/quotes\/[0-9a-f-]+/);

  const fixturePath = path.resolve(__dirname, "../fixtures/sample.gcode");
  expect(fs.existsSync(fixturePath)).toBe(true);
  await page.setInputFiles("#itemFile", fixturePath);
  await page.fill('input[placeholder="Ex.: porta-caneta"]', itemName);
  await page.locator('button[type="submit"]', { hasText: /adicionar peça/i }).click();
  await expect(page.locator("td", { hasText: itemName })).toBeVisible({ timeout: 15_000 });

  // Se este ambiente (base compartilhada, sem reset entre specs) já tem mais
  // de um material do tipo PLA cadastrado, o auto-resolve fica ambíguo e a
  // peça nasce com badge "pendente" — resolve explicitamente pelo seletor
  // inline, igual ao padrão de tests/e2e/clone-e-filamento.spec.ts, em vez de
  // depender de o ambiente ter exatamente um PLA cadastrado.
  const itemRow = page.locator("tr", { hasText: itemName });
  if (await itemRow.locator(".badge.pending").count()) {
    await itemRow.locator("select.inline").selectOption(materialPla.id);
  }
  await expect(itemRow.locator(".badge.pending")).toHaveCount(0, { timeout: 10_000 });

  // ---- Finalizar → Aprovar
  await page.locator("button", { hasText: /^Finalizar$/ }).click();
  await expect(page.locator(".tag", { hasText: /orçado/i })).toBeVisible({ timeout: 15_000 });

  await page.locator("button", { hasText: /^Aprovar$/ }).click();
  await expect(page.locator(".tag", { hasText: /aprovado/i })).toBeVisible({ timeout: 15_000 });

  // ---- Helpers de data/mês
  const pad = (n: number) => String(n).padStart(2, "0");
  const iso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  function parseMoney(txt: string): number {
    const limpo = txt.replace(/[^\d,.-]/g, "").replace(/\.(?=\d{3}(?:\D|$))/g, "").replace(",", ".");
    return parseFloat(limpo) || 0;
  }

  const hoje = new Date();
  const inicioMesAtual = new Date(hoje.getFullYear(), hoje.getMonth(), 1);
  const alvo = new Date(hoje.getFullYear(), hoje.getMonth() - 2, 1);
  const fimAlvo = new Date(alvo.getFullYear(), alvo.getMonth() + 1, 0);
  const soldAt = iso(new Date(alvo.getFullYear(), alvo.getMonth(), 15));

  const receitaBruta = page.locator(
    'section[aria-label="Demonstrativo de resultado"] .line.revenue dd',
  );
  // O <dd> não desmonta entre recargas — dre.data velho continua visível
  // enquanto a nova busca está em voo (guarda do template é `{:else if
  // $dre.data}`, não `{:else if !loading}`). Por isso ler o texto assim que
  // o elemento fica visível é uma corrida: é preciso esperar a resposta da
  // API do período pedido resolver antes de ler o valor.
  async function lerReceitaBruta(periodo?: { from: Date; to: Date }): Promise<number> {
    const resposta = page.waitForResponse(
      (r) => r.url().includes("/api/accounting/dre?") && r.request().method() === "GET" && r.ok(),
    );
    if (periodo) {
      await page.getByLabel("De", { exact: true }).fill(iso(periodo.from));
      await page.getByLabel("Até", { exact: true }).fill(iso(periodo.to));
      await page.locator("button.generate").click();
    }
    await resposta;
    await expect(receitaBruta).toBeVisible({ timeout: 15_000 });
    return parseMoney((await receitaBruta.textContent()) ?? "");
  }

  // ---- 4. Abre o Contábil e lê o DRE do mês corrente ANTES de registrar
  // nada — baseline pra provar depois que a venda retroativa não mexeu nele.
  const respostaInicial = page.waitForResponse(
    (r) => r.url().includes("/api/accounting/dre?") && r.request().method() === "GET" && r.ok(),
  );
  await page.goto("/accounting");
  await respostaInicial;
  await page.locator("nav.subtabs button", { hasText: "DRE" }).click();
  await expect(receitaBruta).toBeVisible({ timeout: 15_000 });
  const receitaMesAtualAntes = parseMoney((await receitaBruta.textContent()) ?? "");

  // Lê também o DRE do mês alvo (dois meses atrás) ANTES da venda — outra
  // baseline, pro delta depois não depender do banco estar "limpo".
  const receitaMesAlvoAntes = await lerReceitaBruta({ from: alvo, to: fimAlvo });

  // ---- 5. Sincroniza o Contábil (a aba não faz isso sozinha — só GET, que
  // agora é somente leitura) e atualiza a lista de Vendas.
  const syncRes = await request.post(`${API}/accounting/sync`, {
    headers: { cookie: cookieHeader },
  });
  expect(syncRes.ok()).toBe(true);

  await page.locator("nav.subtabs button", { hasText: "Vendas" }).click();
  await page.locator("button.tiny.ghost", { hasText: /Atualizar/i }).click();

  const linha = page.locator("tr", { has: page.locator("td", { hasText: itemName }) });
  await expect(linha).toBeVisible({ timeout: 15_000 });
  // Colunas mono, na ordem do DOM: quote_seq, quote_total (Total), cpv_calc, sold_at.
  const totalVendaTexto = (await linha.locator("td.mono").nth(1).textContent()) ?? "";
  const totalVenda = parseMoney(totalVendaTexto);
  expect(totalVenda).toBeGreaterThan(0);

  // ---- 6. Registra a venda com data de dois meses atrás
  await linha.locator("button", { hasText: /registrar venda/i }).click();
  const editor = page.getByRole("dialog", { name: "Registrar venda" });
  await expect(editor).toBeVisible();
  await editor.locator('input[type="date"]').fill(soldAt);
  // Avisa que é retroativo — prova que a tela não deixa isso passar batido.
  await expect(editor.locator(".hint.warn")).toBeVisible();
  await editor.locator("button", { hasText: /^salvar$/i }).click();
  await expect(editor).toHaveCount(0);

  // O chip de status em Vendas começa em "a confirmar" (accounting/+page.svelte
  // — passaStatus: !is_sold && !is_stale) — é o que falta faturar, a razão de
  // abrir a aba. Ao registrar a venda o item vira is_sold e sai desse
  // conjunto por decisão de produto, não por bug: troca pra "vendidos" pra
  // continuar enxergando a linha.
  await page
    .getByRole("group", { name: "Filtrar por status" })
    .getByRole("button", { name: "vendidos", exact: true })
    .click();

  const linhaVendida = page.locator("tr", { has: page.locator("td", { hasText: itemName }) });
  await expect(linhaVendida.locator(".sale-done")).toBeVisible({ timeout: 15_000 });
  await expect(linhaVendida.locator(".sale-done")).toContainText(soldAt.split("-").reverse().join("/"));

  // ---- 7. DRE do mês alvo: a receita subiu exatamente o valor da venda
  await page.locator("nav.subtabs button", { hasText: "DRE" }).click();
  const receitaMesAlvoDepois = await lerReceitaBruta({ from: alvo, to: fimAlvo });
  expect(receitaMesAlvoDepois - receitaMesAlvoAntes).toBeCloseTo(totalVenda, 2);

  // ---- 8. DRE do mês corrente: nada mudou — a venda NÃO caiu aqui
  const receitaMesAtualDepois = await lerReceitaBruta({ from: inicioMesAtual, to: hoje });
  expect(receitaMesAtualDepois).toBeCloseTo(receitaMesAtualAntes, 2);
});
