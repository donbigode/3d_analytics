# Spec — Multicor: mais de um filamento por item

**Data:** 2026-09-26
**Status:** aprovado no brainstorming, aguardando revisão da spec
**Atende ao pedido:** "quando multicor, adicionar mais uma linha na quote de
filamento atrelado ao mesmo item produzido, mas que divida o max do tempo de
produção e qtd de itens"
**Depende de:** PR #32 (energia e depreciação escalam com a quantidade no CPV) —
sem ele a fórmula da seção 5 herda um erro de 35%
**Afeta outro repositório:** `3d_analytics_medallion` (seção 7). O
`3d_analytics_listener` **não** é afetado — não referencia nenhuma das tabelas
envolvidas.

## 1. Contexto

Um item de orçamento tem **um** material: `quote_items.material_version_id`,
FK nullable. Impressão em duas ou mais cores não tem como ser representada.

O que existe hoje e não resolve: `quote_items.is_multi_color`, um booleano que
apenas troca `single_color_waste_pct` por `multi_color_waste_pct` no cálculo de
refugo. Ou seja, multicor hoje é modelado como *"o mesmo material, com mais
purga"* — o que serve para inflar o custo, não para saber que cores entraram.

O lado da **produção real já suporta** multicor: `material_consumptions` é 1:N
por `quote_item_id`, e `ProduceRequest.consumption` é uma lista, não um dicionário
por item. A lacuna está inteira no lado do **orçamento**.

## 2. Escopo

**Dentro:** tabela `quote_item_filaments`;
`material_consumptions.quote_item_filament_id`; fórmula de custo com N
filamentos e tempo único; ajustes em `apply_production`;
`spools.material_version_id`; contrato de API das linhas; tela do item; PDF;
duas migrações com backfill.

**Fora:** extrair as gramas por cor do gcode (decidido: a digitação é manual —
ver 3.2); alterar a regra de DRE; mudar o medallion (fica no repositório dele,
seção 7); numeração ou identificação de bobina por cor.

## 3. Decisões tomadas no brainstorming

Registradas porque cada uma foi uma escolha entre alternativas defensáveis, e
sem a razão a próxima pessoa reabre a discussão.

### 3.1 Abordagem C — a tabela nova é a verdade, a coluna antiga vira derivada

Três formas foram consideradas:

| | o que faz | por que não |
|---|---|---|
| **A** | tabela nova só para multicor; item de uma cor tem zero linhas | `material_version_id` passaria a significar "o único material" **ou** "o principal" conforme a contagem de linhas. Ambiguidade é a classe de bug do PR #32 — dois lugares discordando sobre o mesmo dado |
| **B** | tabela nova é a única verdade, `material_version_id` sai | exige que os cinco pontos do medallion mudem **no mesmo deploy** que o app. Deploy coordenado entre dois repositórios é onde deploys quebram |
| **C** ⭐ | tabela nova é autoritativa; `material_version_id` continua existindo, redefinido como "a linha de `position=1`" | escolhida |

C é expand/contract: expande agora, contrai quando o outro lado estiver pronto.
O medallion continua funcionando **sem nenhuma mudança** — fica *incompleto*
para itens multicor, não *quebrado*.

O preço honesto de C: a coluna derivada precisa ser mantida em sincronia, e
"derivado" só vale se estiver escrito e testado. Sem isso, em seis meses alguém
volta a tratá-la como autoritativa.

### 3.2 As gramas por cor são digitadas, não extraídas do gcode

O gcode dá o total (tempo + filamento agregado); a divisão por cor é digitada na
tela. Slicers com AMS/MMU emitem uso por filamento no cabeçalho, mas não é o
caso aqui — e o parser não ganha trabalho nenhum nesta spec.

### 3.3 O número digitado é valor final — purga inclusa

`multi_color_waste_pct` **não** é aplicado sobre uma linha com `grams_unit`
preenchido.

