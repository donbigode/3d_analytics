# Achados pendentes do review de UX — o que ficou para decidir

**Data:** 2026-09-25
**Origem:** execução das quatro specs de 2026-09-21 (camada compartilhada, plataforma, contábil, orçamentos)
**Status:** nada aqui bloqueia o merge. É a lista de decisões do Otavio.

Este documento existe porque relatórios de tarefa e ledgers de execução são
descartáveis; o repositório não. Cada item abaixo foi encontrado por uma
revisão, julgado, e deliberadamente não consertado — com a razão registrada.

## Consertar antes do próximo fechamento de mês

**1. O `make e2e` está vermelho desde junho — duas causas empilhadas.**
`tests/e2e/happy_path.spec.ts` sobe um gcode de PLA cujo material nunca
auto-resolve, e tenta finalizar com peça pendente. A guarda que bloqueia isso
veio do commit `9635161` (2026-06-07, "pending-material workflow"), anterior a
todo este trabalho — confirmado por `git merge-base --is-ancestor`. O teste
nunca foi atualizado. Consequência: o único teste que cobria o fluxo central
(orçamento → finalizar → PDF) não roda há três meses.
Segunda causa, independente: rodar o Playwright exige `NODE_PATH` apontando
para `frontend/node_modules`, porque o `playwright.config.ts` fica na raiz.
É a origem do `node_modules` que aparece solto na raiz. Os specs novos
(`mobile`, `venda-retroativa`, `clone-e-filamento`) rodam com:
`cd frontend && NODE_PATH="$PWD/node_modules" npx playwright test ../tests/e2e/<f> --config=../playwright.config.ts`

**2. Nenhuma tela foi vista rodando por um humano.**
Os ambientes dos agentes quase nunca tiveram navegador. A verificação foi de
tipo, build, teste unitário e e2e. Precisa de olho seu, com atenção especial a:
`/capacity`, `/insights` e `/quotes/:id` — as três onde a consolidação de CSS
foi feita por dedução, sem browser disponível; e ao fluxo manual completo
rascunho → gcode → material → finalizar → aprovar → produzir → concluir → PDF.

## Consertar em breve

**3. A lista de orçamentos não tem modo card no celular.**
`quotes/+page.svelte` agora usa o componente `Table`, então herdou o modo card
— mas as tabelas de `spools` e `materials` seguem com status em texto simples,
sem as tags coloridas. É a principal lista do app no telefone.

**4. Teste estrutural das migrações.**
Percorrer `alembic.script.ScriptDirectory` afirmando head única e
`down_revision` correto. Pega quebra de cadeia sem executar SQL. A cadeia foi
verificada à mão neste trabalho (28 revisões, head única `0033`), não por teste.

**5. `copy_gcode` sem guarda contra caminho absoluto ou `..`.**
`backend/infra/storage/gcodes.py`. Inalcançável hoje — o `save_gcode` só grava
basename —, mas vira defeito se a coluna passar a receber entrada menos
controlada. Uma linha.

**6. O log de foto pulada não diz de qual orçamento.**
`backend/infra/storage/quote_photos.py` avisa qual `storage_path` foi pulado e
por quê, mas correlacionar com o clone exige cruzamento.

**7. A dica de busca vazia considera o chip de status, não o período.**
`accounting/+page.svelte`. Uma venda escondida pelo intervalo de datas mostra
"ver em todos", mas clicar só reseta o chip e a linha continua oculta pela data.

**8. Botão "Atualizar" das despesas sem `disabled` durante a carga.**
Pré-existente, não introduzido aqui.

**9. Os e2e semeiam no banco de dev e não limpam.**
Sufixos únicos por execução evitam colisão hoje, mas é convenção entre dois
arquivos, não garantia, e as linhas se acumulam. Depende também de o Playwright
rodar sem paralelismo (`fullyParallel: false`).

**9b. O e2e da venda retroativa falha ~1 em 4 execuções.**
`tests/e2e/venda-retroativa.spec.ts`, na asserção de delta do DRE. Isolado com
`git stash`: falha igual com ou sem os consertos desta fase, logo é
pré-existente. A causa é a corrida que o próprio comentário do teste documenta
— o DRE exibe `data` antigo durante um fetch em voo. O conserto de período
(`invalidate()`) resolveu o caminho de troca de datas, não este. Enquanto isso
não for resolvido, o teste treina quem o roda a ignorar falha vermelha, que é
pior que não ter teste.

**9c. `clone-e-filamento.spec.ts:5` fixa `http://localhost:8000`.**
Dormente porque o valor está certo hoje. Mesmo defeito que o
`venda-retroativa.spec.ts` tinha com a porta 8001 — aquele foi corrigido para
derivar do `baseURL`; este não.

**9d. `quotes/+page.svelte:117` tem dependência reativa não rastreada.**
`viewRows` chama `clientName()`, que fecha sobre `$clients.data` sem citá-lo no
bloco `$:`. Mesma classe dos dois bugs corrigidos no contábil (chips de status
e total de perda operacional), impacto menor porque clientes e orçamentos
costumam carregar juntos. Pré-existente.

## Decisões de produto, não defeitos

**10. Não existe indicador de "dado desatualizado" em lugar nenhum.**
O `resource()` preserva os dados quando um reload falha — o que é correto —,
mas a tela não diz que o que você está olhando pode estar velho. O caso mais
agudo (o DRE exibindo números antigos durante recarga) foi consertado; o padrão
geral continua. Aparece em toda página, não só no contábil.

**11. Não há infraestrutura de teste de componente.**
O Vitest roda em `environment: "node"`, sem jsdom. Lógica pura é testável (64
testes); nada dentro de um `.svelte` é. Adicionar jsdom + testing-library é
trabalho que não estava em nenhuma spec.

**12. `Table.svelte` monta o slot de ações duas vezes por linha** — uma na
tabela, outra no card —, com CSS escondendo uma. Componentes com estado local
no slot (como o editor de venda) existem em duplicata; cruzar 700px no meio de
uma edição troca pela cópia com os valores anteriores. Baixo dano hoje.

**13. `spool_label` ainda colide** para duas bobinas de mesmo tipo, fabricante
e cor compradas na mesma loja no mesmo mês.

## Fechados durante o trabalho, registrados por serem contra-intuitivos

- `dur(0)` mostra travessão, não "0min": impressão 3D não leva zero minutos,
  logo zero significa "não registrado". Vale só para duração — `money(0)`
  continua sendo `R$ 0,00`.
- `filterRows` mantém visível a linha cujo formatador lança, com aviso no
  console: sumir da busca é lido como "o registro não existe", e some em
  silêncio; aparecer indevidamente é ruído visível e investigável.
- `custo_total` chega sem arredondar de propósito, para o total do painel bater
  com a regra soma-depois-arredonda do contábil.
- `loss_on` é obrigatório no schema: se a invariante quebrar, falha alto em vez
  de subcontar a perda operacional em silêncio.
