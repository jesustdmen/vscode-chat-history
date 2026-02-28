﻿# VS Code Chat History

> Extraia, normalize e visualize o histórico completo das suas conversas com IAs no VS Code — localmente, sem enviar nada para a internet.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Windows](https://img.shields.io/badge/Plataforma-Windows-lightgrey)
![License](https://img.shields.io/badge/Licen%C3%A7a-MIT-green)
![Status](https://img.shields.io/badge/Status-MVP-orange)

🌐 **Idioma / Language:** Português (BR) | [English](README.en.md)

---

## ⚠️ Status: MVP — Uso Local

**Esta é uma ferramenta pessoal em estágio inicial (MVP).**  
Ela funciona bem para o uso pretendido, mas ainda não está pronta para produção.

- 🖥️ **Somente Windows** — caminhos de AppData e scripts PowerShell; macOS/Linux não testados
- 🔒 **Dados 100% locais** — nenhuma informação sai da sua máquina (ver [SECURITY.md](SECURITY.md))
- 🧪 **MVP** — pode ter comportamentos inesperados com formatos de sessão não mapeados

---

## O que é

O VS Code armazena o histórico de chat do Copilot (e outros assistentes de IA) em arquivos SQLite e JSONL dentro de `%APPDATA%\Code\User\`. Esta ferramenta:

1. **Copia** esses arquivos para um snapshot local isolado
2. **Normaliza** os dados (reconstruindo patches incrementais de sessões ativas)
3. **Expõe** um viewer Streamlit interativo para navegar, buscar e exportar conversas

```
AppData do VS Code
       │
       ▼
 01_ingest   → snapshot somente-leitura + limpeza automática (mantém 2)
       │
       ▼
 02_normalize → sessions.jsonl + summaries.jsonl
       │
       ▼
 03_report   → relatórios JSONL e texto
       │
       ▼
 viewer/app.py → http://localhost:8502
```

---

## Funcionalidades

- ✅ Lê 5 fontes distintas do VS Code: `chat_session_json`, `chat_session_jsonl`, `agent_sessions`, `chat_session_index`, `openai_chatgpt`
- ✅ Reconstrói sessões ativas (workspaces abertos) a partir de patches JSONL incrementais
- ✅ Viewer Streamlit com 3 abas: **Conversa**, **Diário de Atividades**, **Workspaces**
- ✅ Toggle tema claro/escuro
- ✅ Interface em 3 idiomas: 🇧🇷 Português, 🇺🇸 English, 🇪🇸 Español — seletor na sidebar
- ✅ Badges coloridos por fonte · stat bar · busca com índice pré-computado
- ✅ Exportação JSON estruturada (schema v1.0) por sessão
- ✅ Botão "📋 Copiar texto" e tool calls expansíveis por mensagem
- ✅ Botão 🔄 para rodar o pipeline diretamente do viewer
- ✅ Telemetria do Streamlit desativada (`gatherUsageStats = false`)

---

## Pré-requisitos

- Windows 10 ou 11
- Python 3.10 ou superior ([python.org](https://www.python.org/downloads/))
- VS Code com GitHub Copilot Chat instalado e com histórico gerado
- Git ([git-scm.com](https://git-scm.com/downloads))

---

## Instalação

```powershell
# 1. Clone o repositório
git clone https://github.com/SEU_USUARIO/vscode-chat-history.git
cd vscode-chat-history

# 2. Crie o ambiente virtual
python -m venv .venv
.venv\Scripts\pip install --upgrade pip

# 3. Instale as dependências
.venv\Scripts\pip install -r requirements.txt

# 4. Registre o pacote localmente (necessário uma única vez)
.venv\Scripts\pip install -e .
```

---

## Como usar

### Pipeline completo (recomendado)

```powershell
$env:PYTHONUTF8="1"; .venv\Scripts\python.exe pipeline/run_pipeline.py
```

### Opções individuais

```powershell
# Apenas re-normalizar (sem novo snapshot)
$env:PYTHONUTF8="1"; .venv\Scripts\python.exe pipeline/run_pipeline.py --skip-ingest

# Apenas relatórios
$env:PYTHONUTF8="1"; .venv\Scripts\python.exe pipeline/run_pipeline.py --only-report
```

### Viewer

```powershell
$env:PYTHONUTF8="1"; .venv\Scripts\streamlit.exe run pipeline/viewer/app.py
```

Acesse **http://localhost:8502** no navegador.

> **Por que `$env:PYTHONUTF8="1"`?**  
> Necessário no Windows para processar corretamente emojis e caracteres especiais (UTF-8) no terminal.

---

## Estrutura do projeto

```
vscode-chat-history/
├── .streamlit/
│   └── config.toml          # Telemetria desativada · porta 8502 · localhost
├── pipeline/
│   ├── run_pipeline.py      # Orquestrador: ingest → normalize → report
│   ├── 01_ingest/
│   │   └── ingest.py        # Cópia somente-leitura + limpeza automática de snapshots
│   ├── 02_normalize/
│   │   ├── normalize.py     # Orquestração (descobre fontes, emite sessions/summaries)
│   │   ├── parsers.py       # Parsers por fonte (openai, agent, index, json, jsonl)
│   │   ├── aggregator.py    # build_summaries(): ChatMessage → SessionSummary
│   │   └── patch.py         # Reconstrução de patches JSONL (kind 0/1/2)
│   ├── 03_report/
│   │   └── report.py        # Relatórios em JSONL e texto
│   ├── lib/
│   │   ├── config.py        # Caminhos e constantes (com validação de APPDATA)
│   │   ├── models.py        # Dataclasses: ChatMessage + SessionSummary
│   │   ├── db_reader.py     # Leitura somente-leitura de SQLite
│   │   └── patch.py         # Helpers de reconstrução de patches
│   ├── viewer/
│   │   └── app.py           # Interface Streamlit
│   └── output/              # ⚠️ Gerado — nunca versionar (ver .gitignore)
│       ├── raw/             # Snapshots brutos (apenas 2 mantidos)
│       ├── normalized/      # sessions.jsonl · summaries.jsonl
│       └── reports/         # conversations · topics · tool_calls · timeline
├── _dev/                    # Arquivos locais pessoais — nunca versionados
├── pyproject.toml
├── requirements.txt
├── CHANGELOG.md
├── SECURITY.md
└── README.md
```

---

## Limitações conhecidas

| Limitação | Detalhe |
|---|---|
| Somente Windows | Caminhos `%APPDATA%` e scripts `.ps1`; sem suporte testado para macOS/Linux |
| Somente GitHub Copilot Chat | Outros assistentes (Continue, Codeium, etc.) não são parseados |
| Sem autenticação | O viewer roda localmente sem senha — não expor em rede pública |
| Sessões muito antigas | Algumas sessões pré-2025 podem não ter formato mapeado |

---

## Roadmap

- [ ] **PostgreSQL via Docker** — migrar para banco relacional com upsert
- [ ] **`chatEditingSessions`** — histórico de edições de arquivo por sessão
- [ ] **Suporte a outros assistentes** — parsers para Blackbox AI, Continue e outros

---

## Contribuindo

Contribuições são bem-vindas! Veja [CONTRIBUTING.md](CONTRIBUTING.md) para o guia completo.

**Resumo rápido:**
1. Faça um fork
2. Crie uma branch: `git checkout -b feat/minha-feature`
3. Commit: `git commit -m "feat: descrição da mudança"`
4. Push: `git push origin feat/minha-feature`
5. Abra um Pull Request para a branch `main`

---

## Segurança e privacidade

Esta ferramenta lê arquivos pessoais do seu VS Code. Consulte [SECURITY.md](SECURITY.md) para entender o que é acessado, o que nunca vai ao Git e como auditar o código.

---

## Licença

Distribuído sob a [Licença MIT](LICENSE).

---

## Autor

**Jesus Teles** — Apenas um entusiasta que está impressionado com o vibecoding.

Desenvolvido com [GitHub Copilot](https://github.com/features/copilot) (Claude Sonnet 4.6).

Feedback, issues e ⭐ são bem-vindos!

