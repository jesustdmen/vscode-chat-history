# Como Contribuir

Obrigado por considerar contribuir com o **VS Code Chat History**!

---

## Principles

Esta ferramenta lida com dados **pessoais e sensíveis** (histórico de conversas com IA do seu VS Code).  
Toda contribuição deve respeitar os seguintes princípios:

1. **Zero dados para a internet** — nenhuma modificação deve introduzir chamadas de rede (requests, httpx, urllib.request, etc.)
2. **Windows-first** — o foco atual é Windows; contribuições para macOS/Linux são bem-vindas mas não são requisito
3. **Sem dependências desnecessárias** — antes de adicionar uma biblioteca, questione se é realmente necessária

---

## Fluxo de trabalho

### 1. Fork e clone

```bash
git clone https://github.com/SEU_USUARIO/vscode-chat-history.git
cd vscode-chat-history
```

### 2. Crie uma branch a partir de `dev`

```bash
git checkout dev
git checkout -b feat/nome-da-feature
# ou
git checkout -b fix/nome-do-bug
```

**Nunca** abra Pull Request direto para `main`. O fluxo é: `feat/*` → `dev` → `main`.

### 3. Configure o ambiente

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install -e .
```

### 4. Faça as alterações

- Siga o padrão de código existente (snake_case, docstrings, `logging` em vez de `print`)
- Se adicionar um parser novo, crie-o em `pipeline/02_normalize/parsers.py`
- Se alterar o modelo de dados, atualize `pipeline/lib/models.py`
- Teste localmente com `$env:PYTHONUTF8="1"; .venv\Scripts\python.exe pipeline/run_pipeline.py`

### 5. Commit

Use [Conventional Commits](https://www.conventionalcommits.org/pt-br/v1.0.0/):

```
feat: adiciona suporte a sessões do Continue AI
fix: corrige erro de timezone em sessões após meia-noite
docs: atualiza README com novo pré-requisito
refactor: extrai lógica de patch para módulo separado
```

### 6. Push e Pull Request

```bash
git push origin feat/nome-da-feature
```

Abra um Pull Request para a branch **`dev`** (não `main`).

No PR, descreva:
- O que foi alterado e por quê
- Como testar localmente
- Se há impacto em dados existentes (`sessions.jsonl`, `summaries.jsonl`)

---

## O que contribuir

### Bem-vindo

- [ ] Suporte a outros assistentes de IA no VS Code (Continue, Codeium, Blackbox AI)
- [ ] Suporte a `chatEditingSessions` (histórico de edições de arquivo)
- [ ] Testes automatizados (pytest) para os parsers
- [ ] Migração para PostgreSQL via Docker
- [ ] Documentação de novos formatos de sessão descobertos

### Não aceito (por segurança)

- ❌ Qualquer chamada de rede (upload, telemetria, sync com cloud)
- ❌ Autenticação via serviço externo
- ❌ Acesso a arquivos fora de `%APPDATA%\Code\User\` e do diretório do projeto

---

## Dúvidas

Abra uma [Issue](https://github.com/SEU_USUARIO/vscode-chat-history/issues) com a tag `question`.

---

## Código de conduta

Respeito mútuo, feedback construtivo, sem discriminação. É isso.
