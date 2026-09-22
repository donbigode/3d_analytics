# Spec 1 — Plataforma: número humano, busca/ordenação e responsivo

**Data:** 2026-09-21
**Status:** aprovado no brainstorming, aguardando revisão da spec
**Depende de:** Spec 0 (camada compartilhada)
**Habilita:** Specs 2 e 3

## 1. Contexto e objetivo

Três carências transversais, encontradas no review de UX, que as Specs 2 e 3
precisam resolvidas antes de existir:

1. **Identificador ilegível.** Todo lugar que mostra um orçamento mostra
   `uuid.slice(0, 8)` — Orçamentos, Contábil, PDF. Não existe número que duas
   pessoas consigam falar em voz alta ("olha o 124 aí").
2. **Nenhuma lista tem busca nem ordenação.** Nem Orçamentos, nem Contábil, nem
   Clientes, nem Estoque. O pedido de busca no Contábil (Spec 2) é o sintoma de
   uma lacuna que está em toda parte.
3. **Um único breakpoint no app inteiro** (`880px`, em `+layout.svelte:290`).
   Tabelas de 8 colunas viram scroll horizontal no celular — que é onde a
   conferência de bancada acontece.

Resolver os três aqui, uma vez, em vez de três vezes dentro das specs de feature.

## 2. Escopo

**Dentro:** coluna `quotes.seq` + sequence + backfill; exibição do número em todas
as superfícies; busca e ordenação em `Table.svelte`; componente `SearchBar`; modo
card responsivo; tokens de breakpoint.

**Fora:** busca server-side (ver 4.3); numeração de despesas, clientes ou spools;
redesenho visual.

## 3. Número humano — `#0042`

### 3.1 Modelo

Coluna `quotes.seq INTEGER NOT NULL UNIQUE`, alimentada por uma **sequence
Postgres** (`quote_seq`). Sequence, e não `MAX(seq)+1`, porque resolve inserção
concorrente sem lock explícito.

Numeração **global**, não por tipo. Um número só, sem a ambiguidade de "#12
comercial ou #12 pessoal?" — o tipo já aparece como tag ao lado.

### 3.2 Migração `0032_quote_seq`

Esta é a **única migração com backfill real** das quatro specs.

```sql
ALTER TABLE quotes ADD COLUMN seq INTEGER;

CREATE SEQUENCE quote_seq;

-- Backfill em ordem cronológica; id como desempate determinístico
-- para created_at com mesmo valor.
WITH ord AS (
  SELECT id, row_number() OVER (ORDER BY created_at, id) AS rn FROM quotes
)
UPDATE quotes q SET seq = ord.rn FROM ord WHERE q.id = ord.id;

SELECT setval('quote_seq', COALESCE((SELECT MAX(seq) FROM quotes), 0) + 1, false);

ALTER TABLE quotes ALTER COLUMN seq SET NOT NULL,
                   ALTER COLUMN seq SET DEFAULT nextval('quote_seq');

CREATE UNIQUE INDEX ix_quotes_seq ON quotes (seq);
```

`downgrade()`: `DROP INDEX`, `DROP COLUMN`, `DROP SEQUENCE`.

**Compatibilidade com código antigo:** a coluna tem default, então uma API da
versão anterior continua inserindo orçamentos sem erro. A migração pode subir
antes do deploy da API.

Precisão sobre indisponibilidade: o `migrations/env.py` envolve as migrações
numa transação única, e o Postgres segura o `ACCESS EXCLUSIVE` do `ADD COLUMN`
até o commit. Um INSERT vindo do processo antigo **não erra, mas fica
bloqueado** durante a transação inteira. Com o volume atual isso é
imperceptível; a distinção passa a importar se `quotes` crescer a ponto de o
`CREATE INDEX` não-concorrente demorar.

**Buracos na numeração:** orçamento deletado deixa lacuna. Aceito — a sequence
nunca reaproveita, e número que se repete seria pior que número que pula.

### 3.3 Exibição

Formato `#` + `padStart(4, "0")` → `#0042`. Acima de 9999 cresce naturalmente.

| Superfície | Hoje | Depois |
|---|---|---|
| Lista de Orçamentos, coluna `#` | `a3f9c1d2` | `#0042` |
| Detalhe do orçamento (título) | "Orçamento" | "Orçamento #0042" |
| Contábil, coluna "Orçamento" | `a3f9c1d2` | `#0042` |
| PDF (`quote.html`) | — | `#0042` no cabeçalho |
| Inbox / Capacidade | uuid curto | `#0042` |

O UUID sai da superfície visível e vira atributo `title=` onde ainda for útil
para suporte. Continua sendo a chave em toda URL e chamada de API — nada de
rotear por `seq`.

### 3.4 API

- `QuoteOut.seq: int` — novo campo.
- `SaleOut.quote_seq: int` — novo campo, preenchido por join em `_sale_out`.
  A tabela `sales` **não** ganha coluna; ela já tem `quote_id`.
- Nenhum endpoint novo e nenhuma mudança de ordenação na API. `GET /quotes`
  continua ordenando por `created_at desc` — que, por construção do backfill, é a
  mesma ordem de `seq desc`. Ordenar por número na tela é client-side (seção 4.2).

## 4. Busca e ordenação

### 4.1 `SearchBar.svelte`

```svelte
<SearchBar bind:value={q} total={rows.length} shown={filtered.length} />
```

Input com placeholder contextual, contador "23 de 180" e botão limpar. Debounce
de 150ms. Sem ícone de lupa desenhado à mão — segue a linguagem tipográfica do
app (mono, uppercase, letter-spacing).

