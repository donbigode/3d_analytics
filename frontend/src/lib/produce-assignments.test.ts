import { describe, expect, it } from "vitest";
import {
  debitGrams,
  fillMissing,
  missingAssignments,
  preselectSignature,
  preselectSpools,
  spoolsForLine,
  toConsumption,
} from "./produce-assignments";
import type { BobinaProduzir, ItemProduzir, LinhaProduzir } from "./produce-assignments";

// ---- fixtures -------------------------------------------------------------

const MV_PRETO = "mv-preto";
const MV_DOURADO = "mv-dourado";

function linha(id: string, material_id: string): LinhaProduzir {
  return { id, material_id };
}

function bobina(over: Partial<BobinaProduzir> & { id: string }): BobinaProduzir {
  return {
    status: "open",
    material_type: "PLA",
    material_version_id: null,
    remaining_grams: "1000",
    ...over,
  };
}

// ---- preselectSpools ------------------------------------------------------

describe("preselectSpools", () => {
  it("chaveia pelo id da LINHA e casa pelo material_version_id", () => {
    const linhas = [linha("l1", MV_PRETO), linha("l2", MV_DOURADO)];
    const bobinas = [
      bobina({ id: "sp-preto", material_version_id: MV_PRETO }),
      bobina({ id: "sp-dourado", material_version_id: MV_DOURADO }),
    ];
    // A chave é o id da linha, não o do item: é o que o payload manda em
    // quote_item_filament_id, e é único no banco inteiro.
    expect(preselectSpools(linhas, bobinas)).toEqual({
      l1: "sp-preto",
      l2: "sp-dourado",
    });
  });

  it("IGNORA bobina de material_version_id nulo mesmo com material_type igual", () => {
    // O caso que distingue casamento por VÍNCULO de casamento por TIPO. O
    // backfill da 0035 deixou material_version_id NULL em toda bobina que não
    // casou com certeza; adivinhar por "é PLA também" debita a cor errada.
    const linhas = [linha("l1", MV_PRETO)];
    const bobinas = [
      bobina({ id: "sp-sem-vinculo", material_type: "PLA", material_version_id: null }),
    ];
    const r = preselectSpools(linhas, bobinas);
    expect(r.l1).toBeUndefined();
    expect(r).toEqual({});
  });

  it("não pré-seleciona a bobina de tipo igual quando existe a vinculada", () => {
    // Variação do caso acima com as duas bobinas presentes: sem o vínculo
    // exato, um `find` por material_type pegaria a PRIMEIRA — a errada.
    const linhas = [linha("l1", MV_DOURADO)];
    const bobinas = [
      bobina({ id: "sp-sem-vinculo", material_type: "PLA", material_version_id: null }),
      bobina({ id: "sp-dourado", material_type: "PLA", material_version_id: MV_DOURADO }),
    ];
    expect(preselectSpools(linhas, bobinas).l1).toBe("sp-dourado");
  });

  it("exclui bobina zerada mesmo com o vínculo certo", () => {
    const linhas = [linha("l1", MV_PRETO)];
    const bobinas = [
      bobina({ id: "sp-vazia", material_version_id: MV_PRETO, remaining_grams: "0" }),
    ];
    expect(preselectSpools(linhas, bobinas).l1).toBeUndefined();
  });

  it("exclui bobina zerada e escolhe a que ainda tem filamento", () => {
    const linhas = [linha("l1", MV_PRETO)];
    const bobinas = [
      bobina({ id: "sp-vazia", material_version_id: MV_PRETO, remaining_grams: "0" }),
      bobina({ id: "sp-cheia", material_version_id: MV_PRETO, remaining_grams: "820.50" }),
    ];
    expect(preselectSpools(linhas, bobinas).l1).toBe("sp-cheia");
  });

  it("exclui bobina que não está aberta", () => {
    const linhas = [linha("l1", MV_PRETO)];
    const bobinas = [
      bobina({ id: "sp-descartada", material_version_id: MV_PRETO, status: "discarded" }),
      bobina({ id: "sp-empty", material_version_id: MV_PRETO, status: "empty" }),
    ];
    expect(preselectSpools(linhas, bobinas)).toEqual({});
  });

  it("duas linhas da mesma cor recebem a MESMA bobina", () => {
    // Comportamento esperado: o servidor debita duas vezes da mesma bobina, e
    // é isso que acontece de verdade na impressora.
    const linhas = [linha("l1", MV_PRETO), linha("l2", MV_PRETO)];
    const bobinas = [bobina({ id: "sp-preto", material_version_id: MV_PRETO })];
    expect(preselectSpools(linhas, bobinas)).toEqual({ l1: "sp-preto", l2: "sp-preto" });
  });

  it("é determinística: a ordem em que a API devolveu não muda a escolha", () => {
    const linhas = [linha("l1", MV_PRETO)];
    const a = bobina({ id: "sp-a", material_version_id: MV_PRETO, remaining_grams: "300" });
    const b = bobina({ id: "sp-b", material_version_id: MV_PRETO, remaining_grams: "900" });
    // Duas candidatas igualmente válidas: sem ordenação, o resultado seria a
    // primeira da lista — e a lista vem ordenada por purchased_at.
    expect(preselectSpools(linhas, [a, b]).l1).toBe("sp-b");
    expect(preselectSpools(linhas, [b, a]).l1).toBe("sp-b");
  });

  it("desempata por id quando as gramas restantes são iguais", () => {
    const linhas = [linha("l1", MV_PRETO)];
    const a = bobina({ id: "sp-aaa", material_version_id: MV_PRETO, remaining_grams: "500" });
    const b = bobina({ id: "sp-bbb", material_version_id: MV_PRETO, remaining_grams: "500" });
    expect(preselectSpools(linhas, [a, b]).l1).toBe("sp-aaa");
    expect(preselectSpools(linhas, [b, a]).l1).toBe("sp-aaa");
  });

  it("não muta as listas recebidas", () => {
    const linhas = Object.freeze([linha("l1", MV_PRETO)]);
    const bobinas = Object.freeze([
      bobina({ id: "sp-b", material_version_id: MV_PRETO, remaining_grams: "100" }),
      bobina({ id: "sp-a", material_version_id: MV_PRETO, remaining_grams: "900" }),
    ]);
    preselectSpools(linhas, bobinas);
    // A ordenação tem de acontecer numa cópia: `spools` é o array do store de
    // refs, e reordená-lo no lugar mexeria na ordem do <select> de todas as
    // linhas e da tela de estoque.
    expect(bobinas.map((s) => s.id)).toEqual(["sp-b", "sp-a"]);
  });

  it("toda bobina pré-selecionada está entre as opções oferecidas na linha", () => {
    // Invariante que impede um <select> com valor fora das <option>: se a
    // pré-seleção pudesse escolher algo que o dropdown filtra, a tela
    // mostraria "—" com um valor escondido embaixo.
    const l = linha("l1", MV_PRETO);
    const bobinas = [
      // Vínculo certo, mas o texto do tipo está diferente (PLA+ vs PLA).
      bobina({ id: "sp-linkada", material_type: "PLA+", material_version_id: MV_PRETO }),
    ];
    const escolhida = preselectSpools([l], bobinas).l1;
    expect(escolhida).toBe("sp-linkada");
    expect(spoolsForLine(bobinas, l, "PLA").map((s) => s.id)).toContain(escolhida);
  });
});

