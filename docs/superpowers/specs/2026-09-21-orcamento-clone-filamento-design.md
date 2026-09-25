# Spec 3 — Orçamentos: clonar e ver o filamento realmente usado

**Data:** 2026-09-21
**Status:** aprovado no brainstorming, aguardando revisão da spec
**Depende de:** Spec 0 (pacote `quotes/`, helpers) e Spec 1 (`#0042`)
**Atende aos pedidos:** #4 (replicar orçamento), #5 (filamento exato no orçamento fechado)

## 1. Contexto

Dois pedidos independentes que caem no mesmo par de arquivos
(`backend/api/routes/quotes/`, `frontend/src/routes/quotes/`):

- **Repetição manual.** Um pedido parecido com um anterior é refeito do zero:
  reupload de gcode, remontagem de itens, redigitação de markup. Não há clone.
- **Filamento invisível.** Depois que o orçamento sai de rascunho, a coluna
  Material mostra `gcode_meta.material` — só o polímero ("PLA"). A bobina
  efetivamente debitada está em `material_consumptions`, com gramas, custo
  congelado e data, e nunca sobe para a API. O dado existe; falta exibi-lo.

**Nenhuma migração nesta spec.** Ambos os pedidos são atendidos com o schema atual.

## 2. Escopo

**Dentro:** `POST /quotes/{id}/clone` com cópia de arquivos; `consumptions` em
`QuoteItemOut`; painel "Filamento consumido" e coluna Material corrigida.

**Fora:** rastrear no banco a origem do clone (decidido: não — ver 3.5); expor
consumo no PDF (ver 4.4); clonar orçamento parcialmente (escolher itens).

## 3. Clonar orçamento — pedido #4

### 3.1 Endpoint

```
POST /quotes/{quote_id}/clone   →  201  QuoteOut (o novo rascunho)
```

Sem payload. Qualquer status de origem é clonável; o clone nasce sempre `draft`.

### 3.2 O que é copiado

| Origem | Copiado | Observação |
|---|---|---|
| `kind`, `client_id`, `markup_pct`, `min_charge`, `retail_mode`, `notes` | sim | precificação e cliente preservados; tudo editável no rascunho |
| `quote_items` | sim | `name`, `filename`, `gcode_meta`, `material_version_id`, `quantity`, `depreciation_rate_override`, `failure_rate_override`, `is_multi_color`, `model_source_*`, `asset_id` |
| arquivo `.gcode` em disco | sim | ver 3.3 |
| `quote_services` | sim | `service_id`, `quantity`, `rate` — preserva o valor praticado, não o de tabela |
| `quote_photos` | sim | arquivo copiado e `quote_item_id` remapeado — ver 3.4 |
| `quote_people` | sim | atribuição de projeto pessoal |

**Não copiado:** `status` (nasce `draft`), todos os timestamps (`finalized_at`,
`approved_at`, `produced_at`, `delivered_at`, `cancelled_at`),
`material_consumptions`, `production_events`, linha em `sales`. O clone é um
orçamento novo que ainda não aconteceu.

### 3.3 Arquivo de gcode

`save_gcode` grava em `<STORAGE_DIR>/gcodes/<quote_id>/<filename>` e `QuoteItem`
guarda o caminho relativo. Copiar apenas o registro faria o item do clone apontar
para a pasta do orçamento original — e o `reparse` do clone, ou qualquer limpeza
do orçamento antigo, quebraria silenciosamente.

O clone copia os bytes para `gcodes/<novo_quote_id>/<filename>` e grava o caminho
novo. Origem ausente em disco (histórico anterior ao armazenamento) não aborta o
clone: o item é copiado sem `filename`, e a resposta indica quantos itens vieram
sem arquivo.

### 3.4 Fotos

`save_photo` grava em `quote_photos/<uuid>.jpg` — diretório **plano**, sem pasta
por orçamento — e `delete_photo` remove o arquivo do disco. Compartilhar
`storage_path` entre original e clone faria com que apagar a foto do original
apagasse a imagem do clone.

O clone copia os bytes para um `uuid` novo (reusando `save_photo` sobre os bytes
lidos, o que também reencoda de forma consistente) e remapeia `quote_item_id`
para o item correspondente do clone. `sort_order` preservado.

### 3.5 Rastreabilidade sem coluna

Decidido não adicionar `quotes.cloned_from_id`. Em lugar disso, o clone recebe
`"Clone de #0042"` como primeira linha das `notes`, antes do conteúdo copiado.
Rastreabilidade legível, zero migração, e o campo já é livre.

O número `#0042` vem da Spec 1 — é a razão de esta spec depender dela.

### 3.6 Implementação

Em `backend/api/routes/quotes/crud.py` (pacote da Spec 0). Toda a cópia numa
transação: falha em qualquer ponto não deixa orçamento meio-clonado.

Os arquivos em disco são o ponto sem transação. Ordem: gravar arquivos primeiro,
depois commitar; se o commit falhar, remover os arquivos gravados. Arquivo órfão
é preferível a registro apontando para arquivo inexistente.

### 3.7 UI

