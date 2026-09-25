import { describe, it, expect } from "vitest";
import { countShown, type SearchColumn } from "./table-search";
import type { Row } from "./table-logic";

const columns: SearchColumn[] = [
  { key: "name" },
  { key: "total", format: (v) => `R$ ${v}` },
];

const rows: Row[] = [
  { id: "1", name: "Alice", total: "10.00" },
  { id: "2", name: "Bob", total: "20.00" },
];

describe("countShown", () => {
  it("sem busca, conta tudo", () => {
    expect(countShown(rows, "", columns)).toBe(2);
  });

  it("casa sobre o texto já formatado (dinheiro), não o valor bruto", () => {
    expect(countShown(rows, "R$ 10", columns)).toBe(1);
  });

  it("ignora acento/caixa igual ao filtro da Table", () => {
    expect(countShown(rows, "alice", columns)).toBe(1);
  });

  it("inclui searchExtra na contagem", () => {
    const extra = (row: Row) => String(row.notes ?? "");
    const withNotes: Row[] = [{ id: "1", name: "Alice", total: "10.00", notes: "urgente" }];
    expect(countShown(withNotes, "urgente", columns, extra)).toBe(1);
    expect(countShown(withNotes, "inexistente", columns, extra)).toBe(0);
  });

  it("format() que lança não derruba a contagem — linha some do count 0? não: mantém visível", () => {
    const boom: SearchColumn[] = [
      { key: "x", format: () => { throw new Error("boom"); } },
    ];
    expect(countShown([{ id: "1" }], "", boom)).toBe(1);
  });
});
