# Ingestão de jobs da impressora (Creality K1 / Moonraker) → vínculo a orçamento

**Data:** 2026-07-05
**Status:** aprovado no brainstorming, aguardando revisão da spec

## 1. Contexto e objetivo

Hoje o serviço captura gcode por um **watcher de pasta** (`watcher_inbox_files`):
o parser lê a *estimativa* do slicer e o "promote" **cria um orçamento novo**.

O que falta: capturar o que **realmente foi impresso** na Creality K1 e **vincular
a um orçamento existente**, baixando o **filamento real** do estoque. A impressora
só reporta "PLA genérico" — então o job traz **gramas reais + tempo real**, e o
usuário só resolve duas coisas na tela: *qual orçamento* e *qual spool foi usado*.

A K1 roda **Klipper + Moonraker**, cuja REST HTTP local é a fonte confiável
(a Creality Cloud não tem API oficial pública — engenharia reversa instável, fora).

## 2. Restrição central: nuvem ↔ LAN

O serviço roda no **Lightsail (nuvem)**; a impressora está na **LAN de casa/loja**.
A nuvem **não** alcança `192.168.x.x` diretamente. Solução escolhida: **agente local
que empurra** (push). Um Raspberry Pi Zero na rede faz o `GET` no Moonraker (que está
do lado dele) e o `POST` autenticado pro Lightsail. Nada da LAN é exposto à internet;
o Lightsail nunca precisa alcançar a rede de casa.

## 3. Arquitetura

```
K1 (Moonraker, LAN)
      │  GET /server/history/list
      ▼
Agente local (Raspberry Pi Zero)  ── repo SEPARADO
      │  POST (Bearer token do agente)
      ▼
Lightsail: POST /ingest/print-jobs
      │  insert idempotente
      ▼
printer_jobs (inbox_status = PENDING)
      │  usuário abre a aba "Impressora" do inbox e "linka":
      │  { quote_id, spool_id }
      ▼
POST /printer-jobs/{id}/link
      │  == produce com gramas REAIS + baixa do spool escolhido
      ▼
Quote em_producao • MaterialConsumption debitado • printer_jobs = LINKED
```

## 4. Escopo

**Neste repo (`3d_analytics`):**
- Tabela `printer_jobs` + migração.
- `POST /ingest/print-jobs` (auth por token de agente, idempotente).
- `GET /printer-jobs` + `POST /printer-jobs/{id}/link` + `DELETE /printer-jobs/{id}`.
- Conversão mm → gramas (reusa densidade já existente).
- Aba "Impressora" no inbox (frontend), reaproveitando a UX do inbox atual.
- Testes.

**Repo separado (agente, Raspberry Pi Zero) — fora deste repo:**
- Poller do Moonraker que implementa o **contrato de ingestão** da seção 8.
- A spec define o contrato pra que o repo do agente seja construído contra ele.

## 5. Contrato de ingestão — `POST /ingest/print-jobs`

- **Auth:** header `Authorization: Bearer <AGENT_INGEST_TOKEN>`. Token estático em
  env var no serviço (não é sessão de usuário). 401 se ausente/errado.
- **Idempotência:** chave `(machine, job_uid)`. Reenvio do mesmo job **não duplica**
  (retorna 200 com o registro existente; não sobrescreve estado já `LINKED`/`DISCARDED`).
- **Body:**

```json
{
  "machine": "K1-oficina",
  "job_uid": "000042",
  "filename": "suporte_fone.gcode",
  "status": "completed",              // completed | cancelled | error
  "filament_used_mm": 3421.7,
  "print_duration_s": 5234.0,
  "started_at": "2026-07-05T14:02:11Z",
  "finished_at": "2026-07-05T15:29:25Z",
  "raw": { ... }                       // payload bruto do Moonraker, guardado em JSONB
}
```

- **Resposta:** `{ "id": "...", "inbox_status": "PENDING" }` (ou o registro já existente).
- **Validação:** `status` num enum conhecido; números não-negativos; `machine`/`job_uid`
  obrigatórios. `filament_used_mm`/`print_duration_s` podem vir 0 (o usuário completa no link).

## 6. Modelo de dados — `printer_jobs`

Tabela **irmã** do inbox do watcher, não reuso de `watcher_inbox_files`: a semântica
difere (consumo real vs estimativa; linka orçamento existente vs cria novo). Rota
própria e testável isolada; apresentada na mesma UX de inbox.

