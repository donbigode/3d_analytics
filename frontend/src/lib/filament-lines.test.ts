import { describe, expect, it } from "vitest";
import { delta, gcodeGrams, sumGrams, toGrams, whyNotSendable, withoutIndex } from "./filament-lines";

describe("toGrams", () => {
  it("aceita o decimal em string que a API manda", () => {
    // QuoteItemFilamentOut.grams_unit é Decimal no pydantic, e chega "12.34".
    expect(toGrams("12.34")).toBe(12.34);
  });

  it("devolve null para ausência — null, vazio e lixo", () => {
    expect(toGrams(null)).toBeNull();
    expect(toGrams(undefined)).toBeNull();
    expect(toGrams("")).toBeNull();
    expect(toGrams("abc")).toBeNull();
  });

  it("devolve null para zero e negativo", () => {
    // O schema rejeita grams_unit <= 0 (gt=0). Um campo limpo tem que virar
    // null — mandar 0 seria 422, e pior: um 0 aceito custaria zero em silêncio.
    expect(toGrams("0")).toBeNull();
    expect(toGrams(0)).toBeNull();
    expect(toGrams(-3)).toBeNull();
  });
});

describe("sumGrams", () => {
  it("soma as gramas das linhas", () => {
    expect(sumGrams([{ grams_unit: 12.34 }, { grams_unit: 5.66 }])).toBe(18);
  });

  it("devolve null quando alguma linha não tem gramas", () => {
    // Não existe soma parcial honesta: mostrar 12,34 quando falta uma linha
    // sugere que o total é 12,34.
    expect(sumGrams([{ grams_unit: 12.34 }, { grams_unit: null }])).toBeNull();
    // E não importa a ordem: a linha vazia pode ser a primeira.
    expect(sumGrams([{ grams_unit: null }, { grams_unit: 12.34 }])).toBeNull();
  });

  it("devolve null para lista vazia, não 0", () => {
    expect(sumGrams([])).toBeNull();
  });

  it("soma três linhas com valores distintos", () => {
    // Valores diferentes de propósito: com gramas iguais, uma soma trocada por
    // (primeira × n) passaria igual.
    expect(sumGrams([{ grams_unit: 12.34 }, { grams_unit: 5.67 }, { grams_unit: 0.89 }])).toBe(18.9);
  });
});

describe("delta", () => {
  it("é a diferença entre a soma e o gcode", () => {
    expect(delta(18.9, 18.9)).toBe(0);
    expect(delta(20, 18.9)).toBeCloseTo(1.1);
  });

  it("é negativo quando a soma digitada é menor que o gcode", () => {
    expect(delta(17.9, 18.9)).toBeCloseTo(-1);
  });

  it("é null quando a soma é null", () => {
    expect(delta(null, 18.9)).toBeNull();
  });
});

describe("gcodeGrams", () => {
  it("usa filament_g quando existe, ignorando os metros", () => {
    // Os dois campos discordam de propósito: com valores iguais, uma
    // implementação que derivasse sempre dos metros passaria do mesmo jeito.
    expect(gcodeGrams({ filament_g: 42.5, filament_m: 10 }, 1.24)).toBe(42.5);
  });

  it("cai nos metros quando filament_g é 0 ou ausente", () => {
    // Espelha effective_grams_per_unit do backend, que exige filament_g > 0:
    // 0 é campo não preenchido, não uma peça de zero grama.
    expect(gcodeGrams({ filament_g: 0, filament_m: 10 }, 1.24)).toBe(29.83);
    expect(gcodeGrams({ filament_m: 10 }, 1.24)).toBe(29.83);
    expect(gcodeGrams({ filament_g: null, filament_m: 10 }, 1.24)).toBe(29.83);
  });

  it("a densidade muda o derivado dos metros", () => {
    // PETG (1.27) não pesa o mesmo que PLA (1.24) para a mesma metragem.
    expect(gcodeGrams({ filament_m: 10 }, 1.27)).toBe(30.55);
  });

  it("é 0 quando o gcode não trouxe nem metros nem gramas", () => {
    expect(gcodeGrams({}, 1.24)).toBe(0);
    expect(gcodeGrams({ filament_m: null, filament_g: null }, 1.24)).toBe(0);
  });
});