Razão: é exatamente o comportamento que `filament_g` já tem
(`quote_service.py:17` — *"Se `filament_g` está preenchido e > 0, é o valor final
(sem refugo)"*), e o material da wipe tower sai dos próprios filamentos, então
"o que saiu da bobina" já contém a purga.

Consequência a registrar: `multi_color_waste_pct` (default 20%) deixa de atuar
em qualquer linha com gramas digitadas. Ele continua governando as linhas de
`grams_unit NULL`, que é o caso de todo item pré-existente depois da migração —
ver a tabela de refugo na seção 4. Não é removido nesta spec.

### 3.4 `grams_unit` é nullable, e é isso que torna o backfill seguro

`NULL` significa *"derive do `gcode_meta` como hoje"*.

A alternativa era o backfill gravar as gramas calculadas de cada item existente.
Rejeitada: congelar um valor derivado muda o comportamento silenciosamente — um
ajuste futuro de densidade do material deixaria de reprecificar o histórico, que
hoje reprecifica. Com `NULL`, a migração 0034 é **puramente estrutural** e o
custo de todo orçamento histórico continua bit-a-bit idêntico.

### 3.5 A soma das linhas não precisa fechar com o gcode

A tela mostra o total das linhas ao lado do total do gcode, com o delta visível,
e **não bloqueia**. O número do slicer é estimativa; o digitado é medição. Travar
o salvamento numa divergência obrigaria a mentir num dos dois campos.

## 4. Modelo

```sql
CREATE TABLE quote_item_filaments (
  id                  uuid PRIMARY KEY,
  quote_item_id       uuid NOT NULL REFERENCES quote_items(id) ON DELETE CASCADE,
  material_version_id uuid NOT NULL REFERENCES material_versions(id),
  grams_unit          numeric(10,2),          -- por PEÇA, valor final; NULL = deriva do gcode_meta
  position            int  NOT NULL,          -- 1..N, ordem de exibição
  UNIQUE (quote_item_id, position)
);
CREATE INDEX ix_quote_item_filaments_item ON quote_item_filaments (quote_item_id);
```

`grams_unit` é **por peça**, não por linha-total. Mesma convenção do resto do
sistema (`effective_grams_per_unit`, e a spec 2026-06-17 declarando `filament_m`
como "por peça"), e é o que mantém a multiplicação por `quantity` num só lugar.

**Invariantes** (a serem testadas, não apenas escritas). Nenhuma é imposta pelo
esquema — todas vivem no app, e é por isso que cada uma tem teste na seção 10:

1. Todo `quote_item` **com material resolvido** tem pelo menos uma linha. Item
   com `material_version_id IS NULL` — adicionado sem material — fica sem linha
   até resolver, que é o que `_assert_materials_resolved` já exige antes de
   produzir.
2. `quote_items.material_version_id` == o material da linha de `position = 1`.
   Derivada, mantida em **um único ponto** do app.
3. Item com mais de uma linha: **toda** linha tem `grams_unit` preenchido. Não se
   deriva do `gcode_meta` o que é ambíguo entre N cores.
4. `position` é contígua a partir de 1. Remover a linha do meio renumera.

**Qual refugo se aplica** — regra única, sem exceção:

| linha | refugo |
|---|---|
| `grams_unit` preenchido | **nenhum**. O valor é final (3.3) |
| `grams_unit NULL` | o de hoje: `multi_color_waste_pct` se `is_multi_color`, senão `single_color_waste_pct` |

A segunda linha da tabela **não** é uma concessão a código legado: é o que garante
que o custo de todo orçamento histórico fica idêntico após a migração 0034 (3.4).
Trocar o refugo de um item antigo marcado `is_multi_color` para o de cor única o
reprecificaria — exatamente o que o teste de custo antes/depois da seção 10
existe para impedir.

Ou seja: `is_multi_color` continua governando o refugo das linhas `NULL`, e não é
substituído por "tem mais de uma linha". Os dois conceitos coexistem porque
respondem a perguntas diferentes — o booleano diz *"esta impressão troca de
cor?"*, a contagem de linhas diz *"quais filamentos, e quanto de cada"*.

### 4.1 Migração `0034_quote_item_filaments`

Cria a tabela e faz o backfill estrutural:

```sql
INSERT INTO quote_item_filaments (id, quote_item_id, material_version_id, grams_unit, position)
SELECT gen_random_uuid(), qi.id, qi.material_version_id, NULL, 1
  FROM quote_items qi
 WHERE qi.material_version_id IS NOT NULL;
```

Itens com `material_version_id IS NULL` (adicionados sem material resolvido)
ficam **sem linha** — a invariante 1 passa a valer a partir da resolução do
material, que é o que `_assert_materials_resolved` já exige antes de produzir.
Registrar isso explicitamente para que a invariante não seja lida como violada.

`downgrade()`: `DROP TABLE`. Não há perda — no momento do downgrade a única
informação em `quote_item_filaments` que não está em `quote_items` são as linhas
multicor, e um downgrade é justamente a decisão de abandoná-las.

**Passo obrigatório antes de rodar em produção.** Contar os itens que ficarão sem
linha, para não descobrir depois:

```sql
SELECT count(*) FROM quote_items WHERE material_version_id IS NULL;
```

E conferir a cobertura depois:

```sql
SELECT count(*) FROM quote_items qi
  LEFT JOIN quote_item_filaments f ON f.quote_item_id = qi.id
 WHERE f.id IS NULL AND qi.material_version_id IS NOT NULL;   -- deve ser 0
```

### 4.2 Migração `0035_spools_material_version`

`material_versions` é uma tabela **SCD2** — `effective_from`, `effective_to`,
`is_current`, com várias linhas por linha de produto
`(material_type, manufacturer, color)`. Isso decide a regra de casamento: a
versão certa para vincular uma bobina agora é a **corrente**.

```sql
ALTER TABLE spools ADD COLUMN material_version_id uuid REFERENCES material_versions(id);

WITH candidato AS (
  SELECT material_type, manufacturer, color, min(id) AS id, count(*) AS n
    FROM material_versions
   WHERE is_current
   GROUP BY material_type, manufacturer, color
)
UPDATE spools s SET material_version_id = c.id
  FROM candidato c
 WHERE c.n = 1
   AND c.material_type = s.material_type
   AND c.color        IS NOT DISTINCT FROM s.color
   AND c.manufacturer IS NOT DISTINCT FROM s.manufacturer
   AND s.material_version_id IS NULL;
```

Nullable de propósito: bobina cadastrada antes do material, ou com cor escrita
diferente, não casa — e inventar um vínculo errado é pior que deixar `NULL`.

O `c.n = 1` cobre o caso patológico de duas versões marcadas `is_current` para o
mesmo trio, que não deveria existir mas não é impedido pelo esquema. Nesse caso
fica `NULL`, e o `min(id)` nunca é usado — está no `SELECT` só porque o
agrupamento exige uma agregação.

**O vínculo é de identidade, não de preço.** O custo de uma bobina já vem do seu
próprio `purchased_price / initial_grams`; `material_version_id` responde apenas
"que produto é esta bobina". Ninguém deve passar a derivar custo de bobina por
`price_per_kg_ref` da versão vinculada — seria trocar o preço realmente pago por
um preço de referência.

`downgrade()`: `DROP COLUMN`. Idempotente: rodar de novo não muda nada.

**Passo obrigatório antes de produção**, pelo mesmo motivo do 0033 — o banco de
dev tem poucas bobinas e não prova nada:

```sql
-- quantas bobinas existem, e quantas vão casar
SELECT count(*) AS total,
       count(*) FILTER (WHERE material_version_id IS NOT NULL) AS casadas
  FROM spools;
```

Guardar o "antes", rodar, comparar. Uma taxa de casamento baixa não é falha da
migração — é sinal de que os cadastros divergem, e isso é informação útil.

### 4.3 `material_consumptions.quote_item_filament_id`

Coluna nova, nullable, FK para `quote_item_filaments(id)`. Entra na migração
`0034`, sem backfill: linhas históricas ficam `NULL`.

Por que é necessária. `QuoteItemOut.consumptions` (PR #29, "ver o filamento
exato usado") já se documenta como podendo ter mais de uma linha — *"quando houve
reimpressão (falha + nova tentativa consome duas vezes)"*. Multicor cria uma
**segunda** razão para várias linhas, e sem este vínculo nada distingue "duas
cores" de "duas tentativas". A feature que o Otavio pediu em setembro ficaria
ambígua exatamente no caso que esta spec introduz.

Não dá para inferir pelo `spool_id`: duas cores podem sair de bobinas do mesmo
produto, e uma reimpressão sai da mesma bobina. Nem por `consumed_at`: agrupar
por proximidade de horário é heurística, e heurística em cima de dinheiro vira
bug silencioso.

`NULL` continua significando "consumo de antes desta spec", e a tela o mostra
como hoje.

## 5. Custo

```
filamento    = Σ linhas:  gramas_da_linha × quantity × preço(material_da_linha)/1000
energia      = energy_cost(time_s, ...) × quantity           ← UMA vez por item
depreciação  = depreciation_cost(time_s, ...) × quantity     ← UMA vez por item

onde gramas_da_linha = linha.grams_unit                          se preenchido
                     | effective_grams_per_unit(gcode_meta, …)   se NULL (uma linha só)
```

**A armadilha central desta spec**, e a razão de ela estar escrita em três
lugares: gramas **somam** por linha de cor; tempo **não**. O `time_s` do gcode
descreve a impressão da peça inteira, com todas as suas cores — somá-lo por
linha multiplicaria energia e depreciação pelo número de cores.

É o que o pedido original chama de "dividir o max do tempo de produção e qtd de
itens": as linhas compartilham um tempo e uma quantidade.

Os dois motores de custo — `pricing/quote.py` (o que o cliente paga) e
`accounting/cost.py` (o CPV do DRE) — precisam da mesma mudança e continuam
tendo que concordar. O teste `test_cpv_concorda_com_o_pricing_no_mesmo_item`
(PR #32) já existe para isso e passa a cobrir também o caso multicor.

O preço por linha vem de `material_versions.price_per_kg_ref` **da linha**, não
do item: duas cores podem ter preços diferentes, e é justamente isso que torna a
separação útil.

## 6. Produção

`ProduceRequest.consumption` já é `list[ConsumptionAssignment]` — **sem mudança
de contrato**. `ConsumptionAssignment` ganha um campo:

```python
quote_item_filament_id: str | None = None
```

Três correções em `apply_production` (`backend/api/routes/quotes/transitions.py`):

1. **Densidade vem da linha, não do item.** Hoje a linha 282 faz
   `mv = await session.get(MaterialVersion, it.material_version_id)`. Com
   multicor, cada assignment usa o material da **sua** linha.

2. **O fallback não pode calcular o item inteiro por linha.** Hoje a linha 292
   chama `grams_for_item(it.gcode_meta, ..., it.quantity)`, que devolve as gramas
   do item completo. Três assignments sem `grams` explícito debitariam **3× o
   item**. Regra nova: item com mais de uma linha exige
   `quote_item_filament_id` em cada assignment, e as gramas saem da linha —
   nunca de `grams_for_item`. Assignment sem linha identificada num item
   multicor retorna **409** com mensagem explícita.

3. **Aviso de material divergente.** Se a bobina tem `material_version_id`
   (migração 0035) e ele difere do material da linha, avisar. **Não bloquear**:
   o backfill deixa `NULL` em parte das bobinas, e bloquear por um dado
   incompleto impediria produzir.

`_assert_materials_resolved` passa a exigir que todo item tenha ao menos uma
linha com material, em vez de olhar `material_version_id`.

## 7. O outro repositório — `3d_analytics_medallion`

Não muda nada **agora**. Muda quando o Otavio quiser, sem deploy coordenado.

O problema que multicor cria lá está declarado na docstring do próprio mart
(`src/analytics_medallion/gold/consumo.py`):

> *"The export has no spool → material_version link, so usage is attributed to
> the material through the consumed item (material_consumptions → quote_item →
> material_version_id → material)"*

Com um item bicolor, as duas bobinas consumidas têm o mesmo `quote_item_id` —
então as gramas das duas viram **o mesmo material**. Um preto+vermelho reporta
tudo como preto, e a reconciliação de estoque descasa, porque o saldo é agrupado
pela cor da *bobina* e o uso pela cor do *item*.

Isso já está tecnicamente errado hoje (consumo já é 1:N); multicor transforma
latente em real.

| onde | o que fazer |
|---|---|
| `src/analytics_medallion/bronze.py` | ingerir `quote_item_filaments` |
| `gold/consumo.py` (2 joins, linhas ~22 e ~55) | atribuir por `spool.material_version_id`, não por `quote_item.material_version_id` — conserta o caso multicor **e** o erro latente |
| `gold/itens.py`, `gold/performance.py`, `gold/dre.py`, `notebooks/32_gold_projeto_tipo.py` | seguem válidos lendo a cor principal. Revisar só se a granularidade por cor for desejada nesses marts |

O `3d_analytics_listener` não referencia `quote_items`, `material_versions` nem
`material_consumptions` — verificado por busca. Nada a fazer lá.

## 8. Tela

No item do orçamento, onde hoje há um seletor de material:

```
Filamentos
  1  [PLA Preto        ▾]  [ 12,34 ] g/peça        [×]
  2  [PLA Vermelho     ▾]  [  5,67 ] g/peça        [×]
  3  [PETG Branco      ▾]  [  0,89 ] g/peça        [×]
     + cor
     ─────────────────────────────────────────────
     soma  18,90 g/peça   ·   gcode  18,90 g   (delta 0,00)
```

- Item de uma cor com `grams_unit` `NULL`: a coluna de gramas mostra o valor
  derivado do gcode, em cinza, editável — digitar preenche `grams_unit`.
- Remover a última linha não é permitido (invariante 1).
- Remover a linha de `position=1` renumera e atualiza
  `quote_items.material_version_id`.
- O delta é informativo; nunca impede salvar (3.5).

Na tela de produzir, uma linha de bobina **por linha de cor**, pré-selecionando
bobina cujo `material_version_id` case com o da linha quando houver.

## 9. API e PDF

### 9.1 Contrato das linhas

`QuoteItemOut` ganha:

```python
filaments: list[QuoteItemFilamentOut] = []   # id, material_id, material_name,
                                             # material_color, grams_unit, position
```

`material_id` e `is_multi_color` **continuam** em `QuoteItemOut`. O primeiro é o
derivado da linha 1 (invariante 2) e o front atual já o usa para pré-selecionar o
dropdown; removê-lo quebraria a tela sem ganho.

Edição das linhas por **substituição da lista inteira**, não por endpoint por
linha:

```python
class QuoteItemUpdate(BaseModel):
    ...
    filaments: list[QuoteItemFilamentIn] | None = None   # None = não mexer
```

Razão: as invariantes 1, 2 e 4 são sobre o **conjunto** (pelo menos uma linha,
`position` contígua, derivado igual à linha 1). Validar um conjunto num PATCH que
recebe o conjunto é direto; validá-lo em três endpoints que mexem numa linha cada
exige reconstruir o conjunto em cada um — três lugares para a mesma regra
divergir. `None` preserva as linhas, para que um PATCH que só muda `name` não as
apague.

`material_id` no PATCH e `filaments` no mesmo PATCH é **400**: dois jeitos de
dizer a mesma coisa, e adivinhar qual vale é como se escreve um bug.
`material_id` sozinho continua funcionando e passa a reescrever a linha 1.

### 9.2 PDF

`quote.html:16-22` hoje imprime **um** material por item — `material_name` ·
`material_color`, com um `· multicolor` pendurado no `is_multi_color` quando cai
no ramo de fallback. Com N linhas isso esconde a informação que o cliente está
pagando.

O macro `material_label(it)` passa a listar as linhas:

```
Material
  PLA Preto · 12,34 g
  PLA Vermelho · 5,67 g
  PETG Branco · 0,89 g
```

Em `retail_mode` (que já esconde tempo e filamento) as gramas saem e ficam só os
nomes das cores — o modo existe para não expor custo, e a cor é informação de
produto, não de custo.

Item de uma linha imprime exatamente como hoje, sem lista e sem bullet: é o caso
majoritário e o PDF não deve ficar mais pesado por causa de uma feature que ele
não usa. Teste de regressão cobre isso — o PDF de um orçamento de uma cor não
muda.

## 10. Testes

**Custo (o coração)**
- Item com 2 cores e `quantity = 3`: filamento soma as duas linhas × 3; energia e
  depreciação contam o `time_s` **uma vez** × 3. Este é o teste que pega a
  armadilha da seção 5 — precisa ter mais de uma cor **e** quantidade > 1, senão
  não distingue as duas regras.
- Preços diferentes por linha entram separados, não por média.
- Linha com `grams_unit` preenchido ignora refugo, inclusive num item marcado
  `is_multi_color`.
- Linha de `grams_unit NULL` num item `is_multi_color` **mantém** os 20% — é a
  asserção que protege o custo histórico, e ela falha se alguém "simplificar" a
  regra de refugo para depender da contagem de linhas.
- `pricing` e `accounting` concordam num item multicor (estende o teste do PR #32).

**Produção**
- 3 linhas sem `grams` explícito → **409**, e o estoque **não** é debitado
  (a asserção sobre o estoque é o que importa; um 409 sem checar o débito não
  prova que não debitou antes de falhar).
- Cada linha debita da sua bobina, com a densidade do seu material.
- Bobina de material divergente produz aviso e **conclui** a produção.

**Migrações**
- `0034`: o SQL do backfill, aplicado a um item criado sem linha, cria exatamente
  uma linha com `position=1` e `grams_unit IS NULL`; rodar duas vezes não
  duplica. Item com `material_version_id IS NULL` fica sem linha, sem erro.
- `0034`: **o custo de um item é igual antes e depois de o backfill rodar** — é o
  teste que prova que a migração não mexe em dinheiro.

  Forma do teste: `conftest.py` roda `alembic upgrade head` antes de qualquer
  dado existir, então "criar dados antigos e migrar" não é escrevível aqui (ver
  o docstring de `backend/tests/api/test_quote_seq.py`). O SQL do backfill vive
  numa constante da migração; o teste a importa e executa contra itens que ele
  mesmo criou pelo ORM. É o mesmo SQL que roda em produção.
- `0035`: casamento único preenche; casamento ambíguo deixa `NULL`; rodar duas
  vezes não muda nada.
- `downgrade` de ambas roda limpo num banco com dados.

**Invariantes**
- Remover a última linha é rejeitado (invariante 1).
- `quote_items.material_version_id` nunca divergir da linha 1 (invariante 2) —
  teste que cria, reordena e remove linhas, conferindo o derivado ao final de
  **cada** operação, não só no fim.
- Salvar duas linhas com `grams_unit NULL` é rejeitado (invariante 3). Sem esta
  asserção o cálculo da seção 5 cairia no ramo de derivação do `gcode_meta` para
  as duas, contando o filamento do item inteiro duas vezes.
- Remover a linha do meio renumera `position` para contígua (invariante 4).

**API**
- `filaments` e `material_id` no mesmo PATCH → **400**.
- `material_id` sozinho reescreve a linha 1 e não duplica linhas.
- PATCH sem `filaments` (só `name`, por exemplo) **preserva** as linhas — a
  regressão óbvia é um `None` tratado como lista vazia, que as apagaria.
- `QuoteItemOut.filaments` vem ordenado por `position`, e o número de queries não
  cresce com o número de itens do orçamento (o mesmo padrão de lote que a Spec 2
  impôs no contábil).

**Consumo e PDF**
- Consumo gravado com `quote_item_filament_id` aparece atrelado à sua cor;
  consumo histórico (`NULL`) continua aparecendo como hoje.
- Duas cores e uma reimpressão no mesmo item: as quatro linhas de consumo se
  separam corretamente entre cor e tentativa — é o caso que motiva a coluna
  (4.3), e um teste só com duas cores não o distinguiria de um só com duas
  tentativas.
- **PDF de item de uma cor é idêntico ao atual** (regressão). O PDF de item
  multicor lista as cores, e em `retail_mode` lista sem as gramas.

## 11. Riscos

| Risco | Mitigação |
|---|---|
| Somar `time_s` por linha de cor, multiplicando energia e depreciação | Escrito na seção 5, e o teste de custo usa 2 cores **com** quantidade 3, onde a confusão aparece |
| Débito triplo de estoque ao produzir multicor | 409 obrigatório quando falta `quote_item_filament_id`; teste assere que o estoque ficou intacto |
| `material_version_id` derivado divergir da linha 1 | Mantido em um único ponto do app, com teste que reordena e remove |
| Backfill congelar gramas e parar de reprecificar o histórico | `grams_unit` nullable; backfill estrutural; teste de custo antes/depois |
| Casamento ambíguo em `0035` vincular a bobina ao material errado | Casa só quando o candidato é único; o resto fica `NULL` |
| Medallion reportar cor errada sem ninguém notar | Documentado na seção 7 com o ponto exato; o app não depende disso para funcionar |
| `multi_color_waste_pct` virar campo morto e confundir | Continua valendo para linhas de `grams_unit NULL`; tabela de refugo na seção 4, decisão em 3.3 |
| PATCH que não menciona `filaments` apagar as linhas (`None` tratado como lista vazia) | `None` = "não mexer", explícito em 9.1, com teste que faz PATCH só de `name` |
| Duas linhas `NULL` contarem o filamento do item duas vezes | Invariante 3 rejeita; é a asserção que protege a fórmula da seção 5 |
| PDF de orçamento de uma cor mudar sem ninguém notar | Teste de regressão: uma cor imprime idêntico ao atual |
| Consumo de multicor virar indistinguível de reimpressão | `quote_item_filament_id` (4.3); teste com 2 cores **e** 1 reimpressão no mesmo item |

## 12. Critério de pronto

- `make test` verde; lint dos arquivos alterados sem erro novo no conjunto
  `E4,E7,E9,F` (a base do projeto é vermelha — ver memória).
- `alembic upgrade head` e `alembic downgrade -1` limpos num banco com dados.
- Item com 3 cores orça, produz e aparece no contábil com o CPV somando as três.
- Energia e depreciação de um item multicor **não** crescem com o número de cores.
- Custo de todo orçamento histórico inalterado após as duas migrações.
- PDF de orçamento multicor lista as cores; PDF de uma cor não mudou.
- `QuoteItemOut.consumptions` distingue cor de tentativa num item multicor
  reimpresso.
- Seção 7 entregue ao Otavio como lista de trabalho do outro repositório.
