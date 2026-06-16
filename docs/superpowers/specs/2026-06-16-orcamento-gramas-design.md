# Orçamento — informar gramas gastas como base de custo

**Data:** 2026-06-16
**Status:** aprovado no brainstorming, pronto para plano de implementação.

## 1. Objetivo

Hoje o item do orçamento só guarda **metros** de filamento (`filament_m`, do gcode ou
editado na mão) e as **gramas são sempre derivadas** (`metros × área × densidade`); o
custo sai de `gramas × preço/kg` (com um `waste_pct` de refugo aplicado por cima).

Permitir **informar as gramas gastas diretamente** no item, como base alternativa de
custo — útil quando o usuário tem o peso pelo resumo do slicer (Creality Print já
reporta o filamento total, incluindo brim/suporte/purga) ou pesando o carretel.

## 2. Dado e regra de custo

- Novo campo opcional **`filament_g`** dentro do `gcode_meta` do item — gramas **por
  peça**, valor **final** (sem refugo).
- **Gramas efetivas por peça:**
  - se `filament_g` preenchido e `> 0` → `gramas_unidade = filament_g` (sem `waste_pct`);
  - senão → `gramas_unidade = grams_from_meters(filament_m, densidade, diâmetro)` e aplica
    `waste_pct` (comportamento atual).
  - total do item = `gramas_unidade × quantity`.
- Custo do filamento segue `gramas × preço/kg`. `filament_m` continua guardado e
  alimentando analytics/calibração/LLM — só **não** manda no custo quando há `filament_g`.
- **Escopo:** afeta apenas o **custo orçado** (total do orçamento e o
  `quote_total`/`cpv_calc`-orçado materializado na Contábil). **Não** mexe no consumo real
  (`MaterialConsumption`/CPV de produção), que vem da baixa de estoque.

## 3. Helper compartilhado

Novo helper único (em `backend/core/quote_service.py`):

```
effective_grams_per_unit(meta: dict, density, diameter_mm, waste_pct) -> Decimal
```

Encapsula a regra da Seção 2 (override vs. derivação+refugo). É a **fonte única** da
conversão; os dois caminhos de custo passam a chamá-lo, eliminando a derivação duplicada:

1. `gcode_to_item_input` e `grams_for_item` (caminho do **total do orçamento** usado em
   `backend/api/routes/quotes.py`).
2. `compute_quote_costs` em `backend/core/accounting/cost.py` (o `catalog_filament` que
   vira `cost_orcado`/`quote_total` na Contábil).

Como ambos chamam o mesmo helper, o total do orçamento e o valor materializado na Contábil
continuam batendo, agora respeitando o override.

## 4. API e UI

- **API:** `QuoteItemUpdate` ganha `filament_g: float | None`. A rota de update grava em
  `gcode_meta["filament_g"]`; quando vier `null`/`0`, **remove** a chave (volta à derivação
  por metros). `QuoteItemOut.gcode_meta` já expõe o campo.
- **UI (editor do item):** campo **"Gramas (gastas)"** ao lado do editor de metros, com dica
  *"se preenchido, ignora os metros pro custo"*. O resumo de custo do item mostra as gramas
  efetivas.
- **PDF:** onde aparece o filamento, refletir as gramas efetivas (sem mudar layout).

## 5. Testes

- **Backend:**
  - `effective_grams_per_unit`: override ganha (sem refugo); sem override deriva dos metros
    **com** refugo; `filament_g` ausente/`0` cai na derivação.
  - Total do orçamento com gramas digitadas (custo bate com `filament_g × preço/kg`).
  - `compute_quote_costs` honra o override (orçamento ↔ Contábil batem).
  - Update de item: gravar `filament_g`; enviar `null`/`0` limpa a chave.
- **Frontend:** `npm run check`.

## 6. Fora de escopo (YAGNI)

- Toggle explícito metros-XOR-peso (decidimos por override simples).
- Recalcular `filament_m` a partir das gramas (densidade inversa) — metros seguem do gcode.
- Alterar o consumo real/CPV de produção.
