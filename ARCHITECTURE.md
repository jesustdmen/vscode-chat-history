# Arquitetura — chatsvs-pipeline

> Documento gerado em 2026-05-17 via auditoria técnica. Última atualização: 2026-05-18. Atualizar sempre que a arquitetura mudar.

## Visão Geral

Pipeline local em 3 estágios para extração de histórico de chat do VS Code:

```
AppData (Windows) → [INGEST] → snapshot raw → [NORMALIZE] → JSONL canônico → [REPORT] → análises
                                                                     ↓
                                                              [VIEWER Streamlit]
```

## Estágios do Pipeline

### Stage 1: Ingest (`pipeline/01_ingest/ingest.py`)

**Responsabilidade:** Criar snapshot imutável dos dados do VS Code.

- Lê: `%APPDATA%\Code\User\` (globalStorage, workspaceStorage), `~\.codex\sessions\` e `~\.claude\projects\`
- Copia para: `pipeline/output/raw/snapshot_YYYYMMDD_HHmmss/`
- Extrai chaves SQLite relevantes para sidecars `.vscdb.keys.jsonl`
- Rastreia fingerprints (mtime_ns + size) para processamento incremental
- Mantém apenas os 2 snapshots mais recentes (limpeza automática)

**Fontes lidas (read-only):**

| Fonte | Localização |
|---|---|
| globalStorage/state.vscdb | `%APPDATA%\Code\User\globalStorage\` |
| workspaceStorage/state.vscdb | `%APPDATA%\Code\User\workspaceStorage\<hash>\` |
| chatSessions/*.json/.jsonl | `workspaceStorage\<hash>\chatSessions\` |
| chatEditingSessions/ | `workspaceStorage\<hash>\chatEditingSessions\` |
| emptyWindowChatSessions/ | `globalStorage\emptyWindowChatSessions\` |
| Codex CLI sessions | `~\.codex\sessions\`, `~\.codex\archived_sessions\` |
| Claude Code CLI sessions | `~\.claude\projects\<slug>\<uuid>.jsonl` |

---

### Stage 2: Normalize (`pipeline/02_normalize/`)

**Responsabilidade:** Converter 7 tipos de fonte para o modelo canônico.

**Componentes:**

| Arquivo | Responsabilidade |
|---|---|
| `normalize.py` | Orquestrador; decide o que reprocessar via cache de shards |
| `parsers.py` | 9 parsers especializados (um por tipo de fonte) |
| `aggregator.py` | `build_summaries()` — agrupa ChatMessage em SessionSummary |
| `pipeline/lib/patch.py` | Reconstrução de sessões ativas em formato de patch JSONL |

**Cache de shards:**
- Chave: `SHA1("v3:" + file_type + ":" + source_path)`
- Invalida automaticamente se fingerprint mudou OU se `shard_schema_version` foi bumped
- Shards obsoletos (fontes deletadas) são removidos a cada run

**Tipos de fonte suportados:**

| source | Descrição |
|---|---|
| `chat_session_json` | `chatSessions/<uuid>.json` (estado final) |
| `chat_session_jsonl` | `chatSessions/<uuid>.jsonl` (patches ativos) |
| `chat_editing_state` | `chatEditingSessions/<uuid>/state.json` |
| `chat_session_index` | SQLite → `chat.ChatSessionStore.index` |
| `openai_chatgpt` | SQLite → `openai.chatgpt` |
| `agent_sessions` | SQLite → `agentSessions.state.cache` |
| `copilot_jsonl` | `workspaceStorage/<hash>/*.jsonl` (formato legado) |
| `codex_session` | `~/.codex/sessions/*.jsonl` |
| `claude_code_session` | `~/.claude/projects/<slug>/<uuid>.jsonl` |

---

### Stage 3: Report (`pipeline/03_report/report.py`)

**Responsabilidade:** Gerar visões analíticas a partir dos dados normalizados.

| Output | Descrição |
|---|---|
| `conversations_by_thread.jsonl` | Mensagens agrupadas por (session_id, thread_id) |
| `timeline.jsonl` | Todas as mensagens com timestamp, ordenadas cronologicamente |
| `tool_calls.jsonl` | Apenas mensagens com role='tool' |
| `topics_summary.txt` | Tabela legível por humanos com título, contagens e timestamps |

---

## Modelo de Dados

### ChatMessage (mensagem individual)

| Campo | Tipo | Descrição |
|---|---|---|
| thread_id | str | Chave primária da conversa |
| session_id | str | Identificador de sessão |
| role | str | `user` / `assistant` / `tool` / `system` |
| text | str | Conteúdo textual |
| timestamp | str? | ISO 8601 UTC |
| source | str | Tipo de fonte (9 valores — ver `SourceType` em `models.py`) |
| tool | str? | Nome da tool call |
| tool_input | str? | Argumentos JSON |
| files_changed | list[str] | Arquivos tocados |
| request_id | str? | ID da requisição |
| response_id | str? | ID da resposta |
| model_id | str? | Modelo utilizado |
| agent_id | str? | ID do agente |
| agent_name | str? | Nome do agente |
| workspace_hash | str? | Hash do workspace VS Code |
| raw_source_file | str? | Caminho do arquivo de origem |

### SessionSummary (metadados agregados)

| Campo | Tipo | Descrição |
|---|---|---|
| thread_id | str | Chave primária |
| session_id | str | Identificador de sessão |
| source | str | Tipo de fonte |
| title | str | Título da sessão |
| first_ts | str | ISO 8601 — primeira mensagem |
| last_ts | str | ISO 8601 — última mensagem |
| message_count | int | Total de mensagens |
| user_turns | int | Mensagens do usuário |
| assistant_turns | int | Respostas do assistente |
| tool_calls | int | Chamadas de tool |
| files_changed | list[str] | Arquivos tocados na sessão |
| workspace_hash | str? | Workspace associado |

---

## Viewer (`pipeline/viewer/app.py`)

**Framework:** Streamlit (reactive, sem servidor adicional)

**Abas:**

| Aba | Função |
|---|---|
| Conversa | Mensagens de uma sessão com export individual |
| Diário | Sessões agrupadas por data com busca |
| Timeline | Todas as mensagens de um dia específico |
| Workspaces | Workspaces com tags e sessões aninhadas |
| Tags | CRUD de tags de workspace |
| Exportar | Export bulk ZIP com filtros de data e sessão |

**Caching:**
- `@st.cache_data` em `load_data()`, `build_session_index()`, `build_workspace_index()`
- `_search_text` pré-computado por sessão — busca O(n_sessões), não O(n_sessões × n_mensagens)

**Persistência do viewer:**
- Leitura: `sessions.jsonl`, `summaries.jsonl` (imutáveis)
- Escrita: `tags.json` (único arquivo gravado pelo viewer)

---

## Fluxo de Dados Completo

```
VS Code AppData + ~/.codex/sessions/ + ~/.claude/projects/
          │ (read-only)
          ▼
  [01_ingest/ingest.py]
    • cria snapshot_YYYYMMDD_HHmmss/
    • extrai keys SQLite → *.vscdb.keys.jsonl
    • atualiza incremental_index.json
          │
          ▼
  [02_normalize/normalize.py]
    • lê ingest_manifest.jsonl
    • decide o que reprocessar (shards)
    • parsers.py → lista[ChatMessage] por fonte
    • aggregator.py → lista[SessionSummary]
    • grava sessions.jsonl + summaries.jsonl + shards/
          │
          ▼
  [03_report/report.py]
    • lê sessions.jsonl + summaries.jsonl
    • grava 4 arquivos de relatório
          │
          ▼
  [viewer/app.py] (Streamlit)
    • load_data() — carrega JSONL em memória
    • build_session_index() — dict thread_id → session
    • build_workspace_index() — dict hash → workspace
    • renderiza 6 abas
    • grava tags.json quando usuário edita tags
```

---

## Decisões Técnicas Identificadas

| Decisão | Justificativa |
|---|---|
| Streamlit em vez de Flask/Django | Zero config, UI reativa sem JS, ideal para ferramentas locais |
| Flat JSONL em vez de banco de dados | Simplicidade, portabilidade, recuperável re-executando o pipeline |
| Shards por hash SHA1 | Evita colisões; cache cross-platform independente de path |
| Incrementalidade por fingerprint (mtime_ns + size) | Mais barato que hash de conteúdo; suficiente para o caso de uso |
| Snapshots read-only | Preserva dados originais; nunca modifica arquivos do VS Code |
| 2 snapshots retidos | Permite comparação entre runs; limita uso de disco |
| `shard_schema_version = "3"` | Invalida cache automaticamente quando lógica dos parsers muda |

---

## Limitações Atuais

1. **Single-user, single-machine** — sem sincronização entre máquinas
2. **Windows-only** — caminhos `%APPDATA%` hard-coded em `config.py`
3. **`sessions.jsonl` cresce indefinidamente** — sem rotação ou arquivamento
4. **Sem testes automatizados** — refatorações são cegas
5. **`app.py` monolítico** (1.876 linhas) — mistura UI, lógica de dados, CSS, JS e exportação

---

## Arquitetura Alvo (próxima onda)

```
pipeline/viewer/
├── app.py              # main() + sidebar + dispatch (~200 linhas)
├── data.py             # load_data, build_session_index, build_workspace_index
├── export.py           # build_session_json, save_to_workspace, build_zip
├── styles.py           # _CSS_COMMON, _CSS_DARK, _CSS_LIGHT, _SCROLL_BTNS_JS
├── tab_conversa.py     # tab_conversa(), render_message()
├── tab_diario.py       # tab_diario()
├── tab_timeline.py     # tab_timeline()
├── tab_workspaces.py   # tab_workspaces()
├── tab_tags.py         # tab_tags()
├── tab_export.py       # tab_export()
└── i18n.py             # sem alteração
```

Ver [ROADMAP.md](ROADMAP.md) para o plano de evolução completo.
