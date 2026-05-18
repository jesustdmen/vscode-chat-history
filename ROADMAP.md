# Roadmap — chatsvs-pipeline

> Criado em: 2026-05-17 | Baseado em auditoria técnica completa  
> Ver [TECHNICAL_DEBT.md](TECHNICAL_DEBT.md) para a lista detalhada de dívidas.

## Princípios

1. Não quebrar o que funciona — testar antes de refatorar
2. Refatorar antes de otimizar — não otimizar o que não está medido
3. PostgreSQL é decisão futura condicional, não obrigação
4. Cada onda deve entregar valor independentemente das seguintes

---

## Onda 1 — Higiene imediata

**Objetivo:** Corrigir problemas triviais sem risco de regressão.  
**Estimativa:** 2-4 horas  
**Gatilho:** Iniciar agora (independe de qualquer pré-requisito)

- [ ] Corrigir porta inconsistente entre `launcher.py` e `.streamlit/config.toml`
- [ ] Adicionar `try/except` por linha em `report.py` para JSON inválido
- [ ] Adicionar `@st.cache_data` em `_md_to_html()` no viewer
- [ ] Extrair CSS/JS inline de `app.py` para `styles.py`
- [ ] Documentar variáveis de ambiente no README

**Critério de sucesso:** Viewer abre corretamente pelo tray; pipeline não crasha em dados inválidos; nenhuma funcionalidade alterada.

---

## Onda 2 — Decomposição do viewer

**Objetivo:** `app.py` abaixo de 250 linhas, comportamento idêntico ao atual.  
**Estimativa:** 4-8 horas  
**Gatilho:** Após Onda 1 concluída

**Estrutura alvo:**
```
pipeline/viewer/
├── app.py              (~200 linhas — main, sidebar, dispatch)
├── data.py             (load_data, build_session_index, build_workspace_index)
├── export.py           (build_session_json, save_to_workspace, build_zip)
├── styles.py           (_CSS_COMMON, _CSS_DARK, _CSS_LIGHT, _SCROLL_BTNS_JS)
├── tab_conversa.py     (tab_conversa, render_message)
├── tab_diario.py       (tab_diario)
├── tab_timeline.py     (tab_timeline)
├── tab_workspaces.py   (tab_workspaces)
├── tab_tags.py         (tab_tags)
├── tab_export.py       (tab_export)
└── i18n.py             (sem alteração)
```

**Critério de sucesso:** Todos os 6 tabs funcionam identicamente; `app.py` < 250 linhas; nenhuma feature perdida.

---

## Onda 3 — Testes mínimos

**Objetivo:** Cobertura de 30%+ nos parsers; CI automático em push.  
**Estimativa:** 8-16 horas  
**Gatilho:** Após Onda 2 (decomposição facilita a testabilidade)

- [ ] Configurar `pytest` como framework de teste
- [ ] Extrair caminhos hard-coded de `config.py` para parâmetros injetáveis (habilita fixtures)
- [ ] Testes unitários de `parsers.py`: pelo menos 1 caso feliz + 1 caso de erro por parser
- [ ] Testes de integração do pipeline completo com dados sintéticos
- [ ] Testes para utilitários: `_ms_to_iso()`, `_normalize_windows_path()`, `_stable_id()`
- [ ] GitHub Actions: executar `pytest` em push para `main` e `dev`

**Critério de sucesso:** `pytest` verde em CI; parsers cobertos nos casos principais; refatorações futuras são seguras.

---

## Onda 4 — Performance e escalabilidade

**Objetivo:** Viewer carrega em < 3s; `sessions.jsonl` tem tamanho controlado.  
**Estimativa:** 8-16 horas  
**Gatilho:** Quando `sessions.jsonl` ultrapassar 300 MB OU carregamento inicial ultrapassar 5 segundos

- [ ] Lazy loading: carregar apenas `summaries.jsonl` na inicialização; mensagens por sessão on-demand
- [ ] Paginação no viewer para sessões com muitas mensagens (janela configurável: 100/200/500/todas)
- [ ] Rotação de `sessions.jsonl`: arquivar sessões com `last_ts` > 90 dias para `sessions_archive_YYYY.jsonl`
- [ ] Benchmark antes e depois: medir tempo de carga e uso de memória com os dados atuais

**Critério de sucesso:** Carga inicial < 3 segundos; `sessions.jsonl` tem tamanho controlado com rotação ativa.

---

## Onda 5 — Persistência robusta (condicional)

**Objetivo:** Migrar para SQLite se os dados ultrapassarem limites aceitáveis.  
**Estimativa:** 16-24 horas  
**Gatilho:** `sessions.jsonl` ≥ 500 MB OU necessidade explícita de queries complexas

