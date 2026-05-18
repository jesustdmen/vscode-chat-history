# Dívidas Técnicas — chatsvs-pipeline

> Registrado em: 2026-05-17 | Versão: MVP v0.1.0  
> Fonte: auditoria técnica completa do repositório

## Legenda de Prioridade

| Nível | Significado |
|---|---|
| **P0** | Corrigir imediatamente — trivial + impacto direto no uso |
| **P1** | Próxima onda de refatoração — alto impacto, planejável |
| **P2** | Quando houver tempo ou necessidade evidente |
| **P3** | Monitorar; corrigir apenas se virar problema real |

---

## Tabela de Dívidas

| # | Dívida | Categoria | Impacto | Risco de não corrigir | Esforço | Prioridade |
|---|---|---|---|---|---|---|
| 1 | `app.py` monolítico (1.876 linhas) — mistura UI, dados, CSS, JS e exportação | Arquitetural | Manutenção cara; bug exige varrer arquivo enorme | Alto — cada mudança tem risco de regressão invisível | Médio (4-8h para split) | **P1** |
| 2 | Zero testes automatizados | Testes | Refatorações cegas; regressões passam sem detecção | Alto — qualquer mudança em `parsers.py` pode corromper histórico silenciosamente | Alto (8-16h) | **P1** |
| 3 | Caminhos Windows hard-coded em `config.py` | Arquitetural | Impossível testar com dados sintéticos; lock de plataforma | Médio — testes de unidade inviáveis sem AppData real | Baixo (1-2h) | **P1** |
| 4 | `sessions.jsonl` cresce sem rotação ou arquivamento | Persistência | Pressão de memória e degradação de performance com uso contínuo | Alto — OOM eventual; viewer fica lento progressivamente | Médio (2-4h) | **P1** |
| 5 | Porta inconsistente: `launcher.py` usa 8501, `.streamlit/config.toml` define 8502 | DX | Viewer pode não abrir ao usar o tray launcher | Médio — silencioso; difícil de debugar | Mínimo (15 min) | **P0** |
| 6 | `report.py` não trata JSON inválido linha a linha em `sessions.jsonl` | Qualidade | Crash total do stage report se houver uma linha corrompida | Médio — invisível até acontecer | Mínimo (30 min) | **P0** |
| 7 | `_md_to_html()` no viewer sem cache | Performance | Re-renderização de Markdown a cada rerun do Streamlit | Baixo — degradação perceptível em sessões longas | Baixo (1h) | **P2** |
| 8 | CSS e JavaScript inline em `app.py` (~200 linhas de strings) | Qualidade | Dificulta ajustes visuais; mistura responsabilidades | Baixo — código mais difícil de ler | Baixo (1h) | **P2** |
| 9 | Sem CI/CD (GitHub Actions) | Governança | Qualidade verificada apenas manualmente | Baixo hoje — regressões chegam ao usuário sem filtro | Médio (2-4h) | **P2** |
| 10 | Sem versionamento de schema nos arquivos JSONL | Persistência | Mudança em `ChatMessage` invalida histórico sem migração automática | Médio — dívida que cresce com o tempo | Médio (2-4h) | **P3** |
| 11 | Sem backup automático da pasta `output/` | Infraestrutura | Perda de dados normalizados se `output/` for apagado | Baixo — recuperável re-executando o pipeline | Baixo (1h) | **P3** |
| 12 | `topics_summary.txt` gerado mas não exibido no viewer | Qualidade | Recurso sem uso visível; pode ser código morto ou não integrado | Mínimo | Mínimo | **P3** |
| 13 | Sem `__all__` nos módulos `pipeline/lib/` | Qualidade | Interface pública implícita; imports acidentais possíveis | Mínimo | Mínimo | **P3** |

---

## Detalhes por item P0 e P1

### P0 — Porta inconsistente (#5)

**Onde:** `launcher.py` (linha que define a URL do viewer) e `.streamlit/config.toml` (chave `[server] port`)

**Problema:** O launcher abre o browser na porta 8501, mas o Streamlit está configurado para servir na 8502. Se o usuário usar o tray launcher, o browser abre na porta errada.

**Solução:** Unificar em uma constante ou fazer o launcher ler o valor do `config.toml`.

---

### P0 — JSON inválido em report.py (#6)

**Onde:** `pipeline/03_report/report.py` — leitura linha a linha de `sessions.jsonl`

**Problema:** Não há `try/except` por linha. Uma linha corrompida causa crash do stage inteiro.

**Solução:**
```python
for line in f:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        # logar e continuar
        continue
```

---

### P1 — `app.py` monolítico (#1)

**Onde:** `pipeline/viewer/app.py` (1.876 linhas)

**Problema:** Um único arquivo contém lógica de dados, CSS, JavaScript, renderização de mensagens, lógica de export e 6 tabs diferentes. Qualquer bug exige navegar por quase 2000 linhas.

**Solução:** Split em módulos (ver `ARCHITECTURE.md` — seção "Arquitetura Alvo").

---

### P1 — Zero testes (#2)

**Onde:** Todo o projeto — nenhum arquivo `test_*.py` existe

**Problema:** `parsers.py` contém ~800 linhas de lógica crítica sem qualquer cobertura. Qualquer refatoração nesse arquivo é feita às cegas.

**Solução:** Configurar pytest, criar fixtures de dados sintéticos, cobrir ao menos 1 caso feliz + 1 caso de erro por parser.

---

### P1 — Caminhos hard-coded (#3)

**Onde:** `pipeline/lib/config.py`

**Problema:** `VSCODE_APPDATA`, `GLOBAL_STATE_DB`, `WORKSPACE_STORAGE_DIR` etc. são construídos diretamente a partir de `%APPDATA%`. Não há como injetar um caminho alternativo para testes.

**Solução:** Aceitar overrides via variáveis de ambiente com fallback para os valores atuais:
```python
VSCODE_APPDATA = Path(os.environ.get("CHATSVS_APPDATA", os.environ["APPDATA"]) + "/Code")
```

---

### P1 — Crescimento do JSONL (#4)

**Onde:** `pipeline/output/normalized/sessions.jsonl`

**Problema:** Cada run do pipeline pode adicionar novas mensagens. Não há mecanismo de rotação, arquivamento ou compactação. O arquivo já está em 202,5 MB e cresce continuamente.

**Solução candidata:** Arquivar sessões com `last_ts` mais antigo que N dias para `sessions_archive_YYYY.jsonl` e manter o arquivo ativo apenas com sessões recentes.

---

## Histórico de Correções

| Data | Item | Status |
|---|---|---|
| — | — | — |

> Atualizar esta tabela conforme as dívidas forem corrigidas.