describe("whyNotSendable", () => {
  it("deixa passar uma cor só sem gramas — NULL é 'derive do gcode'", () => {
    expect(whyNotSendable([{ material_id: "a", grams_unit: null }])).toBeNull();
  });

  it("deixa passar duas cores com gramas nas duas", () => {
    expect(
      whyNotSendable([
        { material_id: "a", grams_unit: 12.34 },
        { material_id: "b", grams_unit: 5.66 },
      ]),
    ).toBeNull();
  });

  it("barra a lista vazia", () => {
    expect(whyNotSendable([])).toBe("vazio");
  });

  it("barra linha sem material", () => {
    expect(whyNotSendable([{ material_id: "", grams_unit: 12.34 }])).toBe("material");
  });

  it("barra a segunda cor sem gramas, em qualquer posição", () => {
    // Invariante 3 do servidor. A que falta é a segunda…
    expect(
      whyNotSendable([
        { material_id: "a", grams_unit: 12.34 },
        { material_id: "b", grams_unit: null },
      ]),
    ).toBe("gramas");
    // …e também quando a que falta é a primeira, que é o caso real de um item
    // de uma cor (grams NULL) que acabou de ganhar a segunda.
    expect(
      whyNotSendable([
        { material_id: "a", grams_unit: null },
        { material_id: "b", grams_unit: 5.66 },
      ]),
    ).toBe("gramas");
  });

  it("material sem escolher ganha das gramas faltando", () => {
    // Ordem importa para a mensagem: sem material escolhido, cobrar gramas
    // seria cobrar a coisa errada primeiro.
    expect(
      whyNotSendable([
        { material_id: "a", grams_unit: null },
        { material_id: "", grams_unit: null },
      ]),
    ).toBe("material");
  });
});

describe("withoutIndex", () => {
  it("remove e renumera", () => {
    const linhas = [
      { position: 1, material_id: "a" },
      { position: 2, material_id: "b" },
      { position: 3, material_id: "c" },
    ];
    expect(withoutIndex(linhas, 1)).toEqual([
      { position: 1, material_id: "a" },
      { position: 2, material_id: "c" },
    ]);
  });

  it("renumera a partir de 1 quando a removida é a position=1", () => {
    // Não é só o tamanho que importa: se o position não fosse reescrito, a
    // lista sobrevivente começaria em 2 e a linha 1 — a que manda no
    // material_version_id do item — não existiria mais.
    const linhas = [
      { position: 1, material_id: "a" },
      { position: 2, material_id: "b" },
      { position: 3, material_id: "c" },
    ];
    expect(withoutIndex(linhas, 0).map((l) => l.position)).toEqual([1, 2]);
    expect(withoutIndex(linhas, 0).map((l) => l.material_id)).toEqual(["b", "c"]);
  });

  it("não remove a última linha", () => {
    const uma = [{ position: 1, material_id: "a" }];
    expect(withoutIndex(uma, 0)).toEqual(uma);
  });

  it("não mexe na lista quando o índice não existe", () => {
    const linhas = [
      { position: 1, material_id: "a" },
      { position: 2, material_id: "b" },
    ];
    expect(withoutIndex(linhas, 5)).toEqual(linhas);
    expect(withoutIndex(linhas, -1)).toEqual(linhas);
  });

  it("não muta a lista recebida", () => {
    const linhas = [
      { position: 1, material_id: "a" },
      { position: 2, material_id: "b" },
      { position: 3, material_id: "c" },
    ];
    withoutIndex(linhas, 0);
    expect(linhas.map((l) => l.position)).toEqual([1, 2, 3]);
    expect(linhas).toHaveLength(3);
  });
});
