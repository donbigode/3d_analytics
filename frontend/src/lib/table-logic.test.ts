import { describe, it, expect } from "vitest";
import { normalize, compareValues, sortRows, filterRows, nextDir } from "./table-logic";

describe("normalize", () => {
  it("remove acento e caixa", () => {
    expect(normalize("Orçamento PÚBLICO")).toBe("orcamento publico");
  });
  it("aguenta string vazia", () => {
    expect(normalize("")).toBe("");
  });
});

describe("compareValues", () => {
  it("compara números como números, não como texto", () => {
    expect(compareValues(9, 10)).toBeLessThan(0);
  });
  it("compara string numérica da API como número", () => {
    // Decimal serializado pelo backend chega como string
    expect(compareValues("9.00", "10.00")).toBeLessThan(0);
  });
  it("compara data ISO cronologicamente", () => {
    expect(compareValues("2026-09-02", "2026-09-10")).toBeLessThan(0);
  });
  it("compara texto com localeCompare pt-BR", () => {
    expect(compareValues("ácido", "azul")).toBeLessThan(0);
  });
  it("põe nulo por último", () => {
    expect(compareValues(null, 1)).toBeGreaterThan(0);
    expect(compareValues(1, null)).toBeLessThan(0);
  });
});

describe("sortRows", () => {
  const rows = [{ n: 10, s: "b" }, { n: 9, s: "a" }, { n: 11, s: "c" }];

  it("ordena crescente", () => {
    expect(sortRows(rows, "n", "asc").map((r) => r.n)).toEqual([9, 10, 11]);
  });
  it("ordena decrescente", () => {
    expect(sortRows(rows, "n", "desc").map((r) => r.n)).toEqual([11, 10, 9]);
  });
  it("devolve a ordem natural quando dir é null", () => {
    expect(sortRows(rows, "n", null).map((r) => r.n)).toEqual([10, 9, 11]);
  });
  it("não muta o array original", () => {
    sortRows(rows, "n", "asc");
    expect(rows.map((r) => r.n)).toEqual([10, 9, 11]);
  });

  // Caso não coberto explicitamente pelo brief: se compareValues() já devolve
  // valor ausente por último e sortRows apenas multiplica o resultado pelo
  // fator da direção, o fator inverte esse "por último" no decrescente e
  // ausentes aparecem primeiro. sortRows precisa tratar ausência à parte,
  // antes de aplicar o fator, para manter ausentes por último nas duas direções.
  it("põe ausente por último também no decrescente", () => {
    const comAusente = [{ n: 5 }, { n: null }, { n: 1 }, { n: undefined }, { n: 3 }];
    expect(sortRows(comAusente, "n", "desc").map((r) => r.n)).toEqual([
      5,
      3,
      1,
      null,
      undefined,
    ]);
  });
});

describe("filterRows", () => {
  const rows = [
    { id: 1, texto: "R$ 1.234,56 · Maria Silva" },
    { id: 2, texto: "R$ 99,00 · João Ançã" },
  ];
  const hay = (r: Record<string, unknown>) => String(r.texto);

  it("casa sobre o valor formatado", () => {
    expect(filterRows(rows, "1.234", hay).map((r) => r.id)).toEqual([1]);
  });
  it("ignora acento e caixa", () => {
    expect(filterRows(rows, "anca", hay).map((r) => r.id)).toEqual([2]);
    expect(filterRows(rows, "MARIA", hay).map((r) => r.id)).toEqual([1]);
  });
  it("texto vazio devolve tudo", () => {
    expect(filterRows(rows, "", hay)).toHaveLength(2);
  });
  it("sem casamento devolve vazio", () => {
    expect(filterRows(rows, "zzz", hay)).toHaveLength(0);
  });
});

describe("nextDir", () => {
  it("cicla asc → desc → null → asc", () => {
    expect(nextDir(null)).toBe("asc");
    expect(nextDir("asc")).toBe("desc");
    expect(nextDir("desc")).toBe(null);
  });
});