// ---- spoolsForLine --------------------------------------------------------

describe("spoolsForLine", () => {
  const l = linha("l1", MV_PRETO);

  it("oferece as bobinas abertas do tipo da linha", () => {
    const bobinas = [
      bobina({ id: "pla", material_type: "PLA" }),
      bobina({ id: "petg", material_type: "PETG" }),
    ];
    expect(spoolsForLine(bobinas, l, "PLA").map((s) => s.id)).toEqual(["pla"]);
  });

  it("oferece a bobina vinculada mesmo quando o tipo está escrito diferente", () => {
    const bobinas = [bobina({ id: "linkada", material_type: "PLA+", material_version_id: MV_PRETO })];
    expect(spoolsForLine(bobinas, l, "PLA").map((s) => s.id)).toEqual(["linkada"]);
  });

  it("exclui bobina que não está aberta", () => {
    const bobinas = [
      bobina({ id: "aberta", material_type: "PLA" }),
      bobina({ id: "vazia", material_type: "PLA", status: "empty" }),
    ];
    expect(spoolsForLine(bobinas, l, "PLA").map((s) => s.id)).toEqual(["aberta"]);
  });

  it("oferece todas as abertas quando o tipo da linha é desconhecido", () => {
    // Material não encontrado na lista local: filtrar por tipo esconderia
    // tudo e deixaria a pessoa sem como produzir.
    const bobinas = [
      bobina({ id: "pla", material_type: "PLA" }),
      bobina({ id: "petg", material_type: "PETG" }),
    ];
    expect(spoolsForLine(bobinas, l, null).map((s) => s.id)).toEqual(["pla", "petg"]);
  });

  it("preserva a ordem da API (compra mais recente primeiro)", () => {
    const bobinas = [bobina({ id: "nova" }), bobina({ id: "velha" })];
    expect(spoolsForLine(bobinas, l, "PLA").map((s) => s.id)).toEqual(["nova", "velha"]);
  });

  it("mantém zerada-mas-aberta na lista, para escolha manual", () => {
    // Zerada não é PRÉ-selecionada, mas continua escolhível: o servidor é que
    // decide se dá pra debitar, e esconder a bobina só esconde o motivo.
    const bobinas = [bobina({ id: "quase", material_type: "PLA", remaining_grams: "0" })];
    expect(spoolsForLine(bobinas, l, "PLA").map((s) => s.id)).toEqual(["quase"]);
  });
});

