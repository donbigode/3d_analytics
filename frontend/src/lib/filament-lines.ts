/** Lógica pura das linhas de filamento de um item (uma linha por cor).
 *
 *  Vive fora do .svelte de propósito: o Vitest deste projeto roda com
 *  `environment: "node"` e sem jsdom, então nada dentro de um componente é
 *  testável. O que der para calcular aqui, calcula-se aqui.
 *
 *  Espelha o backend em dois pontos que não podem divergir:
 *  - `gcodeGrams` reproduz `effective_grams_per_unit` + `grams_from_meters`
 *    (backend/core/quote_service.py, backend/core/pricing/cost.py): gramas
 *    preenchidas e > 0 ganham dos metros, e sem refugo (spec 3.3).
 *  - `toGrams` reproduz a guarda `gt=0` de `QuoteItemFilamentIn.grams_unit`:
 *    campo vazio é `null` ("derive do gcode"), nunca `0`. */

/** Diâmetro nominal do filamento, em mm — o mesmo default do backend. */
export const DIAMETRO_MM = 1.75;

/** Gramas se exibem e se digitam com duas casas; arredondar aqui evita que
 *  12,34 + 5,66 apareça como 18,000000000000004 no rodapé. */
function casas2(n: number): number {
  return Math.round(n * 100) / 100;
}

/** Converte o que veio da API (Decimal serializado em string) ou do input
 *  para gramas utilizáveis. `null` significa "não informado". */
export function toGrams(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n) || n <= 0) return null;
  return n;
}

/** Soma as gramas por peça das linhas.
 *
 *  `null` quando a lista está vazia ou quando alguma linha não tem gramas:
 *  não há soma parcial honesta. Mostrar 12,34 num item de duas cores em que
 *  só a primeira foi preenchida afirma que o item pesa 12,34 g. */
export function sumGrams(lines: readonly { grams_unit?: number | null }[]): number | null {
  if (lines.length === 0) return null;
  let total = 0;
  for (const l of lines) {
    if (l.grams_unit === null || l.grams_unit === undefined) return null;
    total += l.grams_unit;
  }
  return casas2(total);
}

/** Gramas por peça derivadas do gcode — o valor cinza que a tela mostra numa
 *  linha sem gramas digitadas. Sem refugo: é o número do fatiador, não o
 *  número de custo. */
export function gcodeGrams(gcodeMeta: Record<string, unknown>, density: number): number {
  const gramas = Number(gcodeMeta.filament_g);
  if (Number.isFinite(gramas) && gramas > 0) return gramas;
  const metros = Number(gcodeMeta.filament_m);
  if (!Number.isFinite(metros) || metros <= 0) return 0;
  const areaMm2 = Math.PI * (DIAMETRO_MM / 2) ** 2;
  return casas2(metros * areaMm2 * density);
}

/** Diferença entre a soma digitada e o número do gcode. Informativo: o gcode
 *  é estimativa, o digitado é medição, e a spec (3.5) manda não bloquear. */
export function delta(soma: number | null, gcode: number): number | null {
  if (soma === null) return null;
  return casas2(soma - gcode);
}

/** Por que a lista ainda não pode ir para o servidor, ou `null` se pode.
 *
 *  Espelha as três rejeições 400 da rota (Task 7) para que a tela marque o
 *  campo em vez de descobrir pelo erro do servidor:
 *  - `"vazio"`: item sem linha nenhuma;
 *  - `"material"`: alguma linha sem material escolhido;
 *  - `"gramas"`: item de mais de uma cor com alguma linha sem gramas
 *    (invariante 3 — o gcode é um número do item inteiro e não sabe dividir).
 *
 *  Um item de UMA cor sem gramas é válido: `grams_unit` NULL significa
 *  "derive do gcode" (spec 3.4). */
export type Bloqueio = "vazio" | "material" | "gramas" | null;

export function whyNotSendable(
  lines: readonly { material_id: string; grams_unit: number | null }[],
): Bloqueio {
  if (lines.length === 0) return "vazio";
  if (lines.some((l) => l.material_id === "")) return "material";
  if (lines.length > 1 && lines.some((l) => l.grams_unit === null)) return "gramas";
  return null;
}

/** Remove a linha `i` e renumera as sobreviventes a partir de 1.
 *
 *  Recusa-se a remover a última linha (invariante 1: item sem linha nenhuma é
 *  400 no servidor) e um índice que não existe — nos dois casos devolve a
 *  lista recebida, sem mutá-la. O renumerar não é cosmético: `position` 1 é a
 *  linha que manda no `material_version_id` do item. */
export function withoutIndex<T extends { position: number }>(lines: readonly T[], i: number): T[] {
  if (lines.length <= 1) return [...lines];
  if (i < 0 || i >= lines.length) return [...lines];
  return lines
    .filter((_, idx) => idx !== i)
    .map((l, idx) => ({ ...l, position: idx + 1 }));
}
