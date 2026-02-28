# Política de Segurança e Privacidade de Dados

## Princípio fundamental

**Esta ferramenta opera 100% localmente. Nenhum dado sai da sua máquina.**

Não há chamadas de rede de saída, nenhuma API externa, nenhuma telemetria de conteúdo.  
O histórico das suas conversas com IAs nunca é transmitido para qualquer servidor.

---

## O que a ferramenta acessa

| O que | Onde | Por quê |
|---|---|---|
| Arquivos SQLite (`.vscdb`) | `%APPDATA%\Code\User\workspaceStorage\` | Metadados de workspace do VS Code |
| Arquivos JSONL (`.jsonl`, `.json`) | `%APPDATA%\Code\User\workspaceStorage\` | Histórico de sessões de chat |

Todos os acessos são **somente-leitura**. A ferramenta nunca modifica os arquivos originais do VS Code.

---

## O que NUNCA deve ir ao Git / GitHub

Os arquivos abaixo contêm **histórico pessoal de conversas** e estão cobertos pelo `.gitignore`:

```
pipeline/output/          # sessions.jsonl, summaries.jsonl, reports, snapshots
_chatsession/             # JSONs exportados pelo viewer
_dev/                     # Arquivos pessoais e de contexto local
.streamlit/secrets.toml   # Credenciais do Streamlit (se usadas)
```

> **Antes de qualquer `git add .` ou `git push`, execute `git status` e confirme
> que nenhum desses caminhos aparece na listagem.**

---

## Telemetria do Streamlit

Por padrão, o Streamlit envia métricas anônimas de uso para servidores externos.  
Este projeto desativa isso explicitamente via `.streamlit/config.toml`:

```toml
[browser]
gatherUsageStats = false
```

O viewer também roda exclusivamente em `localhost` — não fica exposto na rede local.

---

## Como auditar o código

Para verificar que não há chamadas HTTP de saída no código-fonte:

```powershell
# Procura por imports de bibliotecas de rede
Get-ChildItem -Path "pipeline" -Include "*.py" -Recurse |
    Select-String -Pattern "import requests|urllib\.request|import httpx|import aiohttp|import socket"
```

Resultado esperado: **nenhuma ocorrência**.

O único uso de `urllib` no projeto é `urllib.parse.unquote` — decodificação de URLs locais de workspace, sem nenhuma chamada de rede.

---

## Reportar uma vulnerabilidade

Se encontrar algum problema de segurança ou privacidade, abra uma [Issue](../../issues) descrevendo:

1. O comportamento observado
2. Como reproduzir
3. Impacto potencial

Não inclua dados pessoais (conteúdo de conversas) ao reportar.
