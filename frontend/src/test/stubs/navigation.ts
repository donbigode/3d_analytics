/** Stub de $app/navigation para os testes unitários. Registra as chamadas
 *  para que os testes possam afirmar sobre redirecionamento sem um router. */
export const gotoCalls: string[] = [];
export function goto(url: string): Promise<void> {
  gotoCalls.push(url);
  return Promise.resolve();
}