// ---- fillMissing ----------------------------------------------------------

describe("fillMissing", () => {
  it("preenche só as chaves ausentes", () => {
    expect(fillMissing({ l1: "sp-a" }, { l1: "sp-preselecionada", l2: "sp-b" })).toEqual({
      l1: "sp-a",
      l2: "sp-b",
    });
  });

  it("NUNCA sobrescreve escolha do usuário", () => {
    // O bug da Task 10 na outra direção: um `$:` que re-roda e apaga o que a
    // pessoa acabou de escolher. Aqui a garantia é estrutural.
    const escolha = { l1: "escolhida-a-mao" };
    expect(fillMissing(escolha, { l1: "sugerida" })).toEqual({ l1: "escolhida-a-mao" });
  });

  it("respeita o vazio como escolha deliberada", () => {
    // Voltar o select para "—" é uma escolha; repreencher brigaria com ela.
    expect(fillMissing({ l1: "" }, { l1: "sugerida" })).toEqual({ l1: "" });
  });

  it("devolve objeto novo sem mutar o recebido", () => {
    const atuais = { l1: "sp-a" };
    const saida = fillMissing(atuais, { l2: "sp-b" });
    expect(atuais).toEqual({ l1: "sp-a" });
    expect(saida).not.toBe(atuais);
  });
});

// ---- preselectSignature ---------------------------------------------------