**Schema SQLite proposto:**
```sql
messages       (id, thread_id, session_id, role, text, timestamp, source, tool, ...)
sessions       (thread_id, title, first_ts, last_ts, user_turns, assistant_turns, ...)
tags           (tag_id, name)
workspace_tags (workspace_hash, tag_id)
```

- [ ] Criar schema com índices em `timestamp`, `thread_id`, `workspace_hash`
- [ ] Script de migração `sessions.jsonl` + `summaries.jsonl` → SQLite
- [ ] Adaptar `data.py` (viewer) para usar SQLite com queries paginadas
- [ ] Adaptar `normalize.py` para gravar no BD (em paralelo com JSONL durante transição)
- [ ] Testes de integridade pós-migração: contagem de mensagens, verificação de thread_ids

**Nota sobre PostgreSQL:** Avaliar apenas se o projeto evoluir para multi-usuário ou sincronização remota. Ver [POSTGRESQL_ASSESSMENT.md](POSTGRESQL_ASSESSMENT.md).

**Critério de sucesso:** Viewer usa SQLite; queries com filtros complexos funcionam; `sessions.jsonl` mantido como backup.

---

## Onda 6 — Governança e qualidade contínua

**Objetivo:** Projeto sustentável a longo prazo.  
**Estimativa:** 4-8 horas  
**Gatilho:** Quando houver pelo menos 30% de cobertura de testes (Onda 3 concluída)

- [ ] Logging estruturado: substituir `print()` por `logging.getLogger(__name__)`
- [ ] Tratamento de erros consistente no pipeline (wrapper de exceção por stage)
- [ ] Pre-commit hooks: `ruff` (lint) + `black` (format)
- [ ] Estratégia de backup de `output/` (script de cópia ou sincronização)
- [ ] CHANGELOG automatizado via conventional commits

**Critério de sucesso:** Pipeline tem logging adequado; pre-commit previne código não formatado; backup configurado.

---

---

## Track UX/UI — Viewer

> Track independente das Ondas técnicas. Não altera pipeline nem modelos de dados.  
> Referência: [`_diagnóstico/AUDITORIA_UXUI.md`](_diagnóstico/AUDITORIA_UXUI.md)

### Fase 1 — Quick Wins ✅ concluída em 2026-05-18

- [x] Chips do multiselect: vermelho → índigo (`_CSS_DARK`)
- [x] Tab ativo: texto branco + `font-weight: 600` (`_CSS_DARK`)
- [x] Balões de mensagem: `border-radius` 14px → 16px (`_CSS_COMMON`)
- [x] Sidebar: 3 seções com captions (CONFIGURAÇÃO / FILTROS / AÇÕES)
- [x] Multiselect de fonte: `format_func` com nomes curtos amigáveis
- [x] Tags: card view com chip índigo + contagem de uso

### Fase 2 — Design System

**Objetivo:** Centralizar variáveis de cor, tipografia e espaçamento em `:root {}`.  
**Estimativa:** 2-4h

- [ ] Bloco `:root {}` com CSS variables (paleta, tipografia, espaçamentos)
- [ ] Migrar `_CSS_DARK` e `_CSS_COMMON` para usar as variables
- [ ] Padronizar card pattern (base / hover / selecionado)
- [ ] Padronizar tipografia (escala de 6 tamanhos)
- [ ] Padronizar botões (primary / secondary / danger / ghost)

### Fase 3 — Melhorias por Tela

**Objetivo:** Aplicar design system em cada tab.  
**Estimativa:** 4-8h

- [ ] Tags: layout de duas colunas (quando > 3 tags)
- [ ] Exportar: layout em duas colunas + resumo de seleção
- [ ] Workspaces: zebra stripe no modo lista
- [ ] Timeline: botões de navegação e hora mais legíveis
- [ ] Diário: header de data com borda esquerda índigo

### Fase 4 — Mudanças Estruturais (validar antes)

- [ ] Avaliar migração de radio tabs para `st.tabs` nativo (alto risco)
- [ ] Tags com cor associável (requer migração de `tags.json`)
- [ ] Responsividade em telas estreitas (≤ 1366px)

---

## Estado atual

| Onda / Track | Status |
|---|---|
| Onda 1 — Higiene | Pendente |
| Onda 2 — Decomposição do viewer | Pendente |
| Onda 3 — Testes | Pendente |
| Onda 4 — Performance | Pendente (gatilho não atingido) |
| Onda 5 — SQLite | Pendente (gatilho não atingido) |
| Onda 6 — Governança | Pendente |
| **UX/UI Fase 1** | **✅ Concluída — 2026-05-18** |
| UX/UI Fase 2 | Próxima |
| UX/UI Fase 3 | Pendente |
| UX/UI Fase 4 | Pendente (validar antes) |

> Atualizar esta tabela conforme as ondas avançarem.
