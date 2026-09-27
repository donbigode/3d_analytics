import { describe, expect, it } from "vitest";
import {
  delta,
  discardsOnLeave,
  enterMultiColor,
  filamentCostPerPiece,
  gcodeGrams,
  isMultiColor,
  leaveMultiColor,
  lineCost,
  linesSignature,
  sumGrams,
  toGrams,
  toPayload,
  whyNotSendable,
  withoutIndex,
} from "./filament-lines";

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

describe("linesSignature", () => {
  const vindas = [
    { id: "f1", material_id: "a", grams_unit: "12.34" },
    { id: "f2", material_id: "b", grams_unit: null },
  ];

  it("é igual para um ARRAY NOVO com o mesmo conteúdo", () => {
    // Esta é a propriedade que existe para um bug específico: a prop `filaments`
    // chega como array novo a cada invalidação do item, e o runtime do Svelte
    // trata todo array como "mudou" (safe_not_equal). Se a assinatura não
    // fosse igual aqui, o rascunho local continuaria sendo sobrescrito.
    const outroArray = vindas.map((f) => ({ ...f }));
    expect(outroArray).not.toBe(vindas);
    expect(linesSignature(outroArray)).toBe(linesSignature(vindas));
  });

  it("muda quando as gramas mudam", () => {
    const depois = [vindas[0], { ...vindas[1], grams_unit: "5.66" }];
    expect(linesSignature(depois)).not.toBe(linesSignature(vindas));
  });

  it("muda quando o material da linha muda, com o mesmo id", () => {
    // O caminho `material_code` reescreve a linha 1 no lugar, sem trocar o id.
    const depois = [{ ...vindas[0], material_id: "z" }, vindas[1]];
    expect(linesSignature(depois)).not.toBe(linesSignature(vindas));
  });

  it("muda quando o id da linha muda, com o mesmo material e gramas", () => {
    // O PUT apaga e recria as linhas, então os ids são novos — é assim que a
    // ressincronização depois de salvar continua acontecendo.
    const depois = [{ ...vindas[0], id: "f9" }, vindas[1]];
    expect(linesSignature(depois)).not.toBe(linesSignature(vindas));
  });

  it("muda quando a ordem muda", () => {
    // A ordem É a posição, então trocar duas cores de lugar é uma mudança.
    expect(linesSignature([vindas[1], vindas[0]])).not.toBe(linesSignature(vindas));
  });

  it("muda quando o número de linhas muda", () => {
    expect(linesSignature([vindas[0]])).not.toBe(linesSignature(vindas));
    expect(linesSignature([])).not.toBe(linesSignature(vindas));
  });
});