describe("preselectSignature", () => {
  const linhas = [linha("l1", MV_PRETO)];

  it("é igual para valores iguais em arrays de identidade diferente", () => {
    // É o que torna o portão uma comparação de verdade: `safe_not_equal`
    // devolve true para qualquer array, então o gate precisa ser string.
    const a = preselectSignature(linhas, [bobina({ id: "sp", material_version_id: MV_PRETO })]);
    const b = preselectSignature([linha("l1", MV_PRETO)], [
      bobina({ id: "sp", material_version_id: MV_PRETO }),
    ]);
    expect(a).toBe(b);
    expect(typeof a).toBe("string");
  });

  it("muda quando as gramas restantes de uma bobina mudam", () => {
    const antes = preselectSignature(linhas, [
      bobina({ id: "sp", material_version_id: MV_PRETO, remaining_grams: "1000" }),
    ]);
    const depois = preselectSignature(linhas, [
      bobina({ id: "sp", material_version_id: MV_PRETO, remaining_grams: "0" }),
    ]);
    expect(depois).not.toBe(antes);
  });

  it("muda quando entra uma linha nova", () => {
    const bobinas = [bobina({ id: "sp", material_version_id: MV_PRETO })];
    expect(preselectSignature([...linhas, linha("l2", MV_DOURADO)], bobinas)).not.toBe(
      preselectSignature(linhas, bobinas),
    );
  });
});

// ---- toConsumption --------------------------------------------------------

const ITEM_BICOLOR: ItemProduzir = {
  id: "it-bicolor",
  quantity: 2,
  filaments: [linha("l1", MV_PRETO), linha("l2", MV_DOURADO)],
};
const ITEM_UMA_COR: ItemProduzir = {
  id: "it-simples",
  quantity: 1,
  filaments: [linha("l3", MV_PRETO)],
};

describe("toConsumption", () => {
  it("emite UMA entrada por linha, com quote_item_filament_id em todas", () => {
    // A lista tem um item de 2 cores E um de 1 cor de propósito: se alguém
    // voltar a emitir por ITEM, o total cai de 3 para 2 e o teste quebra.
    const saida = toConsumption([ITEM_BICOLOR, ITEM_UMA_COR], {
      l1: "sp-preto",
      l2: "sp-dourado",
      l3: "sp-preto",
    });
    expect(saida).toEqual([
      { quote_item_id: "it-bicolor", spool_id: "sp-preto", quote_item_filament_id: "l1" },
      { quote_item_id: "it-bicolor", spool_id: "sp-dourado", quote_item_filament_id: "l2" },
      { quote_item_id: "it-simples", spool_id: "sp-preto", quote_item_filament_id: "l3" },
    ]);
  });

  it("nunca omite quote_item_filament_id, nem no item de uma cor", () => {
    // Omitir no item de uma cor "funcionaria" (o servidor cai em linhas[0]),
    // mas é o campo que impede o 409 e a baixa de N× — mandar sempre.
    const saida = toConsumption([ITEM_BICOLOR, ITEM_UMA_COR], {});
    expect(saida).toHaveLength(3);
    for (const c of saida) {
      expect(c.quote_item_filament_id).toBeTruthy();
    }
  });

  it("deixa spool_id vazio quando a linha não tem bobina escolhida", () => {
    const saida = toConsumption([ITEM_UMA_COR], {});
    expect(saida).toEqual([
      { quote_item_id: "it-simples", spool_id: "", quote_item_filament_id: "l3" },
    ]);
  });

  it("manda as gramas de override POR LINHA", () => {
    const saida = toConsumption([ITEM_BICOLOR], { l1: "sp-a", l2: "sp-b" }, {
      gramasPorLinha: { l1: "20", l2: "16" },
    });
    expect(saida[0].grams).toBe("20");
    expect(saida[1].grams).toBe("16");
    // Uma linha com override não contamina a outra sem override.
    const soUma = toConsumption([ITEM_BICOLOR], { l1: "sp-a", l2: "sp-b" }, {
      gramasPorLinha: { l1: "20" },
    });
    expect(soUma[0].grams).toBe("20");
    expect(soUma[1].grams).toBeUndefined();
  });

  it("gramas têm precedência sobre metros", () => {
    const saida = toConsumption([ITEM_UMA_COR], { l3: "sp" }, {
      gramasPorLinha: { l3: "33" },
      metrosPorItem: { "it-simples": "12" },
    });
    expect(saida[0].grams).toBe("33");
    expect(saida[0].filament_m).toBeUndefined();
  });

  it("manda metros como number, que é o tipo do schema", () => {
    const saida = toConsumption([ITEM_UMA_COR], { l3: "sp" }, {
      metrosPorItem: { "it-simples": "12.5" },
    });
    expect(saida[0].filament_m).toBe(12.5);
    expect(saida[0].grams).toBeUndefined();
  });

  it("ignora override vazio, zero e lixo", () => {
    const saida = toConsumption([ITEM_UMA_COR], { l3: "sp" }, {
      gramasPorLinha: { l3: "0" },
      metrosPorItem: { "it-simples": "abc" },
    });
    expect(saida[0].grams).toBeUndefined();
    expect(saida[0].filament_m).toBeUndefined();
  });

  it("NÃO manda metros para item de mais de uma cor", () => {
    // `filament_m` é campo do ITEM e o servidor o persiste no gcode_meta; num
    // item multicor ele não representa cor nenhuma (achado da Task 8).
    const saida = toConsumption([ITEM_BICOLOR], { l1: "sp", l2: "sp" }, {
      metrosPorItem: { "it-bicolor": "40" },
    });
    expect(saida[0].filament_m).toBeUndefined();
    expect(saida[1].filament_m).toBeUndefined();
  });

  it("ignora item sem linha nenhuma em vez de emitir baixa sem cor", () => {
    const saida = toConsumption([{ id: "it-pendente", quantity: 1 }, ITEM_UMA_COR], { l3: "sp" });
    expect(saida.map((c) => c.quote_item_id)).toEqual(["it-simples"]);
  });
});

