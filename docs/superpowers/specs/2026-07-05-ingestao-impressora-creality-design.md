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
que empurra** (push). Um **container Docker** na rede faz o `GET` async no Moonraker
(que está do lado dele) e o `POST` autenticado pro Lightsail. Roda no notebook agora;
como é imagem Docker, é só re-dockar num Raspberry (ou qualquer host da LAN) depois.
Nada da LAN é exposto à internet; o Lightsail nunca precisa alcançar a rede de casa.

## 3. Arquitetura

```
K1 (Moonraker, LAN)
      │  GET async /server/history/list
      ▼
Agente local (container Docker: notebook agora, portável p/ Pi)  ── repo SEPARADO
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

**Repo separado (agente, container Docker) — fora deste repo:**
- Poller **async** do Moonraker que implementa o **contrato de ingestão** da seção 8.
- Empacotado como imagem Docker: roda no notebook hoje, portável pra Pi/qualquer host da LAN.
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
| `quote_id` | UUID FK null | preenchido no atachar |
| `spool_id` | UUID FK null | spool escolhido no atachar (migração 0031); pré-preenche o Produzir |
| `created_at` | DateTime tz | server default |

Índice único em `(machine, job_uid)`.

## 7. Conversão mm → gramas

Moonraker dá `filament_used` em **mm**. Converte-se `mm → m` (`/1000`) e depois
`m → gramas` reusando a **densidade do PLA já usada no sistema** (mesmo caminho de
`grams_for_item` / spec `orcamento-gramas`). Sem lógica de conversão nova. A densidade
final usada na baixa é a do **spool escolhido no link** (a impressora só sabe "genérico").

## 8. Atachar — `POST /printer-jobs/{id}/link`  (atachar ≠ produzir)

> **Decisão revisada (2026-07-05):** o atachar é **controle manual** e NÃO produz.
> Ele só **prepara** o orçamento; a baixa de estoque acontece depois, no passo
> **Produzir** que já existe. Reverte a "opção A" (atachar = produz na hora).

**Body:** `{ "quote_id": "...", "spool_id": "..." }`

Comportamento:
1. Valida que o job existe (senão 404) e está `PENDING` (senão 409). Re-atachar
   é bloqueado porque um job já `LINKED` não é mais `PENDING`.
2. Valida que o orçamento existe (senão 404) e tem ao menos um item (senão 409).
   **Não** valida status de produção nem exige material resolvido — atachar não
   produz, então não há pré-condição de `produce` aqui.
3. **Alocação por item:** distribui `filament_used_mm` entre os itens
   proporcionalmente às gramas estimadas de cada item (fallback: divisão igual),
   e converte a fração de cada item em gramas reais pela densidade do item
   (seção 7). Quote com 1 item → todas as gramas no item.
4. **Grava o real no item:** escreve `filament_g` (gramas reais) e `time_s`
   (tempo real, fração do item) no `gcode_meta` de cada item. É isso que faz o
   `produce` seguinte debitar a quantidade real (o `produce` já lê `filament_g`).
5. **Registra no job:** `quote_id`, `spool_id` escolhido, `grams` (total real),
   `inbox_status = LINKED`. **Não** debita spool, **não** cria
   `MaterialConsumption`, **não** muda o status do orçamento.
6. Requer nova coluna `printer_jobs.spool_id` (FK spools, nullable) — guarda o
   spool escolhido no atachar para o `produce` pré-selecioná-lo.

**Passo seguinte (já existe):** o usuário abre o orçamento e clica **Produzir**.
O modal de produzir vem **pré-preenchido com o spool atachado** (via
`printer_jobs.spool_id` do job ligado ao quote) e debita pelas gramas reais
(`filament_g` gravado no passo 4). Uma baixa só, no controle do usuário.

**Jobs `cancelled`/`error`:** entram no inbox (PENDING); o usuário descarta
(`DELETE` → DISCARDED) ou atacha a um orçamento à vontade (v1 não automatiza
`falhou`).

## 9. UX (frontend)

- Os `printer_jobs` PENDING aparecem **dentro do Inbox**, numa seção "Impressora"
  ao lado dos `.gcode` do watcher (não em página separada).
- Cada linha: `filename`, `machine`, gramas reais, tempo, status.
- Ação **"Atachar"**: seletor de **orçamento** (que o usuário criou) + seletor de
  **spool**. Ao confirmar, chama `/printer-jobs/{id}/link`, o job sai da lista, e
  a UI orienta a seguir no orçamento e clicar **Produzir**.
- No orçamento, o modal **Produzir** pré-seleciona o spool atachado.
- Ação **"Descartar"** → `DELETE`.
- Segue o padrão visual do inbox existente (usar skill `frontend-design`).

## 10. Segurança

- `AGENT_INGEST_TOKEN` em env var (`.env` / secret do Lightsail), fora do git.
- Ingestão só aceita o token do agente; nenhum outro endpoint fica exposto sem sessão.
- O agente guarda o token localmente (env var do container); TLS no `POST` pro Lightsail (HTTPS já existe).

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
- Empacotamento/deploy do agente (Dockerfile, compose) — vive no repo separado.
