/** Formatadores pt-BR do app. Uma implementação de cada, com os objetos Intl
 *  instanciados uma vez no módulo — antes disto havia 14 definições
 *  concorrentes em 9 arquivos, com regras de nulo divergentes.
 *
 *  Regra única de ausência: null, undefined, "" e NaN viram DASH. */

export const DASH = "—";

const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

function toNumber(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function toDate(v: string | null | undefined): Date | null {
  if (!v) return null;
  // Data pura (YYYY-MM-DD) é construída como local para não recuar um dia
  // por fuso — o backend manda date sem hora em sold_at, incurred_at etc.
  const pure = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v);
  if (pure) return new Date(Number(pure[1]), Number(pure[2]) - 1, Number(pure[3]));
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

export function money(v: string | number | null | undefined): string {
  const n = toNumber(v);
  if (n === null) return DASH;
  // O ICU do Node (e alguns navegadores) usa NBSP (U+00A0) entre "R$" e o
  // valor; normalizamos para espaço comum para ter uma saída previsível.
  return BRL.format(n).replace(/\u00A0/g, " ");
}

export function date(v: string | null | undefined): string {
  const d = toDate(v);
  return d === null ? DASH : `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
}

export function dateTime(v: string | null | undefined): string {
  const d = toDate(v);
  if (d === null) return DASH;
  const ano = String(d.getFullYear()).slice(2);
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${ano} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function num(v: unknown, decimals = 2): string {
  const n = toNumber(v);
  if (n === null) return DASH;
  return n.toLocaleString("pt-BR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function dur(seconds: number | null | undefined): string {
  const n = toNumber(seconds);
  // Duração é a única exceção à regra "zero é valor, não ausência": uma
  // impressão não leva zero minutos, então time_s === 0 significa peça sem
  // gcode lido ainda (tempo não registrado), não um tempo real medido.
  if (n === null || n === 0) return DASH;
  const total = Math.round(n / 60);
  const h = Math.floor(total / 60);
  const m = total % 60;
  return h > 0 ? `${h}h ${m}min` : `${m}min`;
}

export function pct(v: unknown, decimals = 1): string {
  const n = toNumber(v);
  return n === null ? DASH : `${num(n, decimals)}%`;
}