// ---- missingAssignments ---------------------------------------------------

describe("missingAssignments", () => {
  it("devolve os IDS das linhas sem bobina, não um booleano", () => {
    // A tela tem de apontar QUAL cor falta; um booleano só diz que algo falta.
    expect(missingAssignments([ITEM_BICOLOR, ITEM_UMA_COR], { l2: "sp-dourado" })).toEqual([
      "l1",
      "l3",
    ]);
  });

  it("conta string vazia como falta", () => {
    expect(missingAssignments([ITEM_UMA_COR], { l3: "" })).toEqual(["l3"]);
  });

  it("devolve lista vazia quando todas as linhas têm bobina", () => {
    expect(
      missingAssignments([ITEM_BICOLOR, ITEM_UMA_COR], { l1: "a", l2: "b", l3: "c" }),
    ).toEqual([]);
  });

  it("segue a ordem de item e position", () => {
    expect(missingAssignments([ITEM_BICOLOR, ITEM_UMA_COR], {})).toEqual(["l1", "l2", "l3"]);
  });
});

// ---- debitGrams -----------------------------------------------------------

describe("debitGrams", () => {
  it("multiplica as gramas da linha pela quantidade do item", () => {
    // quantity=3 de propósito: com quantity=1 o teste passaria mesmo se
    // alguém esquecesse a multiplicação — e o modal prometeria 1/3 da baixa.
    const item = { quantity: 3, gcode_meta: {} };
    expect(debitGrams(item, { grams_unit: "12.5" }, 1.24)).toBe(37.5);
  });

  it("deriva do gcode quando a linha não tem gramas digitadas", () => {
    const item = { quantity: 2, gcode_meta: { filament_g: 20 } };
    expect(debitGrams(item, { grams_unit: null }, 1.24)).toBe(40);
  });

  it("deriva dos metros quando não há filament_g", () => {
    // Mesma conta do servidor (grams_for_item → effective_grams_per_unit),
    // sem refugo: área do 1,75 mm × densidade × metros.
    const item = { quantity: 1, gcode_meta: { filament_m: 10 } };
    const esperado = 10 * Math.PI * (1.75 / 2) ** 2 * 1.24;
    expect(debitGrams(item, { grams_unit: null }, 1.24)).toBeCloseTo(esperado, 2);
  });

  it("devolve null quando não há de onde derivar", () => {
    const item = { quantity: 2, gcode_meta: {} };
    expect(debitGrams(item, { grams_unit: null }, 1.24)).toBeNull();
  });
});
