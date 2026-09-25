/** Ordenação e filtro das tabelas do app.
 *
 *  Módulo puro de propósito: testável sem DOM, e mantém a Table.svelte
 *  só com renderização.
 *
 *  Regra central da ordenação: compara o valor BRUTO, nunca o formatado —
 *  "R$ 1.234,56" ordenado como texto põe 9 depois de 10. Já o FILTRO
 *  casa sobre o formatado, porque o usuário busca o que está vendo. */

export type Row = Record<string, unknown>;
export type SortDir = "asc" | "desc" | null;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}/;

export function normalize(s: string): string {
  return s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
}

function ausente(v: unknown): boolean {
  return v === null || v === undefined || v === "";
}

function asNumber(v: unknown): number | null {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string" && v.trim() !== "" && !ISO_DATE.test(v)) {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

/* ATENÇÃO — armadilha para quem for reordenar por fora deste módulo:
 * `compareValues` devolve ausente ("null"/"undefined"/"") sempre como
 * "maior" (1), de forma FIXA — sem nenhuma noção de direção. Essa regra
 * não pode ser invertida por um fator de "desc". A forma óbvia de simular
 * decrescente, `dir === "desc" ? -compareValues(a, b) : compareValues(a, b)`,
 * reintroduz o bug já corrigido em `sortRows`: no decrescente, os ausentes
 * sobem para o topo e enchem a tela de linhas em branco. Quem precisa
 * ordenar deve chamar `sortRows` (que isola a ausência do fator de direção)
 * — não reimplemente essa lógica multiplicando este retorno. */
export function compareValues(a: unknown, b: unknown): number {
  const aVazio = ausente(a);
  const bVazio = ausente(b);
  if (aVazio && bVazio) return 0;
  if (aVazio) return 1; // ausente sempre por último, independente de direção
  if (bVazio) return -1;

  const na = asNumber(a);
  const nb = asNumber(b);
  if (na !== null && nb !== null) return na - nb;

  const sa = String(a);
  const sb = String(b);
  if (ISO_DATE.test(sa) && ISO_DATE.test(sb)) return sa < sb ? -1 : sa > sb ? 1 : 0;

  return sa.localeCompare(sb, "pt-BR", { numeric: true, sensitivity: "base" });
}

export function sortRows(rows: Row[], key: string | null, dir: SortDir): Row[] {
  if (!key || dir === null) return rows;
  const fator = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const av = a[key];
    const bv = b[key];
    const aVazio = ausente(av);
    const bVazio = ausente(bv);
    // Ausente fica por último nas duas direções — por isso é tratado antes
    // de aplicar o fator, e não delegado ao compareValues (que embutiria
    // essa regra na comparação e o fator do "desc" a inverteria).
    if (aVazio && bVazio) return 0;
    if (aVazio) return 1;
    if (bVazio) return -1;
    return fator * compareValues(av, bv);
  });
}

export function filterRows(rows: Row[], text: string, haystack: (row: Row) => string): Row[] {
  const alvo = normalize(text.trim());
  if (!alvo) return rows;
  return rows.filter((r) => {
    // `haystack` é fornecido pelo chamador; uma linha com dado inesperado
    // (campo ausente derrubando a formatação, `haystack` lançando exceção,
    // ou um retorno que não vira string) não pode derrubar o filtro da
    // tabela inteira — mas também não pode simplesmente SUMIR da lista.
    // Estas telas (orçamentos, clientes, bobinas, contábil) são
    // escrituração: uma linha que desaparece da busca é indistinguível de
    // "não existe", e isso é invisível até o dinheiro não bater no fim do
    // mês. Uma linha espúria aparecendo é visível e investigável na hora —
    // por isso a linha inavaliável fica VISÍVEL, não excluída. O aviso no
    // console torna isso barulhento em desenvolvimento, em vez de silencioso
    // (inclusive para o caso de o próprio `haystack` ter um bug real, tipo
    // acessar uma propriedade com nome errado — sem o aviso, esse bug vira
    // exclusão silenciosa e fica invisível duas vezes).
    let valor: string;
    try {
      valor = String(haystack(r));
    } catch (err) {
      console.warn("filterRows: linha não pôde ser avaliada para busca; mantida visível", err);
      return true;
    }
    return normalize(valor).includes(alvo);
  });
}

export function nextDir(current: SortDir): SortDir {
  return current === null ? "asc" : current === "asc" ? "desc" : null;
}