| coluna | tipo | nota |
|---|---|---|
| `id` | UUID PK | |
| `machine` | str | nome lógico da impressora |
| `job_uid` | str | `job_id` do Moonraker |
| `filename` | str | nome do gcode impresso |
| `status` | str | completed / cancelled / error |
| `filament_used_mm` | Numeric | real, do Moonraker |
| `time_s` | Numeric | `print_duration` real |
| `grams` | Numeric null | derivado (mm → g); ver seção 7 |
| `started_at` / `finished_at` | DateTime tz | |
| `raw` | JSONB | payload bruto |
| `inbox_status` | str | PENDING / LINKED / DISCARDED |
| `quote_id` | UUID FK null | preenchido no link |
| `created_at` | DateTime tz | server default |

Índice único em `(machine, job_uid)`.

## 7. Conversão mm → gramas

Moonraker dá `filament_used` em **mm**. Converte-se `mm → m` (`/1000`) e depois
`m → gramas` reusando a **densidade do PLA já usada no sistema** (mesmo caminho de
`grams_for_item` / spec `orcamento-gramas`). Sem lógica de conversão nova. A densidade
final usada na baixa é a do **spool escolhido no link** (a impressora só sabe "genérico").

## 8. Vínculo — `POST /printer-jobs/{id}/link`  (opção A: link = produce real)

**Body:** `{ "quote_id": "...", "spool_id": "..." }`

Comportamento:
1. Valida que o job está `PENDING` (senão 409).
2. Valida o orçamento no mesmo critério do `produce` existente
   (`t_produce`, `quotes.py:708-718`): comercial em `aprovado`/`falhou`,
   pessoal em `draft`/`falhou`. Caso contrário 409 com mensagem clara.
3. Calcula `grams` reais a partir de `filament_used_mm` + densidade do spool (seção 7).
4. **Executa a mesma máquina do `produce`** com override direto de gramas
   (`ProduceRequest.consumption[].grams`, já suportado em `quotes.py:726-728`):
   debita o spool escolhido, cria `MaterialConsumption`, move o quote pra `em_producao`.
5. **Alocação por item:** o usuário escolhe **um** spool pro job.
   - Quote com **1 item** → todas as gramas reais no item.
   - Quote com **N itens** → distribui proporcionalmente às gramas estimadas de cada
     item (fallback: divisão igual). Uma `MaterialConsumption` por item, somando o total real.
6. Persiste `time_s` e `grams` reais no `gcode_meta` dos itens (campos que o analítico
   de variância já lê), para comparar **estimado (slicer) × real (impressora)**.
7. Marca `printer_jobs.inbox_status = LINKED`, grava `quote_id`. Re-link bloqueado (409).

**Jobs `cancelled`/`error`:** ainda entram no inbox (PENDING). O usuário pode
descartá-los (`DELETE` → DISCARDED) ou linká-los a um orçamento que vá `falhou`
(fora do v1 automatizar isso; por ora o link só cobre o caminho de produzir com sucesso).

## 9. UX (frontend)

- Nova aba **"Impressora"** no inbox, ao lado do inbox de gcode atual.
- Lista os `printer_jobs` PENDING: `filename`, `machine`, gramas reais, tempo, status.
- Ação "Linkar": seletor de **orçamento** (elegíveis pra produce) + seletor de **spool**.
  Ao confirmar, chama `/printer-jobs/{id}/link` e o item some da lista.
- Ação "Descartar" → `DELETE`.
- Segue o padrão visual do inbox existente (usar skill `frontend-design` na implementação).

## 10. Segurança

- `AGENT_INGEST_TOKEN` em env var (`.env` / secret do Lightsail), fora do git.
- Ingestão só aceita o token do agente; nenhum outro endpoint fica exposto sem sessão.
- O agente guarda o token localmente no Pi; TLS no `POST` pro Lightsail (HTTPS já existe).

## 11. Testes

- **Conversão** mm → gramas (unit).
- **Ingestão:** idempotência `(machine, job_uid)`; auth por token (401 sem/errado);
  mapeamento de `status`; aceita números 0.
- **Link:** debita o spool certo com as gramas reais; linka o quote; marca LINKED;
  re-link bloqueado; orçamento em estado inválido → 409; alocação 1-item e N-itens.
- **Contrato do agente:** exemplo de payload do `/server/history/list` do Moonraker
  usado como fixture, para o repo do agente validar contra o mesmo formato.

## 12. Fora de escopo / futuro

- Automatizar `falhou` a partir de job `cancelled`/`error`.
- Live status (job em andamento) — hoje só jobs finalizados.
- Múltiplos filamentos por job (AMS/multicolor) — v1 assume um spool por job.
- Empacotamento do agente (systemd no Pi) — vive no repo separado.
