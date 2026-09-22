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

  it("descarta o resultado de um reload() superado por outro mais recente, mesmo resolvendo fora de ordem", async () => {
    let soltaA: (v: number[]) => void = () => {};
    let soltaB: (v: number[]) => void = () => {};
    let chamadas = 0;
    const fetcher = vi.fn(
      () =>
        new Promise<number[]>((res) => {
          chamadas++;
          if (chamadas === 1) soltaA = res;
          else soltaB = res;
        }),
    );
    // auto=true (padrão): dispara a chamada #1 (A) já na construção.
    const r = resource(fetcher);
    // chamada #2 (B), disparada logo em seguida — é a mais recente das duas.
    const p2 = r.reload();

    // resolve fora de ordem: a mais recente (B) responde primeiro.
    soltaB([2]);
    await p2;
    expect(get(r).data).toEqual([2]);
    expect(get(r).loading).toBe(false);

    // A (mais antiga) responde depois — sua chegada tardia não pode
    // sobrescrever o valor de B, que é a chamada mais recente.
    soltaA([1]);
    await tick();
    expect(get(r).data).toEqual([2]);
    expect(get(r).loading).toBe(false);
  });

  it("set() durante um reload() pendente sobrevive à resolução tardia do fetch antigo", async () => {
    let solta: (v: number[]) => void = () => {};
    const r = resource(() => new Promise<number[]>((res) => { solta = res; }), { auto: false });
    const p = r.reload();
    expect(get(r).loading).toBe(true);

    r.set([9, 9]);
    expect(get(r).data).toEqual([9, 9]);
    expect(get(r).loading).toBe(false);

    // o fetch invalidado por set() ainda resolve, mas não pode sobrescrever
    // a atualização otimista nem deixar loading preso em true.
    solta([1, 2]);
    await p;
    expect(get(r).data).toEqual([9, 9]);
    expect(get(r).loading).toBe(false);
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

  it("undefined de run() é ambíguo por si só — .error diferencia sucesso sem retorno de falha", async () => {
    const semRetorno = action(() => Promise.resolve(undefined));
    const resOk = await semRetorno.run();
    expect(resOk).toBeUndefined();
    expect(get(semRetorno).error).toBe("");

    const falha = action(() => Promise.reject(new ApiError(500, null)));
    const resFalha = await falha.run();
    expect(resFalha).toBeUndefined();
    expect(get(falha).error).not.toBe("");
  });

  it("reset() limpa o erro de uma execução que falhou", async () => {
    const a = action(() => Promise.reject(new ApiError(500, null)), {
      errorMessage: "Falha ao salvar venda.",
    });
    await a.run();
    expect(get(a).error).not.toBe("");

    a.reset();
    expect(get(a).error).toBe("");
    expect(get(a).pending).toBe(false);
  });
});
