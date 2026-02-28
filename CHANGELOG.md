# Changelog

Todas as mudanças relevantes do projeto são documentadas neste arquivo.  
Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

---

## [0.1.1] — 2026-02-28

### Adicionado
- Viewer: suporte a 3 idiomas (🇧🇷 PT-BR / 🇺🇸 EN-US / 🇪🇸 ES-ES) com seletor na sidebar
- `pipeline/viewer/i18n.py`: dicionário central de traduções com ~40 chaves por idioma
- Helper `_t(key)` que lê `st.session_state["lang"]` dinamicamente
- Helper `_display_title()` para traduzir sentinel `__NO_TITLE__` fora do cache
- Dias da semana no Diário de Atividades traduzidos dinamicamente

### Corrigido
- Import de `i18n.py` corrigido para path relativo (`from i18n import ...`) compatível com `streamlit run`
- Adicionados `pipeline/__init__.py` e `pipeline/viewer/__init__.py` ausentes

---

## [0.1.0] — 2026-02-28

### Adicionado
- Packaging com `pyproject.toml` + `pip install -e .` (elimina sys.path hacks)
- `02_normalize/` dividido em 4 módulos: `parsers.py`, `aggregator.py`, `patch.py`, `normalize.py`
- `lib/models.py` com tipos `Literal` para `role` e `source`
- `lib/db_reader.py` com `logging` estruturado
- Limpeza automática de snapshots (mantém 2 mais recentes)
- Viewer: toggle tema claro/escuro (☀️/🌙) com cobertura total do chrome do Streamlit
- Viewer: badges coloridos por fonte de dados
- Viewer: stat bar colorida (perguntas / respostas / tool calls / data)
- Viewer: botão "📋 Copiar texto" por mensagem
- Viewer: tool calls expansíveis com argumentos JSON
- Viewer: export JSON com campo `role` + `tool_name` em `assistant_responses`
- Viewer: `exchange_id` determinístico via uuid5
- Viewer: busca O(n_sessões) com índice pré-computado `_search_text`
- Viewer: aba Exportar removida (funcionalidade integrada à aba Conversa)
- Viewer: porta padrão alterada para `8502`
- Fix XSS: `html.escape()` em todos os dados externos
- `.gitignore`, `SECURITY.md`, `.streamlit/config.toml` adicionados

### Corrigido
- `_extend_nested` / `_set_nested`: navegação de caminhos mistos dict/list com índices inteiros (ex: `requests[N].response`)

---

## [Sem versão] — 2026-02-27

### Adicionado
- Suporte a `questionCarousel` (Gemini 3.1)

### Corrigido
- Respostas ausentes em sessões agent mode (`gpt-5.2-codex`): fallback `kind=thinking+generatedTitle`
- Re-pipeline: 3.988 msgs, 1.708 respostas assistant, sessão Wave 26/02 recuperada (28 user + 26 asst turns)

---

## [Sem versão] — 2026-02-26

### Corrigido
- Timezone: todos os timestamps e agrupamentos de data convertidos de UTC para BRT
- `ts_to_label()`, `ts_to_date_brt()` centralizados com `_BRT` e `_to_utc_aware()`

---

## [Sem versão] — 2026-02-25

### Adicionado
- Date picker com calendário nativo e formato automático via locale do SO
- Botão ↗ no Diário navega diretamente para aba Conversa
- Botão 🔄 Executar pipeline na sidebar com log em tempo real
- Exportação JSON schema v1.0 com `exchanges[]`
- Salvamento de export direto em `_chatsession/` do workspace
- Ocultar sessões vazias (sidebar, checkbox ativo por padrão)
- Nome de arquivo de export sem truncamento (máximo 120 caracteres)

### Corrigido
- `workspace_hash` propagado corretamente via `_parse_chat_session_obj(ws_hash=)`
- Snapshot atualizado: 3.612 msgs, 458 sessões, 54 workspaces

---

## [Sem versão] — 2026-02-22

### Adicionado
- Pipeline completo: ingest → normalize → report → viewer
- Suporte a patches `.jsonl` (kind 0/1/2) via `lib/patch.py`
- Aba Workspaces com hash → pasta resolvido via `workspace.json`
- Filtro de busca no Diário por título/thread ID

### Corrigido
- `assistant_turns=0` em todas as sessões: `_extract_response_text()` aceita `not kind`
