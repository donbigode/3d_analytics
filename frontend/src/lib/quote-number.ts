import { DASH } from "$lib/format";

/** Número humano do orçamento. O UUID segue sendo a chave em URLs e na API;
 *  isto é só o que a pessoa lê e fala em voz alta. */
export function quoteNumber(seq: number | null | undefined): string {
  if (seq === null || seq === undefined || !Number.isFinite(seq)) return DASH;
  return `#${String(seq).padStart(4, "0")}`;
}
