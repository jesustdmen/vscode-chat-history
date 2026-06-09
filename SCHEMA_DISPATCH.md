# Reconhecimento de schemas por agente/fonte

Como o pipeline identifica cada formato de chat (Copilot, Codex, Claude Code, ChatGPT, etc.) e o resolve até o schema canônico consumido pelo `viewer`.

---

## 1) Visão geral

Não existe um único “arquivo de schemas”. O reconhecimento acontece em **três camadas encadeadas**:

```
[ingest] rotula a origem (campo "type")
   │
   └──► ingest_manifest.jsonl  (uma linha por arquivo bruto)
            │
            ▼
[normalize] lê o manifest e despacha para o parser certo
   │
   ├── dispatch por "type" de arquivo        ──► _parse_target()
   └── dispatch por "key" dentro de .vscdb   ──► _KEY_PARSERS
            │
            ▼
[parsers] cada parser emite ChatMessage no schema canônico
            │
            ▼
[output/normalized] sessions.jsonl + summaries.jsonl  (consumido pelo viewer)
```

O “discriminador de agente” no produto final é o campo `source` de cada `ChatMessage` / `SessionSummary`.

---

## 2) Camada 1 — Rotulagem na ingest

Arquivo: [pipeline/01_ingest/ingest.py](pipeline/01_ingest/ingest.py)

O ingest varre diretórios conhecidos do VS Code e dos CLIs, copia os artefatos para `output/raw/snapshot_<timestamp>/` e grava `ingest_manifest.jsonl`. Cada entrada do manifest carrega um campo `type` que **classifica fisicamente** o arquivo pela origem.

| Bloco no `ingest.py` | Diretório de origem                                          | `type` gravado no manifest |
| -------------------- | ------------------------------------------------------------ | -------------------------- |
| `[1/6]`              | `globalStorage/state.vscdb`                                  | `vscdb`                    |
| `[2/6]`              | `workspaceStorage/<hash>/state.vscdb`                        | `vscdb`                    |
| `[3/6]`              | `workspaceStorage/<hash>/*.jsonl` (legado Copilot)           | `jsonl`                    |
| `[4/6]`              | `workspaceStorage/<hash>/chatSessions/<uuid>.json`/`.jsonl`  | `chat_session_json` / `chat_session_jsonl` |
| `[5/6]`              | `workspaceStorage/<hash>/chatEditingSessions/<uuid>/state.json` | `chat_editing_state`    |
| `[6/6]`              | `globalStorage/emptyWindowChatSessions/*.json`/`.jsonl`      | `chat_session_json` / `chat_session_jsonl` |
| `[6/6]` (Codex)      | `~/.codex/sessions/**/*.jsonl` + `archived_sessions/`        | `codex_session`            |
| `[7/7]` (Claude)     | `~/.claude/projects/<slug>/*.jsonl`                          | `claude_code_session`      |

Para cada `.vscdb`, o ingest extrai as chaves de interesse via `KEY_REGEX` ([pipeline/lib/config.py](pipeline/lib/config.py)) e grava um **sidecar** `<nome>.vscdb.keys.jsonl` ao lado do binário. Esse sidecar contém uma linha por chave (`{"key": ..., "value": ...}`) e é o que o normalize realmente lê — o `.vscdb` original nunca é reaberto.

---

## 3) Camada 2 — Dispatch por tipo de arquivo

Arquivo: [pipeline/02_normalize/normalize.py](pipeline/02_normalize/normalize.py)

### 3.1 Coleta dos alvos

`_collect_normalize_targets` em [pipeline/02_normalize/normalize.py](pipeline/02_normalize/normalize.py) lê o manifest e mantém apenas os `type` aceitos:

```python
allowed_types = {
    "vscdb",
    "jsonl",
    "chat_session_json",
    "chat_session_jsonl",
    "chat_editing_state",
    "codex_session",
    "claude_code_session",
}
```

Para `vscdb`, troca o caminho pelo sidecar `.vscdb.keys.jsonl` e marca `parse_type = "keys_sidecar"`. Para os demais, `parse_type == file_type`.

### 3.2 Resolução parser ↔ tipo

`_parse_target` em [pipeline/02_normalize/normalize.py](pipeline/02_normalize/normalize.py) é a tabela de despacho central:

| `parse_type`           | Parser invocado                                                                                   |
| ---------------------- | ------------------------------------------------------------------------------------------------- |
| `keys_sidecar`         | `parse_keys_sidecar` (dispatch interno por chave)                                                 |
| `jsonl`                | `parse_copilot_jsonl_file`                                                                        |
| `chat_session_json`    | `parse_chat_session_json`                                                                         |
| `chat_session_jsonl`   | `parse_chat_session_jsonl`                                                                        |
| `chat_editing_state`   | `parse_chat_editing_state`                                                                        |
| `codex_session`        | `parse_codex_session_jsonl`                                                                       |
| `claude_code_session`  | `parse_claude_code_session`                                                                       |

Tipos novos (ex.: outra extensão de agente) exigem **três alterações coordenadas**: rotular no ingest, incluir em `allowed_types`, adicionar `if parse_type == ...` em `_parse_target`.

---

## 4) Camada 3 — Dispatch por chave dentro de `.vscdb`

Arquivo: [pipeline/02_normalize/parsers.py](pipeline/02_normalize/parsers.py)

Cada linha do sidecar `.keys.jsonl` é roteada pelo dicionário `_KEY_PARSERS` em [pipeline/02_normalize/parsers.py](pipeline/02_normalize/parsers.py):

```python
_KEY_PARSERS = {
    "openai.chatgpt":              parse_openai_chatgpt,
    "agentSessions.state.cache":   parse_agent_sessions_state,
    "chat.ChatSessionStore.index": parse_chat_session_index,
}
```

`parse_keys_sidecar` percorre as linhas e chama o parser correspondente. Chaves desconhecidas são silenciosamente ignoradas.

Para adicionar uma nova chave SQLite reconhecida: incluir o nome em `KEY_REGEX` ([pipeline/lib/config.py](pipeline/lib/config.py)) **e** registrar o parser em `_KEY_PARSERS`.

---

## 5) Schema canônico final

Arquivo: [pipeline/lib/models.py](pipeline/lib/models.py)

Todos os parsers convergem para dois dataclasses:

- `ChatMessage` — unidade mínima de troca, com `source`, `session_id`, `thread_id`, `role`, `text`, `timestamp`, `workspace_hash`, `tool/tool_input`, `files_changed`, `model_id`, `agent_id`, `mode_name`, `raw_source_file`.
- `SessionSummary` — agregação por sessão produzida por [`build_summaries`](pipeline/02_normalize/aggregator.py).

O campo `source` é o **discriminador de agente** no consumidor final e usa a lista fechada `SourceType`:

```
chat_session_json | chat_session_jsonl | chat_editing_state
chat_session_index | openai_chatgpt | agent_sessions
copilot_jsonl | copilot_jsonl_raw | chat_session
codex_session | claude_code_session
```

A saída fica em:

- `output/normalized/sessions.jsonl` — uma linha por `ChatMessage` (shardeada em `shards/messages/`)
- `output/normalized/summaries.jsonl` — uma linha por `SessionSummary` (shardeada em `shards/summaries/`)
- títulos são derivados de mensagens `system` com `_type = "thread_title"` durante a agregação das sessões.

---

## 6) Pontos de extensão (resumo prático)

Para suportar **um novo agente / formato**:

1. **Ingest**: adicionar bloco que copie os arquivos e grave `type: "<novo_tipo>"` no manifest ([pipeline/01_ingest/ingest.py](pipeline/01_ingest/ingest.py)).
2. **Normalize**: incluir `"<novo_tipo>"` em `allowed_types` e ramo correspondente em `_parse_target` ([pipeline/02_normalize/normalize.py](pipeline/02_normalize/normalize.py)).
3. **Parser**: implementar `parse_<novo_tipo>(path, ws_hash) -> list[ChatMessage]` em [pipeline/02_normalize/parsers.py](pipeline/02_normalize/parsers.py) emitindo `source="<novo_tipo>"`.
4. **Models**: estender `SourceType` em [pipeline/lib/models.py](pipeline/lib/models.py).
5. **Títulos** (opcional): emitir uma mensagem `system` com `_type = "thread_title"` se a fonte trouxer títulos.

Para **uma nova chave dentro de `state.vscdb`**:

1. Adicioná-la a `KEY_REGEX` em [pipeline/lib/config.py](pipeline/lib/config.py) (assim o ingest a extrai no sidecar).
2. Registrar `"<chave>": parse_<func>` em `_KEY_PARSERS` em [pipeline/02_normalize/parsers.py](pipeline/02_normalize/parsers.py).
