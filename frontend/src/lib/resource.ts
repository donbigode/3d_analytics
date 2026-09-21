import { writable, type Readable } from "svelte/store";
import { errorMessage } from "$lib/api";
import { handleApiError } from "$lib/guard";

/** Helpers de carga e mutação.
 *
 *  Antes disto, cada função de cada página repetia o mesmo bloco
 *  loading/try/catch/handleApiError/errorMessage/finally — 98 vezes em
 *  16 páginas. Aqui o tratamento vive num lugar só, e o `pending` do
 *  action() dá o estado "salvando" de graça para qualquer tela. */

export type ResourceState<T> = { loading: boolean; error: string; data: T | undefined };

export type Resource<T> = Readable<ResourceState<T>> & {
  reload: () => Promise<void>;
  set: (v: T) => void;
};

export function resource<T>(
  fetcher: () => Promise<T>,
  opts: { initial?: T; errorMessage?: string; auto?: boolean } = {},
): Resource<T> {
  const { subscribe, update } = writable<ResourceState<T>>({
    loading: false,
    error: "",
    data: opts.initial,
  });

  // Token de sequência: cada reload() em curso só pode escrever no store se
  // ainda for o mais recente quando terminar. Sem isso, dois reload()
  // concorrentes (ex.: auto-load seguido de um reload() manual) resolvem
  // fora de ordem e o que responder por último — não o mais recente — vence.
  // set() também invalida o que estiver em voo, para que uma atualização
  // otimista nunca seja sobrescrita por um fetch antigo ainda pendente.
  let seq = 0;

  async function reload(): Promise<void> {
    const mySeq = ++seq;
    update((s) => ({ ...s, loading: true, error: "" }));
    try {
      const data = await fetcher();
      if (mySeq !== seq) return; // superado por um reload()/set() mais novo — não escreve nada
      update((s) => ({ ...s, loading: false, error: "", data }));
    } catch (err) {
      handleApiError(err);
      if (mySeq !== seq) return;
      update((s) => ({ ...s, loading: false, error: errorMessage(err, opts.errorMessage) }));
    }
  }

  function set(v: T): void {
    seq++; // invalida qualquer reload() em voo, para ele não sobrescrever este valor ao terminar
    update((s) => ({ ...s, data: v, loading: false }));
  }

  if (opts.auto !== false) void reload();

  return { subscribe, reload, set };
}

export type ActionState = { pending: boolean; error: string };

export type Action<A extends unknown[], R> = Readable<ActionState> & {
  run: (...args: A) => Promise<R | undefined>;
};

export function action<A extends unknown[], R>(
  fn: (...args: A) => Promise<R>,
  opts: { errorMessage?: string } = {},
): Action<A, R> {
  const { subscribe, set } = writable<ActionState>({ pending: false, error: "" });

  /** `undefined` de volta significa "não teve sucesso" OU "teve sucesso e o
   *  retorno em si é `undefined`" — os dois casos são indistinguíveis pelo
   *  valor de retorno. Confira `.error` (via `get(action)` ou `$action`) para
   *  diferenciar: erro não-vazio é falha; erro vazio é sucesso sem retorno. */
  async function run(...args: A): Promise<R | undefined> {
    set({ pending: true, error: "" });
    try {
      const res = await fn(...args);
      set({ pending: false, error: "" });
      return res;
    } catch (err) {
      handleApiError(err);
      set({ pending: false, error: errorMessage(err, opts.errorMessage) });
      return undefined;
    }
  }

  return { subscribe, run };
}
