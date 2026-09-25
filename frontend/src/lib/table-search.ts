/** Conta quantas linhas passam no mesmo filtro que a <Table> aplica por
 *  baixo dos panos, para alimentar o contador "N de M" do <SearchBar>.
 *
 *  Replica a mesma formatação por coluna que Table.svelte usa para montar
 *  o haystack da busca (texto renderizado, não valor bruto — ver o
 *  cabeçalho de table-logic.ts). Mantida separada da Table para não editar
 *  um componente já pronto e testado por outra tarefa; se o comportamento
 *  de busca da Table mudar, este arquivo precisa acompanhar. */
import { filterRows, type Row } from "./table-logic";
import { DASH } from "./format";

export type SearchColumn = {
  key: string;
  format?: (v: unknown, row: Row) => string;
};

function displayForSearch(col: SearchColumn, row: Row): string {
  const v = row[col.key];
  if (col.format) {
    try {
      return col.format(v, row);
    } catch {
      return DASH; // Table também mantém a linha visível nesse caso.
    }
  }
  if (v === null || v === undefined || v === "") return DASH;
  return String(v);
}

export function countShown(
  rows: Row[],
  searchText: string,
  columns: SearchColumn[],
  searchExtra?: (row: Row) => string,
): number {
  const haystack = (row: Row): string => {
    const cols = columns.map((c) => displayForSearch(c, row)).join(" ");
    return searchExtra ? `${cols} ${searchExtra(row)}` : cols;
  };
  return filterRows(rows, searchText, haystack).length;
}
