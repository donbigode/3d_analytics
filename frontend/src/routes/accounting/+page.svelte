<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { get } from "svelte/store";
  import { api } from "$lib/api";
  import { requireAuth } from "$lib/guard";
  import { resource, action } from "$lib/resource";
  import { money, date as fmtDate } from "$lib/format";
  import Table from "$lib/components/Table.svelte";
  import Form from "$lib/components/Form.svelte";
  import SaleEditor from "$lib/components/SaleEditor.svelte";
  import SearchBar from "$lib/components/SearchBar.svelte";
  import { countShown } from "$lib/table-search";
  import { quoteNumber } from "$lib/quote-number";
  import type {
    Sale,
    Expense,
    Dre,
    ExpenseCategory,
    MonthlyDre,
    Profitability,
  } from "$lib/types";

  let tab: "vendas" | "pessoal" | "despesas" | "dre" | "lucratividade" = "vendas";
  let dreMode: "periodo" | "mensal" = "periodo";

  // Vendas é só comercial — pessoal tem sub-aba própria (não é candidato a venda).
  // Antes filtrava is_stale=false na URL; agora a lista traz tudo do tipo e os
  // chips de status (abaixo) filtram na tela — um controle client-side só
  // faz sentido porque o volume aqui é o de um negócio pequeno (dezenas a
  // poucas centenas de orçamentos por ano). Se um dia isso estourar, o chip
  // "arquivados" volta a virar parâmetro de API (?is_stale=).
  const sales = resource(() => api<Sale[]>("/accounting/sales?kind=commercial"), {
    initial: [],
    errorMessage: "Falha ao carregar vendas.",
    auto: false,
  });
  // Uso pessoal: sem filtro de arquivada na URL — o rodapé (e o badge da
  // sub-aba) fazem o próprio filtro em JS, no mesmo critério do teste que
  // trava a consistência com o DRE (test_perda_vs_aba_pessoal.py).
  const personal = resource(() => api<Sale[]>("/accounting/sales?kind=personal"), {
    initial: [],
    errorMessage: "Falha ao carregar uso pessoal.",
    auto: false,
  });
  const saveSale = action(
    (id: string, body: Record<string, unknown>) =>
      api<Sale>(`/accounting/sales/${id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
    { errorMessage: "Falha ao salvar venda." },
  );
  // Id da linha (Vendas ou Uso pessoal) com o popover de registro de venda
  // aberto — só um por vez, compartilhado entre as duas sub-abas.
  let editandoId: string | null = null;

  let exCategory: ExpenseCategory = "maintenance";
  let exDescription = "";
  let exAmount = "";
  let exRecurring = false;
  let exDate = new Date().toISOString().slice(0, 10);

  const expenses = resource(() => api<Expense[]>("/accounting/expenses"), {
    initial: [],
    errorMessage: "Falha ao carregar despesas.",
    auto: false,
  });
  const createExpenseAction = action(
    (body: Record<string, unknown>) =>
      api<Expense>("/accounting/expenses", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
    { errorMessage: "Falha ao criar despesa." },
  );
  const removeExpenseAction = action(
    (id: string) => api(`/accounting/expenses/${id}`, { method: "DELETE" }),
    { errorMessage: "Falha ao remover." },
  );
  // Erro exibido no painel de despesas: qualquer uma das três operações pode tê-lo produzido.
  $: expError = $expenses.error || $createExpenseAction.error || $removeExpenseAction.error;

  let from = new Date().toISOString().slice(0, 8) + "01";
  let to = new Date().toISOString().slice(0, 10);

  // Chips de status em Vendas — substituem o checkbox "mostrar arquivadas"
  // (duas posições) por quatro. Começa em "a_confirmar": é a razão de abrir
  // a aba, então o caso comum não exige clique nenhum.
  type StatusFiltro = "todos" | "a_confirmar" | "vendidos" | "arquivados";
  let statusFiltro: StatusFiltro = "a_confirmar";
  const STATUS_CHIPS: { value: StatusFiltro; label: string }[] = [
    { value: "todos", label: "todos" },
    { value: "a_confirmar", label: "a confirmar" },
    { value: "vendidos", label: "vendidos" },
    { value: "arquivados", label: "arquivados" },
  ];
  function passaStatus(s: Sale, filtro: StatusFiltro): boolean {
    switch (filtro) {
      case "vendidos":
        return s.is_sold;
      case "arquivados":
        return s.is_stale;
      case "a_confirmar":
        return !s.is_sold && !s.is_stale;
      default:
        return true;
    }
  }
  // Período em Vendas reaproveita o mesmo from/to do DRE e do Uso pessoal —
  // dois estados de data independentes fariam a aba Uso pessoal divergir do
  // DRE assim que alguém mexesse só num dos dois (há teste de backend
  // (test_perda_vs_aba_pessoal.py) travando que os dois números batem).
  // Linha sem sold_at (ainda não vendida) passa sempre: se o período
  // derrubasse essas linhas, o chip "a confirmar" — que é só isso —
  // ficaria sempre vazio, o oposto do que a busca deveria resolver.
  function passaPeriodo(s: Sale, de: string, ate: string): boolean {
    return !s.sold_at || (s.sold_at >= de && s.sold_at <= ate);
  }
  // `statusFiltro`/`from`/`to` entram como argumento (não por closure) pra
  // aparecer textualmente no bloco `$:` — o Svelte só rastreia dependência
  // reativa em identificador citado no próprio bloco, não em variável lida
  // de dentro de uma função externa que ele chama. Mesmo padrão que
  // `vendasMostradas`/`despesasMostradas` já usavam (argumento direto, sem
  // vírgula pendurada). Sem isso, o clique nos chips de status (e a troca de
  // período) trocava a classe "on" do botão mas nunca refiltrava a tabela —
  // os e2e pegaram isso.
  $: vendasFiltradas = ($sales.data ?? []).filter(
    (s) => passaStatus(s, statusFiltro) && passaPeriodo(s, from, to),
  );

  // Colunas extraídas pra variável (em vez de literal no template) porque
  // countShown() precisa da mesma definição de coluna que a Table usa pra
  // montar o haystack da busca — ver table-search.ts.
  const vendasColumns = [
    { key: "quote_seq", label: "Orçamento", mono: true, sortable: true,
      format: (v: unknown) => quoteNumber(v as number) },
    { key: "client_name", label: "Cliente", sortable: true },
    { key: "quote_kind", label: "Tipo", format: (v: unknown) => fmtKind(v as string) },
    { key: "itens_label", label: "Itens" },
    { key: "quote_status", label: "Estado" },
    { key: "quote_total", label: "Total", mono: true, align: "right" as const, sortable: true,
      format: (v: unknown) => money(v as string) },
    { key: "cpv_calc", label: "CPV", mono: true, align: "right" as const, sortable: true,
      format: (v: unknown) => money(v as string) },
    { key: "sold_at", label: "Vendido em", mono: true, align: "center" as const, sortable: true,
      format: (v: unknown) => fmtDate(v as string | null) },
  ];
  // Notas não é coluna — entra na busca via searchExtra.
  const vendasSearchExtra = (row: Record<string, unknown>) => (row as Sale).notes ?? "";
  let buscaVendas = "";
  $: vendasMostradas = countShown(vendasFiltradas, buscaVendas, vendasColumns, vendasSearchExtra);
  // Achado IMPORTANT 4 do review final: statusFiltro começa em "a_confirmar",
  // então a busca já roda sobre um subconjunto — procurar o número de uma
  // venda já entregue dá "Nada encontrado para a busca" sem pista nenhuma de
  // que existe um filtro escondendo o resultado. Mantém o default (é a razão
  // de abrir a aba, ver comentário de STATUS_CHIPS acima) mas nomeia o filtro
  // ativo e oferece "ver em todos" assim que a busca zera sob um filtro
  // restrito — sem isso a busca (que existe pra achar registro antigo) é
  // exatamente o caso que o default mais atrapalha.
  $: buscaSemResultadoNoFiltro =
    buscaVendas.trim() !== "" && vendasMostradas === 0 && statusFiltro !== "todos";

  const personalColumns = [
    { key: "quote_seq", label: "#", mono: true, sortable: true,
      format: (v: unknown) => quoteNumber(v as number) },
    { key: "itens_label", label: "Itens" },
    { key: "people", label: "Pessoas",
      format: (v: unknown) => ((v as string[] | undefined)?.join(", ") || "—") },
    { key: "produced_on", label: "Produzido em", mono: true, align: "center" as const, sortable: true,
      format: (v: unknown) => fmtDate(v as string | null) },
    { key: "cpv_calc", label: "CPV", mono: true, align: "right" as const, sortable: true,
      format: (_v: unknown, row: Record<string, unknown>) =>
        money((row as Sale).cpv_override ?? (row as Sale).cpv_calc) },
    { key: "quote_status", label: "Estado" },
  ];
  const personalSearchExtra = (row: Record<string, unknown>) => (row as Sale).notes ?? "";
  let buscaPessoal = "";
  // Chip ativos/arquivados em Uso pessoal — mesmo problema que Vendas já
  // tinha resolvido com activeSalesCount/STATUS_CHIPS (achado IMPORTANT 3 do
  // review final): sem filtro nenhum, a tabela, o contador do cabeçalho e o
  // total da busca misturavam linhas arquivadas (is_stale) com as vivas, sem
  // indicação nenhuma — só o rodapé de perda operacional excluía arquivadas
  // (isLossRow já checa !s.is_stale), então "quantas tem" e "quanto pesa" já
  // não contavam as mesmas linhas. Ao contrário de Vendas, não há chip
  // "vendidos"/"a confirmar" aqui: is_sold em Uso pessoal é uma transição rara
  // (virou venda depois de produzido pra uso próprio) e continua visível
  // inline (div .sale-done), então dois estados (ativos/arquivados) bastam —
  // replicar as quatro posições de Vendas seria filtro sem uso real.
  type PersonalFiltro = "ativos" | "arquivados";
  let personalFiltro: PersonalFiltro = "ativos";
  const PERSONAL_CHIPS: { value: PersonalFiltro; label: string }[] = [
    { value: "ativos", label: "ativos" },
    { value: "arquivados", label: "arquivados" },
  ];
  $: personalFiltrados = ($personal.data ?? []).filter((s) =>
    personalFiltro === "arquivados" ? s.is_stale : !s.is_stale,
  );
  $: personalMostrados = countShown(
    personalFiltrados,
    buscaPessoal,
    personalColumns,
    personalSearchExtra,
  );

  const despesasColumns = [
    { key: "incurred_at", label: "Data", mono: true, sortable: true,
      format: (v: unknown) => fmtDate(v as string) },
    { key: "category", label: "Categoria", sortable: true, format: (v: unknown) => catLabel(v as string) },
    { key: "description", label: "Descrição" },
    { key: "is_recurring", label: "Recorrência", align: "center" as const,
      format: (v: unknown) => (v ? "mensal" : "—") },
    { key: "amount", label: "Valor", mono: true, align: "right" as const, sortable: true,
      format: (v: unknown) => money(v as string) },
  ];
  let buscaDespesas = "";
  $: despesasMostradas = countShown($expenses.data ?? [], buscaDespesas, despesasColumns);

  const dre = resource(() => api<Dre>(`/accounting/dre?from=${from}&to=${to}`), {
    errorMessage: "Falha ao gerar o DRE.",
    auto: false,
  });
  const monthly = resource(
    () => api<MonthlyDre[]>(`/accounting/dre/monthly?from=${from}&to=${to}`),
    { initial: [], errorMessage: "Falha ao gerar o DRE mensal.", auto: false },
  );
  $: monthlyRows = $monthly.data ?? [];
  // A limpeza de fato acontece em dois lugares: reloadDre()/reloadMonthly()
  // zeram o erro do irmão sempre que de fato recarregam (ver comentário
  // acima), e a guarda de setDreMode()/openTab() dispara um reload novo ao
  // entrar num modo cuja última tentativa falhou (não só quando está vazio) —
  // então um erro nunca fica só escondido, ele é refeito. A seleção por modo
  // aqui embaixo é puramente de exibição, por cima disso: evita mostrar, por
  // um instante, o erro do modo que você acabou de sair enquanto o do modo
  // atual ainda está recarregando.
  $: dreError = dreMode === "mensal" ? $monthly.error : $dre.error;

  const prof = resource(() => api<Profitability>(`/accounting/profitability?from=${from}&to=${to}`), {
    errorMessage: "Falha ao gerar a lucratividade.",
    auto: false,
  });

  const CATS: { value: ExpenseCategory; label: string }[] = [
    { value: "maintenance", label: "Manutenção" },
    { value: "parts", label: "Peças" },
    { value: "tools", label: "Ferramentas" },
    { value: "labor", label: "Mecânicos" },
    { value: "equipment", label: "Máquinas/Equipamentos" },
    { value: "other", label: "Outros" },
  ];
  const catLabel = (c: string) => CATS.find((x) => x.value === c)?.label ?? c;
  const fmtKind = (k: string) => (k === "personal" ? "Pessoal" : "Comercial");

  const MONTHS_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  function monthLabel(m: string): string {
    const [y, mm] = m.split("-");
    const idx = Number(mm) - 1;
    return `${MONTHS_PT[idx] ?? mm}/${(y ?? "").slice(2)}`;
  }

  // Recarregar a lista é o "caminho de recarga" que também precisa limpar o
  // erro de uma mutação irmã: sales.reload()/expenses.reload() só zeram o
  // próprio erro do resource — não sabem (nem devem saber, ver resource.ts)
  // que existe uma action() cujo erro está combinado no mesmo alerta. Sem
  // isso, um PATCH/POST/DELETE que falhou deixa a mensagem presa na tela
  // mesmo depois de um "Atualizar" bem-sucedido.
  function reloadSales() {
    saveSale.reset();
    return sales.reload();
  }
  // Mesmo raciocínio de reloadSales(): saveSale é a mesma action() das duas
  // sub-abas (mesmo endpoint PATCH /accounting/sales/{id}), então seu erro
  // preso precisa ser limpo aqui também, não só do lado Vendas.
  function reloadPersonal() {
    saveSale.reset();
    return personal.reload();
  }
  function reloadExpenses() {
    createExpenseAction.reset();
    removeExpenseAction.reset();
    return expenses.reload();
  }
  // Mesmo raciocínio para o DRE: dre e monthly são dois resource() (não um
  // resource()+action()), mas o problema é idêntico — um reload() bem-sucedido
  // num modo não apaga sozinho o erro velho que ficou no outro (são stores
  // independentes). Igual a reloadSales()/reloadExpenses(), o reset() aqui só
  // roda emparelhado com um reload() que de fato vai acontecer — nunca sozinho
  // — então é honesto: o resultado exibido é sempre o desfecho real dessa
  // chamada. (A guarda de setDreMode/openTab que decide SE chama reloadDre()/
  // reloadMonthly() é outro problema, resolvido separadamente ali.)
  function reloadDre() {
    monthly.reset();
    return dre.reload();
  }
  function reloadMonthly() {
    dre.reset();
    return monthly.reload();
  }

  // Registra a venda com a data escolhida no popover. A resposta do PATCH já
  // vem com a linha inteira (itens_label, client_name, quote_seq,
  // produced_on, people) — trocarLinha() substitui a linha na lista em
  // memória com ela, sem recarregar a lista inteira (o reload provisório da
  // Task 4 da Spec 0 sai daqui).
  async function registrarVenda(s: Sale, dados: { sold_at: string; confirmed_revenue: string }) {
    const atualizada = await saveSale.run(s.id, { is_sold: true, ...dados });
    if (!atualizada) return; // erro já exposto em $saveSale.error (alerta da aba)
    editandoId = null;
    trocarLinha(atualizada);
  }

  // Desfazer apaga a data e a receita confirmada no backend (PATCH com
  // is_sold: false limpa os dois) — por isso o aviso antes de agir.
  async function desfazer(s: Sale) {
    if (!confirm("Desfazer a venda apaga a data e a receita confirmada. Continuar?")) return;
    const atualizada = await saveSale.run(s.id, { is_sold: false });
    if (atualizada) trocarLinha(atualizada);
  }

  // Atualização otimista: substitui a linha pelo objeto que o PATCH devolveu
  // em qualquer uma das duas listas (Vendas é comercial, Uso pessoal é
  // pessoal — a linha só existe numa das duas, mas a função não precisa saber
  // qual).
  function trocarLinha(nova: Sale) {
    for (const r of [sales, personal]) {
      const atual = get(r).data ?? [];
      if (atual.some((x) => x.id === nova.id)) {
        r.set(atual.map((x) => (x.id === nova.id ? nova : x)));
      }
    }
  }

  async function createExpense() {
    const created = await createExpenseAction.run({
      category: exCategory,
      description: exDescription,
      amount: exAmount,
      is_recurring: exRecurring,
      incurred_at: exDate,
    });
    if (created) {
      exDescription = "";
      exAmount = "";
      exRecurring = false;
      await reloadExpenses();
    }
  }
  async function removeExpense(id: string) {
    if (!confirm("Remover esta despesa?")) return;
    // run() volta undefined tanto no erro quanto no sucesso sem corpo (DELETE não devolve
    // conteúdo) — os dois casos só se distinguem olhando o .error da action.
    await removeExpenseAction.run(id);
    if (!$removeExpenseAction.error) await reloadExpenses();
  }
  function exportXlsx() {
    window.open(`/api/accounting/dre/export.xlsx?from=${from}&to=${to}`, "_blank");
  }

  function generateDre() {
    if (dreMode === "mensal") reloadMonthly();
    else reloadDre();
  }
  // A guarda (pré-existente) só recarregava "se vazio" — mas monthlyRows não
  // fica vazio quando um reload falha (falha preserva os dados antigos, só
  // marca error). Isso deixava dois caminhos ruins: (a) reset() incondicional
  // antes da guarda (tentado numa rodada anterior) apagava o erro sem refazer
  // a busca — dado velho na tela, sem aviso e sem nova tentativa, silencioso
  // e pior que o bug original; (b) sem reset() nenhum, o erro velho reaparecia
  // ao voltar para o modo. A guarda certa é "vazio OU a tentativa anterior
  // falhou": erro significa que o dado exibido não é confiável, e a resposta
  // a dado não confiável é refazer a busca, não apagar o aviso. O próprio
  // reload() já é honesto nos dois desfechos — limpa o erro no sucesso, repõe
  // no fracasso — então isso resolve sem reset() nenhum neste caminho.
  function setDreMode(m: typeof dreMode) {
    dreMode = m;
    if (m === "mensal" && (monthlyRows.length === 0 || $monthly.error)) reloadMonthly();
    else if (m === "periodo" && (!$dre.data || $dre.error)) reloadDre();
  }

  function openTab(t: typeof tab) {
    tab = t;
    if (t === "dre") {
      if (dreMode === "mensal" && (monthlyRows.length === 0 || $monthly.error)) reloadMonthly();
      else if (dreMode === "periodo" && (!$dre.data || $dre.error)) reloadDre();
    }
    if (t === "lucratividade" && !$prof.data) prof.reload();
  }

  type DreAmountKey =
    | "receita_bruta"
    | "impostos"
    | "receita_liquida"
    | "cpv"
    | "custos_variaveis"
    | "lucro_bruto"
    | "custo_estoque"
    | "perda_operacional"
    | "resultado_liquido";
  function sumMonthly(key: DreAmountKey): number {
    return monthlyRows.reduce((acc, m) => acc + Number(m[key] || 0), 0);
  }
  function sumMonthlyCat(cat: string): number {
    return monthlyRows.reduce((acc, m) => acc + Number(m.despesas[cat] || 0), 0);
  }
  $: monthlyCats = Array.from(
    new Set(monthlyRows.flatMap((m) => Object.keys(m.despesas))),
  ).sort();
  $: totalReceitaLiquida = sumMonthly("receita_liquida");
  $: totalResultado = sumMonthly("resultado_liquido");
  $: totalMargemPct =
    totalReceitaLiquida !== 0 ? (totalResultado / totalReceitaLiquida) * 100 : 0;

  // Denominador exclui arquivadas — o mesmo recorte que o default antigo
  // (is_stale=false na URL) já dava ao badge da sub-aba; sem isso, a busca
  // agora trazendo tudo do backend infla o "de quantas" com registros mortos.
  $: activeSalesCount = ($sales.data ?? []).filter((s) => !s.is_stale).length;
  $: confirmedCount = ($sales.data ?? []).filter((s) => s.is_sold && !s.is_stale).length;
  $: expenseTotal = ($expenses.data ?? []).reduce((acc, e) => acc + Number(e.amount || 0), 0);
  $: dreNegative = $dre.data ? Number($dre.data.resultado_liquido) < 0 : false;

  // Linhas que entram na perda operacional do período: pessoal, não vendida,
  // não arquivada, com loss_on dentro de [from, to]. loss_on (não produced_on)
  // é o critério real do DRE (backend/core/accounting/dre.py:_perda_operacional):
  // produced_on OU, na falta de produção, a data de criação da venda — um
  // orçamento pessoal aprovado mas ainda não produzido já pesa na perda, e
  // produced_on ficaria null pra ele (a coluna "Produzido em" não pode mentir
  // dizendo que foi produzido). Usar produced_on aqui foi o bug que fez este
  // rodapé divergir do DRE silenciosamente — travado por
  // backend/tests/api/test_perda_vs_aba_pessoal.py. Comparação lexicográfica
  // de datas ISO (YYYY-MM-DD) é comparação cronológica, então dá pra comparar
  // as strings direto sem parsear.
  function isLossRow(s: Sale, de: string, ate: string): boolean {
    return !s.is_sold && !s.is_stale && s.loss_on >= de && s.loss_on <= ate;
  }
  // Mesmo bug dos chips de Vendas (ver vendasFiltradas acima) — `from`/`to`
  // entram como argumento, não por closure, pra aparecer textualmente no
  // bloco `$:` e serem de fato usados. Sem isso, arrastar as datas em Uso
  // pessoal trocava o rótulo do período (reativo direto no template) mas não
  // o valor da perda operacional, que ficava congelado no período anterior.
  $: perdaPeriodo = ($personal.data ?? [])
    .filter((s) => isLossRow(s, from, to))
    .reduce((acc, s) => acc + Number(s.cpv_override ?? s.cpv_calc), 0);
  // Erro combinado do painel Uso pessoal: mesma lógica de expError acima —
  // saveSale é action() compartilhada com Vendas.
  $: personalError = $personal.error || $saveSale.error;

  onMount(() => {
    if (requireAuth()) return;
    reloadSales();
    reloadPersonal();
    reloadExpenses();
    reloadDre();
    periodReady = true;
  });

  // from/to são compartilhados por Vendas, Uso pessoal, DRE e Lucratividade,
  // mas só Vendas/Uso pessoal filtram client-side (passaPeriodo/isLossRow,
  // reativos de graça). DRE e Lucratividade vêm de resource() escopados por
  // from/to no fetch (dre, monthly, prof) — nada os recarregava ao trocar o
  // período: o cabeçalho ({fmtDate(from)} — {fmtDate(to)}) mudava, os números
  // continuavam do período antigo, sem aviso nenhum (CRITICAL 1 do review
  // final). invalidatePeriodo() corrige isso apagando os três assim que
  // from/to mudam — imediato e sem custo de rede (só limpa a store), então
  // não tem por que atrasar: atrasar deixaria uma janela com cabeçalho novo e
  // número velho, exatamente o bug. Isso também resolve de graça o problema
  // irmão (a guarda `$dre.loading && !$dre.data` ficava falsa durante um
  // reload porque `data` já existia): com data limpo antes do reload, a
  // guarda volta a ser verdadeira assim que o reload começa.
  // O reload de fato (que gasta rede) é debounced — do contrário, arrastar
  // o seletor de data ou digitar dispararia uma requisição por tecla — e só
  // acontece pra aba ATUALMENTE aberta; as outras ficam invalidadas e
  // recarregam sozinhas na próxima vez que forem abertas, pela guarda já
  // existente em openTab()/setDreMode().
  // periodReady é lido só de DENTRO de invalidatePeriodo(), nunca no corpo
  // do `$:` abaixo — Svelte só rastreia como dependência reativa o que
  // aparece textualmente na própria declaração `$:`, não o que uma função
  // chamada por ela lê. Colocar `periodReady` ali dentro (como uma versão
  // anterior fazia) faz esse próprio `$:` também disparar quando
  // periodReady vira true no fim do onMount() — depois que reloadDre() já
  // começou — e invalidatePeriodo() cancelava (seq++) o fetch que tinha
  // acabado de sair, trocando o pré-aquecimento da aba DRE por um GET
  // jogado fora e 400ms de spinner a mais em toda carga de página.
  let periodReady = false; // true só depois do onMount(): evita invalidar antes da primeira carga
  let periodDebounceTimer: ReturnType<typeof setTimeout> | undefined;
  $: {
    from; to;
    invalidatePeriodo();
  }
  function invalidatePeriodo() {
    if (!periodReady) return;
    dre.invalidate();
    monthly.invalidate();
    prof.invalidate();
    clearTimeout(periodDebounceTimer);
    periodDebounceTimer = setTimeout(() => {
      if (tab === "dre") generateDre();
      else if (tab === "lucratividade") prof.reload();
    }, 400);
  }
  onDestroy(() => clearTimeout(periodDebounceTimer));
</script>

<header class="page-head">
  <span class="page-eyebrow">Financeiro / 05</span>
  <h1 class="page-title">Contábil<em>.</em></h1>
  <p class="page-lede">
    Vendas confirmadas viram receita; despesas avulsas entram no DRE. Confirme o que entregou, lance os
    gastos do mês e leia o resultado líquido fechado.
  </p>
</header>

<nav class="subtabs" aria-label="Seções da contabilidade">
  <button type="button" class="subtab" class:active={tab === "vendas"} on:click={() => openTab("vendas")}>
    <span class="idx">01</span> Vendas
    <span class="badge mono">{confirmedCount}/{activeSalesCount}</span>
  </button>
  <button type="button" class="subtab" class:active={tab === "pessoal"} on:click={() => openTab("pessoal")}>
    <span class="idx">02</span> Uso pessoal
    <span class="badge mono" title="Perda operacional no período">{money(perdaPeriodo)}</span>
  </button>
  <button type="button" class="subtab" class:active={tab === "despesas"} on:click={() => openTab("despesas")}>
    <span class="idx">03</span> Despesas
    <span class="badge mono">{($expenses.data ?? []).length}</span>
  </button>
  <button type="button" class="subtab" class:active={tab === "dre"} on:click={() => openTab("dre")}>
    <span class="idx">04</span> DRE
  </button>
  <button
    type="button"
    class="subtab"
    class:active={tab === "lucratividade"}
    on:click={() => openTab("lucratividade")}
  >
    <span class="idx">05</span> Lucratividade
  </button>
</nav>

{#if tab === "vendas"}
  <section class="panel list-panel">
    <div class="panel-head">
      <h2 class="section-title">
        Vendas <span class="count">· {vendasFiltradas.length}</span>
      </h2>
      <div class="head-tools">
        <div class="chips" role="group" aria-label="Filtrar por status">
          {#each STATUS_CHIPS as c}
            <button
              type="button"
              class="chip"
              class:on={statusFiltro === c.value}
              on:click={() => (statusFiltro = c.value)}
            >
              {c.label}
            </button>
          {/each}
        </div>
        <label class="field">
          De
          <input type="date" bind:value={from} />
        </label>
        <label class="field">
          Até
          <input type="date" bind:value={to} />
        </label>
        <button class="tiny ghost" on:click={reloadSales} disabled={$sales.loading}>
          {$sales.loading ? "Carregando…" : "Atualizar"}
        </button>
      </div>
    </div>
    {#if $sales.error || $saveSale.error}<div class="alert">{$sales.error || $saveSale.error}</div>{/if}
    <SearchBar
      bind:value={buscaVendas}
      total={vendasFiltradas.length}
      shown={vendasMostradas}
      placeholder="buscar por número, cliente, peça ou nota…"
    />
    <Table
      columns={vendasColumns}
      rows={vendasFiltradas}
      searchText={buscaVendas}
      searchExtra={vendasSearchExtra}
      empty="Nenhuma venda elegível ainda"
    >
      <svelte:fragment slot="actions" let:row>
        {@const s = row as Sale}
        {#if editandoId === s.id}
          <SaleEditor
            sale={s}
            pending={$saveSale.pending}
            on:save={(e) => registrarVenda(s, e.detail)}
            on:cancel={() => (editandoId = null)}
          />
        {:else if s.is_sold}
          <div class="sale-done mono">
            <span>{fmtDate(s.sold_at)}</span>
            <span>{money(s.confirmed_revenue)}</span>
            <button class="tiny ghost" on:click={() => (editandoId = s.id)}>editar</button>
            <button class="tiny ghost danger" on:click={() => desfazer(s)}>desfazer</button>
          </div>
        {:else}
          <button class="tiny" class:stale={s.is_stale} on:click={() => (editandoId = s.id)}>
            registrar venda
          </button>
        {/if}
      </svelte:fragment>
    </Table>
    {#if buscaSemResultadoNoFiltro}
      <p class="hint mono search-filter-hint">
        Nada encontrado para essa busca no filtro
        <strong>{STATUS_CHIPS.find((c) => c.value === statusFiltro)?.label}</strong>.
        <button type="button" class="tiny ghost" on:click={() => (statusFiltro = "todos")}>
          ver em todos
        </button>
      </p>
    {/if}
    <p class="hint mono">
      A receita confirmada substitui o total do orçamento no DRE. Bobinas e CPV vêm do cálculo original.
    </p>
  </section>
{/if}

{#if tab === "pessoal"}
  <section class="panel list-panel">
    <div class="panel-head">
      <h2 class="section-title">
        Uso pessoal <span class="count">· {personalFiltrados.length}</span>
      </h2>
      <div class="head-tools">
        <div class="chips" role="group" aria-label="Filtrar por status">
          {#each PERSONAL_CHIPS as c}
            <button
              type="button"
              class="chip"
              class:on={personalFiltro === c.value}
              on:click={() => (personalFiltro = c.value)}
            >
              {c.label}
            </button>
          {/each}
        </div>
        <label class="field">
          De
          <input type="date" bind:value={from} />
        </label>
        <label class="field">
          Até
          <input type="date" bind:value={to} />
        </label>
        <button class="tiny ghost" on:click={reloadPersonal} disabled={$personal.loading}>
          {$personal.loading ? "Carregando…" : "Atualizar"}
        </button>
      </div>
    </div>
    {#if personalError}<div class="alert">{personalError}</div>{/if}
    <SearchBar
      bind:value={buscaPessoal}
      total={personalFiltrados.length}
      shown={personalMostrados}
      placeholder="buscar por número, peça, pessoa ou nota…"
    />
    <Table
      columns={personalColumns}
      rows={personalFiltrados}
      searchText={buscaPessoal}
      searchExtra={personalSearchExtra}
      empty="Nenhum uso pessoal produzido ainda"
    >
      <svelte:fragment slot="actions" let:row>
        {@const s = row as Sale}
        {#if editandoId === s.id}
          <SaleEditor
            sale={s}
            pending={$saveSale.pending}
            on:save={(e) => registrarVenda(s, e.detail)}
            on:cancel={() => (editandoId = null)}
          />
        {:else if s.is_sold}
          <div class="sale-done mono">
            <span>{fmtDate(s.sold_at)}</span>
            <span>{money(s.confirmed_revenue)}</span>
            <button class="tiny ghost" on:click={() => (editandoId = s.id)}>editar</button>
            <button class="tiny ghost danger" on:click={() => desfazer(s)}>desfazer</button>
          </div>
        {:else}
          <button class="tiny" class:stale={s.is_stale} on:click={() => (editandoId = s.id)}>
            registrar venda
          </button>
        {/if}
      </svelte:fragment>
    </Table>
    <p class="hint mono personal-footer">
      Perda operacional no período ({fmtDate(from)} — {fmtDate(to)}): <strong>{money(perdaPeriodo)}</strong>
      — soma o CPV das linhas não vendidas e não arquivadas produzidas nessa janela. Bate com a linha
      "Perda operacional" do DRE no mesmo período.
    </p>
  </section>
{/if}

{#if tab === "despesas"}
  <Form
    eyebrow="Novo lançamento"
    title="Registrar despesa"
    submitLabel="Lançar"
    submitting={$createExpenseAction.pending}
    error={expError}
    allowSubmit={exDescription.trim().length > 0 && exAmount !== ""}
    on:submit={createExpense}
  >
    <label class="field">
      Categoria
      <select bind:value={exCategory}>
        {#each CATS as c}<option value={c.value}>{c.label}</option>{/each}
      </select>
    </label>
    <label class="field full">
      Descrição
      <input bind:value={exDescription} placeholder="Troca de bico, parafusos, lubrificante…" required />
    </label>
    <label class="field">
      Valor (R$)
      <input bind:value={exAmount} type="number" step="0.01" min="0" required />
    </label>
    <label class="field">
      Data
      <input type="date" bind:value={exDate} required />
    </label>
    <label class="field recurring-field">
      <span class="recurring-spacer">&nbsp;</span>
      <span class="recurring-check toggle mono">
        <input type="checkbox" bind:checked={exRecurring} />
        recorrente (mensal)
      </span>
    </label>
  </Form>

  <section class="panel list-panel">
    <div class="panel-head">
      <h2 class="section-title">
        Despesas <span class="count">· {($expenses.data ?? []).length}</span>
        {#if ($expenses.data ?? []).length > 0}<span class="head-sum mono">total {money(expenseTotal)}</span>{/if}
      </h2>
      <button class="tiny ghost" on:click={reloadExpenses} disabled={$expenses.loading}>
        {$expenses.loading ? "Carregando…" : "Atualizar"}
      </button>
    </div>
    {#if expError}<div class="alert">{expError}</div>{/if}
    <SearchBar
      bind:value={buscaDespesas}
      total={($expenses.data ?? []).length}
      shown={despesasMostradas}
      placeholder="buscar por descrição ou categoria…"
    />
    <Table
      columns={despesasColumns}
      rows={$expenses.data ?? []}
      searchText={buscaDespesas}
      empty="Nenhuma despesa lançada"
    >
      <svelte:fragment slot="actions" let:row>
        <button class="tiny danger" on:click={() => removeExpense((row as Expense).id)}>Excluir</button>
      </svelte:fragment>
    </Table>
  </section>
{/if}

{#if tab === "dre"}
  <section class="panel dre-controls">
    <div class="panel-head">
      <h2 class="section-title">Demonstrativo de resultado</h2>
      <div class="head-tools">
        <div class="segmented mono" role="group" aria-label="Modo do DRE">
          <button
            type="button"
            class:active={dreMode === "periodo"}
            on:click={() => setDreMode("periodo")}>Período</button
          >
          <button
            type="button"
            class:active={dreMode === "mensal"}
            on:click={() => setDreMode("mensal")}>Mensal</button
          >
        </div>
        <button class="tiny ghost" on:click={exportXlsx}>Exportar XLSX</button>
      </div>
    </div>
    <div class="period">
      <label class="field">
        De
        <input type="date" bind:value={from} />
      </label>
      <label class="field">
        Até
        <input type="date" bind:value={to} />
      </label>
      <button class="generate" on:click={generateDre} disabled={$dre.loading || $monthly.loading}>
        {$dre.loading || $monthly.loading ? "Calculando…" : "Gerar"}
      </button>
    </div>
    {#if dreError}<div class="alert">{dreError}</div>{/if}
  </section>

  {#if dreMode === "mensal"}
    {#if $monthly.loading && monthlyRows.length === 0}
      <div class="state mono">Calculando demonstrativo mensal…</div>
    {:else if monthlyRows.length > 0}
      <section class="ledger panel" aria-label="DRE mensal">
        <div class="ledger-mast">
          <span class="ledger-eyebrow mono">DRE mensal</span>
          <span class="ledger-range mono">{fmtDate(from)} — {fmtDate(to)}</span>
        </div>
        <div class="grid-wrap">
          <table class="dre-grid">
            <thead>
              <tr>
                <th class="acct">Conta</th>
                {#each monthlyRows as m}<th class="num">{monthLabel(m.month)}</th>{/each}
                <th class="num total">Total</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td class="acct">Receita bruta</td>
                {#each monthlyRows as m}<td class="num mono">{money(m.receita_bruta)}</td>{/each}
                <td class="num mono total">{money(sumMonthly("receita_bruta"))}</td>
              </tr>
              <tr class="muted">
                <td class="acct"><span class="op">(−)</span> Impostos</td>
                {#each monthlyRows as m}<td class="num mono">{money(m.impostos)}</td>{/each}
                <td class="num mono total">{money(sumMonthly("impostos"))}</td>
              </tr>
              <tr class="sub">
                <td class="acct"><span class="op">=</span> Receita líquida</td>
                {#each monthlyRows as m}<td class="num mono">{money(m.receita_liquida)}</td>{/each}
                <td class="num mono total">{money(sumMonthly("receita_liquida"))}</td>
              </tr>
              <tr class="muted">
                <td class="acct"><span class="op">(−)</span> CPV</td>
                {#each monthlyRows as m}<td class="num mono">{money(m.cpv)}</td>{/each}
                <td class="num mono total">{money(sumMonthly("cpv"))}</td>
              </tr>
              <tr class="muted">
                <td class="acct"><span class="op">(−)</span> Custos variáveis</td>
                {#each monthlyRows as m}<td class="num mono">{money(m.custos_variaveis)}</td>{/each}
                <td class="num mono total">{money(sumMonthly("custos_variaveis"))}</td>
              </tr>
              <tr class="sub">
                <td class="acct"><span class="op">=</span> Lucro bruto</td>
                {#each monthlyRows as m}<td class="num mono">{money(m.lucro_bruto)}</td>{/each}
                <td class="num mono total">{money(sumMonthly("lucro_bruto"))}</td>
              </tr>
              {#each monthlyCats as cat}
                <tr class="muted">
                  <td class="acct expense"><span class="op">(−)</span> {catLabel(cat)}</td>
                  {#each monthlyRows as m}<td class="num mono">{money(m.despesas[cat] ?? 0)}</td>{/each}
                  <td class="num mono total">{money(sumMonthlyCat(cat))}</td>
                </tr>
              {/each}
              <tr class="muted">
                <td class="acct expense"><span class="op">(−)</span> Custo de estoque</td>
                {#each monthlyRows as m}<td class="num mono">{money(m.custo_estoque)}</td>{/each}
                <td class="num mono total">{money(sumMonthly("custo_estoque"))}</td>
              </tr>
              <tr class="muted">
                <td class="acct expense"><span class="op">(−)</span> Perda operacional (uso pessoal)</td>
                {#each monthlyRows as m}<td class="num mono">{money(m.perda_operacional)}</td>{/each}
                <td class="num mono total">{money(sumMonthly("perda_operacional"))}</td>
              </tr>
              <tr class="result">
                <td class="acct"><span class="op">=</span> Resultado líquido</td>
                {#each monthlyRows as m}
                  <td class="num mono" class:neg={Number(m.resultado_liquido) < 0}>
                    {money(m.resultado_liquido)}
                  </td>
                {/each}
                <td class="num mono total" class:neg={totalResultado < 0}>{money(totalResultado)}</td>
              </tr>
              <tr class="margin-row">
                <td class="acct">Margem %</td>
                {#each monthlyRows as m}<td class="num mono">{m.margem_liquida_pct}%</td>{/each}
                <td class="num mono total">{totalMargemPct.toFixed(1)}%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    {:else}
      <div class="state mono">Selecione um período e gere o demonstrativo mensal.</div>
    {/if}
  {:else if $dre.loading && !$dre.data}
    <div class="state mono">Calculando demonstrativo…</div>
  {:else if $dre.data}
    {@const d = $dre.data}
    <section class="ledger panel" aria-label="Demonstrativo de resultado">
      <div class="ledger-mast">
        <span class="ledger-eyebrow mono">DRE</span>
        <span class="ledger-range mono">{fmtDate(from)} — {fmtDate(to)}</span>
      </div>

      <dl class="statement">
        <div class="line revenue">
          <dt>Receita bruta</dt>
          <dd class="mono">{money(d.receita_bruta)}</dd>
        </div>
        <div class="line deduction">
          <dt><span class="op">(−)</span> Impostos</dt>
          <dd class="mono">{money(d.impostos)}</dd>
        </div>
        <div class="line subtotal">
          <dt><span class="op">=</span> Receita líquida</dt>
          <dd class="mono">{money(d.receita_liquida)}</dd>
        </div>
        <div class="line deduction">
          <dt><span class="op">(−)</span> CPV</dt>
          <dd class="mono">{money(d.cpv)}</dd>
        </div>
        <div class="line deduction">
          <dt><span class="op">(−)</span> Custos variáveis</dt>
          <dd class="mono">{money(d.custos_variaveis)}</dd>
        </div>
        <div class="line subtotal">
          <dt><span class="op">=</span> Lucro bruto</dt>
          <dd class="mono">{money(d.lucro_bruto)}</dd>
        </div>

        <div class="group-head">
          <dt>Despesas operacionais</dt>
          <dd class="mono">{money(d.total_despesas)}</dd>
        </div>
        <div class="line expense">
          <dt><span class="op">(−)</span> Custo de estoque (não vendido)</dt>
          <dd class="mono">{money(d.custo_estoque)}</dd>
        </div>
        <div class="line expense">
          <dt><span class="op">(−)</span> Perda operacional (uso pessoal)</dt>
          <dd class="mono">{money(d.perda_operacional)}</dd>
        </div>
        {#each Object.entries(d.despesas) as [cat, val]}
          <div class="line expense">
            <dt><span class="op">(−)</span> {catLabel(cat)}</dt>
            <dd class="mono">{money(val)}</dd>
          </div>
        {/each}
        {#if Object.keys(d.despesas).length === 0}
          <div class="line expense empty-line">
            <dt>Sem despesas no período</dt>
            <dd class="mono">{money(0)}</dd>
          </div>
        {/if}

        <div class="line result" class:negative={dreNegative}>
          <dt><span class="op">=</span> Resultado líquido</dt>
          <dd class="mono">{money(d.resultado_liquido)}</dd>
        </div>
      </dl>

      <div class="margin-strip" class:negative={dreNegative}>
        <span class="margin-label mono">Margem líquida</span>
        <span class="margin-value mono">{d.margem_liquida_pct}%</span>
      </div>
    </section>
  {:else}
    <div class="state mono">Selecione um período e gere o demonstrativo.</div>
  {/if}
{/if}

{#if tab === "lucratividade"}
  <section class="panel dre-controls">
    <div class="panel-head">
      <h2 class="section-title">Lucratividade</h2>
    </div>
    <div class="period">
      <label class="field">
        De
        <input type="date" bind:value={from} />
      </label>
      <label class="field">
        Até
        <input type="date" bind:value={to} />
      </label>
      <button class="generate" on:click={prof.reload} disabled={$prof.loading}>
        {$prof.loading ? "Calculando…" : "Gerar"}
      </button>
    </div>
    {#if $prof.error}<div class="alert">{$prof.error}</div>{/if}
  </section>

  {#if $prof.loading && !$prof.data}
    <div class="state mono">Calculando lucratividade…</div>
  {:else if $prof.data}
    {@const p = $prof.data}
    {#each [{ title: "Por cliente", rows: p.by_client, empty: "Nenhum cliente no período" }, { title: "Por material", rows: p.by_material, empty: "Nenhum material no período" }] as block}
      <section class="panel list-panel">
        <div class="panel-head">
          <h2 class="section-title">
            {block.title} <span class="count">· {block.rows.length}</span>
          </h2>
        </div>
        <Table
          columns={[
            { key: "label", label: block.title.replace("Por ", "") },
            { key: "receita", label: "Receita", mono: true, align: "right", format: (v) => money(v as string) },
            { key: "custo", label: "Custo", mono: true, align: "right", format: (v) => money(v as string) },
            { key: "margem", label: "Margem", mono: true, align: "right", format: (v) => money(v as string) },
            { key: "margem_pct", label: "Margem %", mono: true, align: "right", format: (v) => `${v}%` },
          ]}
          rows={block.rows as unknown as Record<string, unknown>[]}
          empty={block.empty}
        />
      </section>
    {/each}
  {:else}
    <div class="state mono">Selecione um período e gere a lucratividade.</div>
  {/if}
{/if}

<style>
  .page-head {
    margin-bottom: 1.5rem;
  }
  .list-panel {
    margin-top: 1.5rem;
  }
  .list-panel :global(.searchbar) {
    margin: 1rem 0;
  }
  .field.full {
    grid-column: 1 / -1;
  }

  /* ---------- sub-tabs ---------- */
  .subtabs {
    display: flex;
    flex-wrap: wrap;
    gap: 0;
    border: 1px solid var(--line-strong);
    background: var(--paper);
    margin-bottom: 1.5rem;
  }
  /* .subtab e estados/filhos (.idx, .badge) agora vivem em app.css */

  /* ---------- vendas ---------- */
  .head-tools {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 1rem;
  }
  /* .toggle agora vive em app.css */
  /* Chips de status (todos · a confirmar · vendidos · arquivados) — mesma
     classe .chip/.chip.on que os chips de pessoa em Orçamentos, só que
     aqui é seleção única (um "on" por vez), não múltipla. */
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
  }
  /* Venda já registrada: data + receita confirmada, com editar/desfazer ao
     lado. Some com registrar venda/checkbox — quem está registrado mostra o
     que foi gravado, não um formulário. */
  .sale-done {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    justify-content: flex-end;
    font-size: 0.82rem;
    color: var(--ink);
    white-space: nowrap;
  }
  button.tiny.stale {
    opacity: 0.45;
  }
  /* Override local: tamanho/margem menores que o padrão global (cor já vem de app.css) */
  .hint {
    margin: 1rem 0 0;
    font-size: 0.68rem;
    letter-spacing: 0.04em;
  }
  .personal-footer strong {
    color: var(--ink);
    font-weight: 600;
  }
  .search-filter-hint {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.5rem;
    color: var(--ink);
  }
  .search-filter-hint strong {
    font-weight: 600;
  }

  /* ---------- uso pessoal: mesmo padrão de .field das datas do DRE, só compacto */
  .head-tools .field {
    min-width: 0;
  }
  .head-tools .field input {
    padding: 0.3rem 0.45rem;
    font-size: 0.78rem;
  }
  .recurring-field .recurring-spacer {
    display: block;
    font-size: 0.66rem;
  }
  .recurring-check {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.55rem 0;
  }
  .recurring-check input {
    width: auto;
    margin: 0;
  }
  .head-sum {
    margin-left: 0.6rem;
    font-size: 0.64rem;
    color: var(--muted);
    letter-spacing: 0.08em;
    text-transform: none;
  }

  /* ---------- DRE controls ---------- */
  .dre-controls .period {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: 0.85rem 1rem;
  }
  .dre-controls .field {
    flex: 0 0 auto;
    min-width: 150px;
  }
  .generate {
    height: fit-content;
  }

  /* ---------- segmented control ---------- */
  .segmented {
    display: inline-flex;
    border: 1px solid var(--line-strong);
    background: var(--paper);
  }
  .segmented button {
    background: transparent;
    border: 0;
    border-right: 1px solid var(--line);
    color: var(--muted);
    padding: 0.4rem 0.8rem;
    font-size: 0.66rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    cursor: pointer;
    transition: background 120ms ease, color 120ms ease;
  }
  .segmented button:last-child {
    border-right: 0;
  }
  .segmented button:hover {
    color: var(--ink);
  }
  .segmented button.active {
    background: var(--ink);
    color: var(--paper);
  }

  /* ---------- DRE monthly grid ---------- */
  .grid-wrap {
    overflow-x: auto;
  }
  .dre-grid {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.86rem;
  }
  .dre-grid th,
  .dre-grid td {
    padding: 0.5rem 0.85rem;
    border-bottom: 1px solid var(--line);
    white-space: nowrap;
  }
  .dre-grid thead th {
    font-family: var(--font-mono);
    font-weight: 500;
    font-size: 0.64rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
    border-bottom: 1px solid var(--line-strong);
    background: var(--paper);
    position: sticky;
    top: 0;
  }
  .dre-grid .acct {
    text-align: left;
    color: var(--ink);
  }
  .dre-grid .acct.expense {
    padding-left: 1.6rem;
    color: var(--muted);
  }
  .dre-grid .num {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .dre-grid .total {
    border-left: 1px solid var(--line-strong);
    font-weight: 600;
  }
  .dre-grid .op {
    display: inline-block;
    width: 1.4rem;
    color: var(--muted);
    font-family: var(--font-mono);
    font-size: 0.72rem;
  }
  .dre-grid tr.muted td {
    color: var(--muted);
  }
  .dre-grid tr.sub td {
    font-weight: 600;
    border-bottom: 1px solid var(--line-strong);
  }
  .dre-grid tr.sub td.acct {
    color: var(--ink);
  }
  .dre-grid tr.result td {
    border-top: 2px solid var(--ink);
    border-bottom: none;
    font-weight: 600;
    color: var(--ok);
  }
  .dre-grid tr.result td.acct {
    color: var(--ink);
    font-family: var(--font-display);
  }
  .dre-grid tr.result td.neg {
    color: var(--danger);
  }
  .dre-grid tr.margin-row td {
    border-bottom: none;
    color: var(--muted);
    font-size: 0.78rem;
  }
  .dre-grid tr.margin-row td.acct {
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .state {
    border: 1px dashed var(--line);
    background: var(--paper);
    padding: 2.5rem 1rem;
    text-align: center;
    color: var(--muted);
    font-size: 0.74rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin-top: 1.5rem;
  }

  /* ---------- DRE statement ---------- */
  .ledger {
    margin-top: 1.5rem;
    padding: 0;
    overflow: hidden;
  }
  .ledger-mast {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding: 1rem 1.4rem;
    border-bottom: 1px solid var(--line-strong);
    background: var(--ink);
    color: var(--paper);
  }
  .ledger-eyebrow {
    font-size: 0.72rem;
    letter-spacing: 0.32em;
    text-transform: uppercase;
  }
  .ledger-range {
    font-size: 0.68rem;
    letter-spacing: 0.12em;
    opacity: 0.7;
  }

  .statement {
    margin: 0;
    padding: 0.6rem 1.4rem;
  }
  .statement .line,
  .statement .group-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--line);
  }
  .statement dt {
    font-size: 0.92rem;
    color: var(--ink);
  }
  .statement dd {
    margin: 0;
    font-size: 0.92rem;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .statement .op {
    display: inline-block;
    width: 1.6rem;
    color: var(--muted);
    font-family: var(--font-mono);
    font-size: 0.78rem;
  }

  .line.deduction dt,
  .line.expense dt {
    color: var(--muted);
  }
  .line.deduction dd,
  .line.expense dd {
    color: var(--muted);
  }
  .line.expense {
    padding-left: 1rem;
  }
  .empty-line dt {
    font-style: italic;
  }

  .group-head {
    margin-top: 0.4rem;
    border-bottom: 1px dashed var(--line-strong);
  }
  .group-head dt {
    font-family: var(--font-mono);
    font-size: 0.66rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--ink);
  }
  .group-head dd {
    font-size: 0.82rem;
    color: var(--muted);
  }

  .line.subtotal {
    border-bottom: 1px solid var(--line-strong);
  }
  .line.subtotal dt,
  .line.subtotal dd {
    font-weight: 600;
  }

  .line.result {
    border-bottom: none;
    border-top: 2px solid var(--ink);
    margin-top: 0.3rem;
    padding-top: 0.8rem;
  }
  .line.result dt {
    font-family: var(--font-display);
    font-size: 1.1rem;
    font-weight: 600;
  }
  .line.result dd {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--ok);
  }
  .line.result.negative dd {
    color: var(--danger);
  }

  .margin-strip {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding: 0.85rem 1.4rem;
    border-top: 1px solid var(--line);
    background: rgba(47, 111, 79, 0.06);
  }
  .margin-strip.negative {
    background: rgba(168, 32, 26, 0.06);
  }
  .margin-label {
    font-size: 0.66rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .margin-value {
    font-size: 1.05rem;
    font-weight: 500;
    color: var(--ok);
  }
  .margin-strip.negative .margin-value {
    color: var(--danger);
  }

  @media (max-width: 560px) {
    .subtab .badge {
      display: none;
    }
    .head-tools {
      flex-direction: column;
      align-items: flex-end;
      gap: 0.4rem;
    }
  }
</style>
