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

  async function reload(): Promise<void> {
    update((s) => ({ ...s, loading: true, error: "" }));
    try {
      const data = await fetcher();
      update((s) => ({ ...s, loading: false, error: "", data }));
    } catch (err) {
      handleApiError(err);
      update((s) => ({ ...s, loading: false, error: errorMessage(err, opts.errorMessage) }));
    }
  }

  function set(v: T): void {
    update((s) => ({ ...s, data: v }));
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
