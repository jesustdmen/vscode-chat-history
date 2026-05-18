# Avaliação: PostgreSQL — chatsvs-pipeline

> Criado em: 2026-05-17 | Contexto: MVP v0.1.0, single-user, local, Windows-only  
> Revisar quando: `sessions.jsonl` ≥ 500 MB, ou surgir necessidade multi-usuário

---

## Diagnóstico de Persistência Atual

| Aspecto | Estado atual |
|---|---|
| Tipo de armazenamento | Flat files JSONL (append-only, regenerados pelo pipeline) |
| Arquivo principal | `pipeline/output/normalized/sessions.jsonl` — 202,5 MB e crescendo |
| Metadados de sessões | `pipeline/output/normalized/summaries.jsonl` — 925 KB, regenerado a cada run |
| Tags de usuário | `pipeline/output/normalized/tags.json` — único arquivo gravado pelo viewer |
| Estado incremental | `pipeline/output/state/incremental_index.json` — fingerprints para cache |
| Cache de normalização | `pipeline/output/normalized/shards/` — por arquivo-fonte |
| Concorrência | Single-user; sem acesso simultâneo |
| Backup | Nenhum mecanismo automático |
| Tipo de consulta | Scan linear O(n) — tudo carregado em memória no viewer |

---

## Decisão Recomendada

**PostgreSQL: NÃO recomendado agora.**

**Próximo passo de persistência (quando necessário): SQLite próprio.**

---

## Justificativa

### Por que PostgreSQL não é adequado agora

1. **Sem servidor:** A aplicação é 100% local, sem backend. PostgreSQL exige um servidor sempre rodando — overhead de configuração e manutenção para uma ferramenta pessoal.

2. **Overkill para a escala atual:** 202 MB de dados com 1 usuário não justifica um RDBMS com servidor. O SQLite resolve o mesmo problema sem dependência externa.

3. **Pré-requisitos não atendidos:** O projeto ainda não tem testes automatizados. Adicionar um banco externo antes de ter testes é empilhar complexidade sobre fragilidade.

4. **O problema real é diferente:** O gargalo atual é o carregamento total em memória e o crescimento ilimitado do JSONL — ambos resolvíveis com lazy loading ou SQLite, sem a complexidade de PG.

5. **Custo de introdução:** PostgreSQL exigiria instalar servidor PG, driver psycopg2, schema migrations (Alembic), connection pooling, estratégia de backup e documentação de setup — tudo isso para resolver um problema que SQLite resolve com ~50 linhas de código.

### Por que SQLite é o próximo passo natural

- Disponível na stdlib Python — zero dependência nova
- Arquivo único portável — backup é copiar um arquivo
- WAL mode para writes seguros do viewer sem locks manuais
- SQL completo para queries complexas e filtros
- Índices em `timestamp`, `thread_id`, `workspace_hash`
- Sem servidor, sem configuração adicional
- Já está em uso no projeto (para leitura do VS Code)

### Quando PostgreSQL faria sentido

- Evolução para API REST servindo múltiplos clientes simultaneamente
- Sincronização do histórico entre máquinas (backup remoto)
- Uso compartilhado entre membros de equipe
- Volume de dados > 10 GB (onde SQLite começa a ter limitações)

---

## Entidades Candidatas a Tabelas

| Entidade | Fonte atual | Tabela proposta |
|---|---|---|
| Mensagem de chat | `sessions.jsonl` | `messages` |
| Metadados de sessão | `summaries.jsonl` | `sessions` |
| Tag | `tags.json` | `tags` |
| Vínculo workspace ↔ tag | `tags.json` | `workspace_tags` |
| Fingerprint incremental | `incremental_index.json` | `file_fingerprints` (opcional) |

---

## Schema SQLite Proposto

```sql
CREATE TABLE messages (
    id             INTEGER PRIMARY KEY,
    thread_id      TEXT NOT NULL,
    session_id     TEXT,
    source         TEXT NOT NULL,
    role           TEXT NOT NULL CHECK(role IN ('user','assistant','tool','system')),
    text           TEXT,
    timestamp      TEXT,           -- ISO 8601 UTC
    tool           TEXT,
    tool_input     TEXT,           -- JSON string
    request_id     TEXT,
    response_id    TEXT,
    model_id       TEXT,
    agent_id       TEXT,
    agent_name     TEXT,
    workspace_hash TEXT,
    files_changed  TEXT            -- JSON array
);

CREATE INDEX idx_messages_thread_id  ON messages(thread_id);
CREATE INDEX idx_messages_timestamp  ON messages(timestamp);
CREATE INDEX idx_messages_workspace  ON messages(workspace_hash);

CREATE TABLE sessions (
    thread_id       TEXT PRIMARY KEY,
    session_id      TEXT,
    source          TEXT,
    title           TEXT,
    first_ts        TEXT,
    last_ts         TEXT,
    message_count   INTEGER DEFAULT 0,
    user_turns      INTEGER DEFAULT 0,
    assistant_turns INTEGER DEFAULT 0,
    tool_calls      INTEGER DEFAULT 0,
    workspace_hash  TEXT
);

CREATE INDEX idx_sessions_last_ts   ON sessions(last_ts);
CREATE INDEX idx_sessions_workspace ON sessions(workspace_hash);

CREATE TABLE tags (
    tag_id INTEGER PRIMARY KEY,
    name   TEXT UNIQUE NOT NULL
);

CREATE TABLE workspace_tags (
    workspace_hash TEXT NOT NULL,
    tag_id         INTEGER NOT NULL REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (workspace_hash, tag_id)
);
```

> Este schema é conceitual. Não criar scripts de migração sem autorização explícita.

---

## Pré-requisitos para qualquer migração

1. **Testes de regressão nos parsers** — garantir que dados migrados são idênticos aos JSONL
2. **Definir a fonte de verdade** — durante a transição, manter JSONL como backup
3. **Script de migração testado** — com verificação de contagens antes/depois
4. **Adaptar `data.py`** — substituir `load_data()` por queries SQL paginadas
5. **Estratégia de rollback** — JSONL sempre recuperável re-executando o pipeline

---

## Riscos de Migração

| Risco | Probabilidade | Mitigação |
|---|---|---|
| JSONL e BD ficarem dessincronizados durante transição | Média | Manter JSONL como fonte de verdade; BD é secundário inicialmente |
| Performance do BD pior que JSONL para scan total | Baixa | Criar índices adequados; medir antes de comparar |
| Schema de `ChatMessage` mudar após migração | Média | Versionamento de schema com migrations antes de migrar |
| Perda de dados durante migração | Baixa | Backup obrigatório antes de executar o script |

---

## Próximos Passos Recomendados

| Gatilho | Ação |
|---|---|
| **Agora** | Nenhuma mudança de persistência necessária |
| `sessions.jsonl` ≥ 300 MB | Avaliar lazy loading no viewer como primeiro passo |
| `sessions.jsonl` ≥ 500 MB ou queries complexas necessárias | Iniciar Onda 5 — migração para SQLite |
| Necessidade multi-usuário ou sincronização remota | Reavaliar PostgreSQL com arquitetura de API REST |

---

## Conclusão

O projeto está no estágio correto com JSONL. A transição para banco de dados deve ser uma decisão baseada em necessidade demonstrada — não em antecipação. **SQLite é o caminho natural quando chegar a hora. PostgreSQL é para quando SQLite não for mais suficiente.**

Ver [ROADMAP.md](ROADMAP.md) — Onda 5 para o plano detalhado de migração.
