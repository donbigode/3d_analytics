import { describe, it, expect } from "vitest";
import { quoteNumber } from "./quote-number";

describe("quoteNumber", () => {
  it("formata com quatro dígitos", () => {
    expect(quoteNumber(42)).toBe("#0042");
  });
  it("não trunca acima de 9999", () => {
    expect(quoteNumber(12345)).toBe("#12345");
  });
  it("formata o primeiro orçamento", () => {
    expect(quoteNumber(1)).toBe("#0001");
  });
  it("devolve travessão para ausente", () => {
    expect(quoteNumber(null)).toBe("—");
    expect(quoteNumber(undefined)).toBe("—");
  });
});
