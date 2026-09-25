import { describe, it, expect } from "vitest";
import { money, date, dateTime, num, dur, pct, DASH } from "./format";

describe("money", () => {
  it("formata em BRL pt-BR", () => {
    expect(money(1234.56)).toBe("R$ 1.234,56");
  });
  it("aceita string numérica vinda da API (Decimal serializado)", () => {
    expect(money("340.00")).toBe("R$ 340,00");
  });
  it("devolve travessão para nulo, indefinido, vazio e não-numérico", () => {
    expect(money(null)).toBe(DASH);
    expect(money(undefined)).toBe(DASH);
    expect(money("")).toBe(DASH);
    expect(money("abc")).toBe(DASH);
  });
  it("formata zero como valor, não como vazio", () => {
    expect(money(0)).toBe("R$ 0,00");
  });
});

describe("date", () => {
  it("formata ISO date como dd/mm/aaaa", () => {
    expect(date("2026-09-21")).toBe("21/09/2026");
  });
  it("aceita ISO datetime e ignora a hora", () => {
    expect(date("2026-09-21T14:30:00Z")).toBe("21/09/2026");
  });
  it("devolve travessão para nulo e vazio", () => {
    expect(date(null)).toBe(DASH);
    expect(date("")).toBe(DASH);
  });
});

describe("dateTime", () => {
  it("formata data curta com hora", () => {
    expect(dateTime("2026-09-21T14:30:00")).toBe("21/09/26 14:30");
  });
  it("devolve travessão para nulo", () => {
    expect(dateTime(null)).toBe(DASH);
  });
});

describe("num", () => {
  it("usa duas casas por padrão", () => {
    expect(num(1234.5)).toBe("1.234,50");
  });
  it("respeita o número de casas pedido", () => {
    expect(num(48.24, 1)).toBe("48,2");
  });
  it("devolve travessão para nulo e não-numérico", () => {
    expect(num(null)).toBe(DASH);
    expect(num("abc")).toBe(DASH);
  });
});

describe("dur", () => {
  it("formata horas e minutos", () => {
    expect(dur(8100)).toBe("2h 15min");
  });
  it("omite a hora quando menor que uma", () => {
    expect(dur(900)).toBe("15min");
  });
  it("devolve travessão para nulo", () => {
    expect(dur(null)).toBe(DASH);
  });
  it("devolve travessão para zero — nenhuma impressão leva 0 minutos, então time_s=0 é ausência de registro", () => {
    expect(dur(0)).toBe(DASH);
  });
});

describe("pct", () => {
  it("usa uma casa por padrão", () => {
    expect(pct(12.54)).toBe("12,5%");
  });
  it("devolve travessão para nulo", () => {
    expect(pct(null)).toBe(DASH);
  });
});
