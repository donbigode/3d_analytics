import { describe, it, expect, vi } from "vitest";
import { get } from "svelte/store";
import { resource, action } from "./resource";
import { ApiError } from "./api";
import { gotoCalls } from "../test/stubs/navigation";

const tick = () => new Promise((r) => setTimeout(r, 0));

describe("resource", () => {
  it("não carrega sozinho quando auto=false", async () => {
    const fetcher = vi.fn().mockResolvedValue([1, 2]);
    const r = resource(fetcher, { auto: false });
    await tick();
    expect(fetcher).not.toHaveBeenCalled();
    expect(get(r).data).toBeUndefined();
  });

  it("carrega no reload e expõe os dados", async () => {
    const r = resource(() => Promise.resolve([1, 2]), { auto: false });
    await r.reload();
    expect(get(r).data).toEqual([1, 2]);
    expect(get(r).loading).toBe(false);
    expect(get(r).error).toBe("");
  });

  it("marca loading durante a carga", async () => {
    let solta: (v: number[]) => void = () => {};
    const r = resource(() => new Promise<number[]>((res) => { solta = res; }), { auto: false });
    const p = r.reload();
    expect(get(r).loading).toBe(true);
    solta([9]);
    await p;
    expect(get(r).loading).toBe(false);
  });

  it("captura o erro e usa a mensagem configurada", async () => {
    const r = resource(
      () => Promise.reject(new ApiError(500, null)),
      { auto: false, errorMessage: "Falha ao carregar vendas." },
    );
    await r.reload();
    expect(get(r).error).toContain("Falha ao carregar vendas.");
    expect(get(r).loading).toBe(false);
  });

  it("limpa o erro de uma carga anterior ao recarregar com sucesso", async () => {
    let falhar = true;
    const r = resource(
      () => (falhar ? Promise.reject(new ApiError(500, null)) : Promise.resolve([1])),
      { auto: false },
    );
    await r.reload();
    expect(get(r).error).not.toBe("");
    falhar = false;
    await r.reload();
    expect(get(r).error).toBe("");
    expect(get(r).data).toEqual([1]);
  });

  it("redireciona para /login em 401", async () => {
    gotoCalls.length = 0;
    const r = resource(() => Promise.reject(new ApiError(401, null)), { auto: false });
    await r.reload();
    expect(gotoCalls).toContain("/login");
  });

  it("set troca os dados sem refazer a chamada (atualização otimista)", async () => {
    const fetcher = vi.fn().mockResolvedValue([1]);
    const r = resource(fetcher, { auto: false });
    await r.reload();
    r.set([1, 2, 3]);
    expect(get(r).data).toEqual([1, 2, 3]);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});

describe("action", () => {
  it("marca pending durante a execução e devolve o resultado", async () => {
    let solta: (v: string) => void = () => {};
    const a = action(() => new Promise<string>((res) => { solta = res; }));
    const p = a.run();
    expect(get(a).pending).toBe(true);
    solta("ok");
    expect(await p).toBe("ok");
    expect(get(a).pending).toBe(false);
  });

  it("captura o erro, devolve undefined e não propaga", async () => {
    const a = action(() => Promise.reject(new ApiError(409, null)), {
      errorMessage: "Falha ao salvar venda.",
    });
    const res = await a.run();
    expect(res).toBeUndefined();
    expect(get(a).error).not.toBe("");
    expect(get(a).pending).toBe(false);
  });

  it("limpa o erro anterior numa execução bem-sucedida", async () => {
    let falhar = true;
    const a = action(() => (falhar ? Promise.reject(new ApiError(409, null)) : Promise.resolve(1)));
    await a.run();
    expect(get(a).error).not.toBe("");
    falhar = false;
    await a.run();
    expect(get(a).error).toBe("");
  });

  it("repassa os argumentos para a função", async () => {
    const fn = vi.fn().mockResolvedValue(null);
    const a = action(fn as (id: string, body: object) => Promise<null>);
    await a.run("abc", { x: 1 });
    expect(fn).toHaveBeenCalledWith("abc", { x: 1 });
  });
});