describe("toPayload", () => {
  it("manda material_id e as gramas como string", () => {
    const p = toPayload([{ material_id: "a", grams_unit: 12.34 }]);
    expect(p).toEqual([{ material_id: "a", grams_unit: "12.34" }]);
    // `Decimal` do outro lado: número viraria float no JSON.
    expect(typeof p[0].grams_unit).toBe("string");
  });

  it("não manda position, nem qualquer outra chave do rascunho", () => {
    // A ORDEM DA LISTA é a posição; `QuoteItemFilamentIn` não tem o campo.
    const rascunho = [
      { material_id: "a", grams_unit: 12.34, position: 1, gramasRaw: "12.34" },
      { material_id: "b", grams_unit: 5.66, position: 2, gramasRaw: "5.66" },
    ];
    const p = toPayload(rascunho);
    expect(Object.keys(p[0]).sort()).toEqual(["grams_unit", "material_id"]);
    expect(Object.keys(p[1]).sort()).toEqual(["grams_unit", "material_id"]);
    expect(JSON.stringify(p)).not.toContain("position");
    expect(JSON.stringify(p)).not.toContain("gramasRaw");
  });

  it("omite a chave grams_unit quando não há gramas — não manda null", () => {
    const p = toPayload([{ material_id: "a", grams_unit: null }]);
    expect(Object.keys(p[0])).toEqual(["material_id"]);
    expect("grams_unit" in p[0]).toBe(false);
    // `{material_id, grams_unit: undefined}` passaria num toEqual frouxo e
    // serializaria igual; a asserção acima é sobre a CHAVE existir.
    expect(JSON.stringify(p)).toBe('[{"material_id":"a"}]');
  });

  it("transforma 0 e negativo em ausência, nunca na string \"0\"", () => {
    // `grams_unit` tem `gt=0` no schema: um "0" que chegasse lá é 422, e pior,
    // um 0 aceito custaria zero em silêncio sem cair no fallback do gcode.
    expect(JSON.stringify(toPayload([{ material_id: "a", grams_unit: 0 }]))).toBe(
      '[{"material_id":"a"}]',
    );
    expect(JSON.stringify(toPayload([{ material_id: "a", grams_unit: -3 }]))).toBe(
      '[{"material_id":"a"}]',
    );
  });

  it("preserva a ordem das linhas, que é o que define a position", () => {
    const p = toPayload([
      { material_id: "c", grams_unit: 1 },
      { material_id: "a", grams_unit: 2 },
      { material_id: "b", grams_unit: 3 },
    ]);
    // Materiais e gramas distintos de propósito: com valores iguais, uma
    // implementação que ordenasse a lista passaria igual.
    expect(p.map((l) => l.material_id)).toEqual(["c", "a", "b"]);
    expect(p.map((l) => l.grams_unit)).toEqual(["1", "2", "3"]);
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

describe("enterMultiColor", () => {
  const cor1 = { material_id: "preto", gramasRaw: "12.34", position: 1 };

  it("acrescenta uma segunda linha em branco e preserva a primeira", () => {
    const r = enterMultiColor([cor1]);
    expect(r).toEqual([cor1, { material_id: "", gramasRaw: "", position: 2 }]);
  });

  it("é idempotente: chamar duas vezes não cria duas linhas em branco", () => {
    const uma = enterMultiColor([cor1]);
    const duas = enterMultiColor(uma);
    expect(duas).toHaveLength(2);
    expect(duas).toEqual(uma);
  });

  it("não mexe numa lista que já tem duas ou mais cores", () => {
    const tres = [
      cor1,
      { material_id: "ouro", gramasRaw: "5.67", position: 2 },
      { material_id: "branco", gramasRaw: "0.89", position: 3 },
    ];
    expect(enterMultiColor(tres)).toEqual(tres);
  });

  it("não muta a lista recebida", () => {
    const linhas = [cor1];
    enterMultiColor(linhas);
    expect(linhas).toEqual([cor1]);
  });
});

describe("leaveMultiColor", () => {
  it("mantém só a cor 1, com o material e as gramas dela", () => {
    const r = leaveMultiColor([
      { material_id: "preto", gramasRaw: "12.34", position: 1 },
      { material_id: "ouro", gramasRaw: "5.67", position: 2 },
      { material_id: "branco", gramasRaw: "0.89", position: 3 },
    ]);
    expect(r).toEqual([{ material_id: "preto", gramasRaw: "12.34", position: 1 }]);
  });

  it("devolve a lista de uma cor sem mudança", () => {
    const uma = [{ material_id: "preto", gramasRaw: "", position: 1 }];
    expect(leaveMultiColor(uma)).toEqual(uma);
  });
});

describe("discardsOnLeave", () => {
  it("é verdade quando uma cor além da 1 tem material", () => {
    expect(
      discardsOnLeave([
        { material_id: "preto", gramasRaw: "12", position: 1 },
        { material_id: "ouro", gramasRaw: "", position: 2 },
      ]),
    ).toBe(true);
  });

  it("é verdade quando uma cor além da 1 tem só gramas", () => {
    expect(
      discardsOnLeave([
        { material_id: "preto", gramasRaw: "12", position: 1 },
        { material_id: "", gramasRaw: "4", position: 2 },
      ]),
    ).toBe(true);
  });

  it("é falso quando só existe a linha em branco que o multicolor criou", () => {
    // Marcar e desmarcar em seguida não deve pedir confirmação: não há cor a perder.
    expect(
      discardsOnLeave([
        { material_id: "preto", gramasRaw: "12", position: 1 },
        { material_id: "", gramasRaw: "", position: 2 },
      ]),
    ).toBe(false);
  });

  it("é falso com uma cor só", () => {
    expect(discardsOnLeave([{ material_id: "preto", gramasRaw: "12", position: 1 }])).toBe(false);
  });
});

describe("isMultiColor", () => {
  it("flag marcado com uma linha é multicor", () => {
    expect(isMultiColor([{}], true)).toBe(true);
  });
  it("mais de uma linha é multicor mesmo com o flag desmarcado", () => {
    expect(isMultiColor([{}, {}], false)).toBe(true);
  });
  it("uma linha e flag desmarcado não é", () => {
    expect(isMultiColor([{}], false)).toBe(false);
  });
});

describe("lineCost / filamentCostPerPiece", () => {
  // Preços E gramas diferentes por linha: com gramas iguais, aplicar a média
  // dos preços daria a mesma soma e o teste não pegaria preço trocado.
  const materials = [
    { id: "preto", price_per_kg_ref: "100" },
    { id: "ouro", price_per_kg_ref: "450" },
    { id: "branco", price_per_kg_ref: 120 },
    { id: "sem-preco", price_per_kg_ref: "" },
  ];

  it("usa o preço do material da própria linha", () => {
    expect(lineCost({ material_id: "preto", grams_unit: 12 }, materials)).toBeCloseTo(1.2, 10);
    expect(lineCost({ material_id: "ouro", grams_unit: 5 }, materials)).toBeCloseTo(2.25, 10);
    expect(lineCost({ material_id: "branco", grams_unit: 1 }, materials)).toBeCloseTo(0.12, 10);
  });

  it("null sem gramas, sem material ou sem preço", () => {
    expect(lineCost({ material_id: "preto", grams_unit: null }, materials)).toBeNull();
    expect(lineCost({ material_id: "", grams_unit: 3 }, materials)).toBeNull();
    expect(lineCost({ material_id: "sumiu", grams_unit: 3 }, materials)).toBeNull();
    expect(lineCost({ material_id: "sem-preco", grams_unit: 3 }, materials)).toBeNull();
  });

  it("soma o custo de cada cor pelo preço de cada uma", () => {
    const soma = filamentCostPerPiece(
      [
        { material_id: "preto", grams_unit: 12 },
        { material_id: "ouro", grams_unit: 5 },
        { material_id: "branco", grams_unit: 1 },
      ],
      materials,
    );
    // 1,20 + 2,25 + 0,12. Média de preço × gramas totais daria 18 × 223,33/1000 = 4,02.
    expect(soma).toBeCloseTo(3.57, 10);
  });

  it("null se alguma cor não tem custo — não existe soma parcial honesta", () => {
    expect(
      filamentCostPerPiece(
        [
          { material_id: "preto", grams_unit: 12 },
          { material_id: "ouro", grams_unit: null },
        ],
        materials,
      ),
    ).toBeNull();
  });

  it("null com lista vazia", () => {
    expect(filamentCostPerPiece([], materials)).toBeNull();
  });
});