### 4.2 `Table.svelte` — ordenação

Cada coluna ganha `sortable?: boolean`. Clique no cabeçalho cicla
**asc → desc → nenhum** (voltar à ordem natural da lista importa: em Orçamentos,
a ordem natural é cronológica).

Comparador: numérico quando o valor bruto é número ou string numérica; data
quando parseável como ISO; senão `localeCompare(pt-BR, { numeric: true })`.
Ordena sobre o **valor bruto**, não o formatado — senão `R$ 1.234,56` ordena como
texto e quebra.

Indicador de direção no `th`, em mono, no estilo já usado nos cabeçalhos.

### 4.3 `Table.svelte` — filtro por texto

```ts
export let searchText = "";
export let searchExtra: ((row: Row) => string) | undefined = undefined;
```

Filtra sobre os valores **já formatados** de todas as colunas (para que buscar
"1.234" encontre `R$ 1.234,56`, e "21/09" encontre a data como o usuário a vê),
concatenados com o retorno de `searchExtra` — que cobre campos que não são
coluna, como notas. Casamento por substring, sem acento e sem caixa
(`normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase()`).

**Client-side, por decisão.** É uma operação de duas pessoas; a ordem de grandeza
é de centenas a poucos milhares de linhas, e filtrar em memória é instantâneo e
não cria endpoint. A assinatura permite trocar para server-side depois sem mudar
nenhuma chamada: bastaria a página passar `searchText` adiante para a API em vez
de para a `Table`.

### 4.4 Onde aplicar

Orçamentos, Contábil (as três listas — ver Spec 2), Clientes, Estoque, Materiais,
Biblioteca. Campos buscáveis por tela ficam definidos na spec de cada uma; aqui
fica o mecanismo.

## 5. Responsivo

### 5.1 Tokens de breakpoint

```css
--bp-sm: 560px;   /* telefone em pé   */
--bp-md: 880px;   /* já em uso hoje   */
--bp-lg: 1180px;  /* largura de main  */
```

Media queries não aceitam `var()`. Os tokens documentam a escala; as queries usam
os literais, e a escala fica num comentário único no topo do `app.css`, para não
haver um quarto breakpoint inventado numa página qualquer.

### 5.2 Modo card na `Table`

Abaixo de 700px, cada linha vira um bloco empilhado `rótulo: valor`, gerado dos
mesmos `columns` — sem markup duplicado:

```
┌─────────────────────────────┐
│ #0042            comercial  │   ← primeira coluna + tag em destaque
│ Cliente      Maria Silva    │
│ Total          R$ 340,00    │
│ Vendido em     21/09/2026   │
│ [ações]                     │
└─────────────────────────────┘
```

Controlado por `stackOnMobile` (default `true`). Tabelas genuinamente numéricas,
onde comparar coluna importa mais que ler linha, passam `false` e mantêm o
scroll horizontal dentro do `.table-wrap`.

### 5.3 Alvos de toque

Mínimo de 44×44px nos controles hoje pequenos demais: `.chip` de pessoas
(`0.05rem 0.45rem` de padding), checkbox de "Vendido", botões `.tiny`. Aumentar a
área clicável sem inflar o desenho — padding e `min-height` no elemento, não
fonte maior.

### 5.4 Gutters

Garantir 16px de respiro lateral em qualquer largura. `main` hoje usa
`padding: 2rem 1.5rem 5rem` — checar as páginas que reabrem `padding` e zeram os
lados.

## 6. Testes

**Backend**
- Migração: teste que cria N orçamentos, roda `upgrade`, verifica que os `seq`
  são `1..N` na ordem de `created_at`, sem buracos nem repetição.
- Inserção pós-migração recebe `seq` seguinte, sem passar o campo.
- `QuoteOut.seq` e `SaleOut.quote_seq` presentes e corretos.
- Unicidade: tentativa de inserir `seq` duplicado falha.

**Frontend**
- `Table`: ordenação por coluna numérica, de texto e de data; ciclo
  asc→desc→nenhum; filtro casando sobre valor formatado; filtro sem acento;
  `searchExtra` incluído na busca.
- `SearchBar`: contador, limpar, debounce.

**E2E (Playwright, viewport 390px)**
- `/quotes` e `/accounting` não produzem scroll horizontal no `body`.
- Modo card renderiza rótulo e valor de cada coluna.

## 7. Riscos

| Risco | Mitigação |
|---|---|
| Backfill em produção com volume grande trava a tabela | Volume atual é pequeno (operação de duas pessoas); o `UPDATE` é único e rápido. Conferir `count(*)` antes de rodar |
| `setval` errado gera colisão no primeiro insert novo | `COALESCE(MAX(seq), 0) + 1` com `is_called = false`; teste cobre o primeiro insert pós-migração |
| Ordenação sobre valor formatado quebraria números e datas | Ordenar sobre o valor bruto é regra explícita; testes cobrem os três tipos |
| Modo card esconde informação em vez de reorganizar | Todas as colunas aparecem no card; nada é omitido por largura |

## 8. Critério de pronto

- `make test`, `make lint` e `make e2e` verdes.
- `alembic upgrade head` e `alembic downgrade -1` rodam limpos num banco com dados.
- Nenhuma tela do app exibe UUID cru para o usuário.
- Orçamentos, Contábil, Clientes, Estoque, Materiais e Biblioteca têm busca e
  ordenação funcionando.
- Em 390px, nenhuma página produz scroll horizontal.