- Lista de orçamentos: botão `clonar` ao lado de `abrir`.
- Detalhe, painel Ações: `clonar`, disponível em qualquer status.
- Após clonar, navega para `/quotes/<novo_id>`.
- Enquanto clona, botão em `pending` (helper da Spec 0) — copiar arquivos leva
  tempo perceptível com muitas fotos.

## 4. Filamento exato — pedido #5

### 4.1 O dado que já existe

`material_consumptions` grava, por item e por ciclo de produção: `spool_id`,
`grams_used`, `unit_cost_snapshot` (custo por grama congelado no momento da
baixa) e `consumed_at`. Reimpressão após falha gera **linhas adicionais** — o
histórico completo está lá.

### 4.2 API

`QuoteItemOut` ganha:

```python
class ConsumptionOut(BaseModel):
    spool_id: str
    spool_label: str          # "PLA · Preto · Voolt3D · a3f9c1d2"
    material_type: str
    color: str | None
    manufacturer: str | None
    grams_used: Decimal
    unit_cost_snapshot: Decimal
    custo_total: Decimal      # grams_used * unit_cost_snapshot, já calculado
    consumed_at: datetime

class QuoteItemOut(BaseModel):
    ...
    consumptions: list[ConsumptionOut] = []
```

`spool_label` segue o formato já usado na tela de produzir, para que o usuário
reconheça a mesma bobina nos dois lugares.

Carregado em `_quote_out` com **uma** query para o orçamento inteiro
(`selectinload` sobre os itens + join com `spools`), não uma por item. Em
rascunho a lista vem vazia, porque ainda não houve baixa.

### 4.3 UI — detalhe do orçamento

**Coluna Material**, fora de rascunho: deixa de mostrar `gcode_meta.material` e
passa a mostrar a bobina real (`cor · fabricante`), com o polímero ao lado.
Havendo mais de um consumo, mostra o mais recente com indicador de que há
histórico. Sem consumo (orçado, nunca produzido), mantém o comportamento atual e
o rótulo fica marcado como estimativa.

**Painel novo "Filamento consumido"**, abaixo de Peças, visível quando existe ao
menos um consumo:

```
Filamento consumido                                       · 3 baixas

Peça             Bobina                        Gramas    Custo     Data
porta-caneta     PLA · Preto · Voolt3D          48,2 g   R$ 4,82   12/09
suporte          PETG · Azul · 3DLab            31,0 g   R$ 3,72   12/09
porta-caneta     PLA · Preto · Voolt3D          48,2 g   R$ 4,82   14/09  ← reimpressão
                                              ─────────────────
                                              127,4 g   R$ 13,36
```

A data distingue os ciclos. Hoje, uma reimpressão após falha consome material
duas vezes e a tela não registra nenhuma das duas.

### 4.4 PDF

Não incluir. É custo interno, e `retail_mode` existe justamente para esconder
composição de custo do cliente. Fica só na tela.

## 5. Testes

**Clone**
- Clone de orçamento entregue nasce `draft`, sem nenhum timestamp de ciclo.
- Itens, serviços, fotos e pessoas são copiados na quantidade certa.
- Arquivo de gcode existe em `gcodes/<novo_id>/` e difere do caminho de origem.
- Apagar a foto do original **não** afeta a foto do clone (regressão da 3.4).
- `quote_item_id` das fotos do clone aponta para itens do clone, nunca do original.
- `notes` do clone começa com `"Clone de #<seq do original>"`.
- Clone **não** cria `material_consumptions`, `production_events` nem linha em `sales`.
- Clonar um orçamento sem gcode em disco não falha; resposta indica os itens sem arquivo.
- Falha simulada no commit não deixa arquivo órfão referenciado por registro.
- Clonar orçamento pessoal preserva `kind` e as pessoas atribuídas.

**Filamento**
- `consumptions` vazio em rascunho.
- Após `produce`, traz bobina, gramas, custo unitário e `custo_total` corretos.
- Ciclo falhou → reproduzido gera duas entradas, ordenadas por `consumed_at`.
- `unit_cost_snapshot` não muda quando o preço da bobina muda depois (congelamento).
- Contagem de queries de `GET /quotes/{id}` não cresce com o número de itens.

**E2E**
- Clonar da lista abre o rascunho novo com os mesmos itens.
- Orçamento produzido exibe o painel com a bobina correta.

## 6. Riscos

| Risco | Mitigação |
|---|---|
| Clone compartilhando arquivo faz o original apagar a imagem do clone | Cópia dos bytes com `uuid` novo; teste de regressão explícito |
| `quote_item_id` de foto apontando para item do original | Remapeamento por dicionário item-antigo → item-novo; teste explícito |
| Arquivo gravado e commit falhando deixa registro quebrado | Arquivos primeiro, commit depois, limpeza no erro; órfão é o modo de falha aceito |
| Clonar com muitas fotos demora e parece travado | Estado `pending` no botão |
| `consumptions` reintroduzindo N+1 | Uma query por orçamento; teste de contagem de queries |

## 7. Critério de pronto

- `make test`, `make lint` e `make e2e` verdes.
- Clonar um orçamento entregue produz um rascunho utilizável sem nenhum reupload.
- Orçamento fora de rascunho mostra a bobina real, não só o polímero.
- Reimpressão após falha aparece como linha própria no painel de consumo.
- Nenhuma migração criada.
