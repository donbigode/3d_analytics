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
  reset: () => void;
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

  /** Zera só o `error`. Não mexe em `loading`: assim como o `pending` de
   *  action() (ver o comentário lá), `loading` é um fato sobre o mundo — ou
   *  há um reload() de fato em voo, ou não há — e o chamador não tem
   *  autoridade para declarar isso falso. Não bota `seq++` de propósito: se
   *  houver mesmo um reload() em voo quando reset() é chamado e ele vier a
   *  falhar depois, é legítimo que o erro real dessa requisição real apareça
   *  — reset() descarta o que já teria sido exibido até agora, não cancela a
   *  requisição. Existe para o mesmo motivo do reset() de action(): páginas
   *  que combinam o erro de dois resource() independentes (ex.: DRE por
   *  período e DRE mensal) num único alerta, e cujo caminho de recarga de
   *  um precisa limpar o erro velho do outro — resource() não sabe fazer
   *  isso sozinho, nem deveria (os dois seguem independentes). */
  function reset(): void {
    update((s) => ({ ...s, error: "" }));
  }

  if (opts.auto !== false) void reload();

  return { subscribe, reload, set, reset };
}

export type ActionState = { pending: boolean; error: string };

export type Action<A extends unknown[], R> = Readable<ActionState> & {
  run: (...args: A) => Promise<R | undefined>;
  reset: () => void;
};

export function action<A extends unknown[], R>(
  fn: (...args: A) => Promise<R>,
  opts: { errorMessage?: string } = {},
): Action<A, R> {
  const { subscribe, set, update } = writable<ActionState>({ pending: false, error: "" });

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

  /** Zera só o `error`. Existe para páginas que combinam o erro de uma
   *  action() com o de um resource() irmão num único alerta (ex.:
   *  `$sales.error || $saveSale.error`): sem isso, um erro de mutação
   *  sobrevive indefinidamente na tela mesmo depois de um reload()
   *  bem-sucedido, porque resource() e action() são stores independentes — um
   *  não sabe zerar o erro do outro.
   *
   *  Não mexe em `pending`. `pending` é um fato sobre o mundo — existe ou não
   *  existe uma requisição em voo — e o chamador não tem autoridade para
   *  declarar isso falso. A primeira versão deste reset() zerava os dois
   *  juntos, e isso abriu uma janela real: reset() chamado enquanto um
   *  run() ainda está em voo (ex.: o usuário clica "Atualizar" antes do POST
   *  do formulário resolver) reabilitava um submit que existia justamente
   *  para impedir envio duplicado, com a requisição original ainda pendente.
   *  `error` é só uma mensagem exibida — o chamador pode legitimamente
   *  dispensá-la; `pending` não é dele para mentir. */
  function reset(): void {
    update((s) => ({ ...s, error: "" }));
  }

  return { subscribe, run, reset };
}
