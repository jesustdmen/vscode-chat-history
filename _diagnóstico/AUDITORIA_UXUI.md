# Auditoria UX/UI — Chat Viewer (18/05/2026)

**Stack:** Streamlit (Python) · CSS inline (~800 linhas) · i18n pt-BR/en/es
**Arquivo principal:** `pipeline/viewer/app.py` · **Traduções:** `pipeline/viewer/i18n.py`

---

## 1. Resumo Executivo

A interface está funcional e organizada logicamente, mas apresenta quatro problemas centrais que reduzem a qualidade percebida: (1) sidebar sem agrupamento visual, (2) chips de filtro vermelhos que parecem erros, (3) telas com espaço vazio excessivo (Tags, Exportar), e (4) falta de um sistema de design consistente — cores, espaçamentos e componentes foram crescendo por adição sem padrão unificado. O plano propõe correções em três ondas: mudanças rápidas de alto impacto, melhorias estruturais e mudanças sensíveis que precisam de validação.

---

## 2. Diagnóstico Visual Geral

**Framework:** Streamlit impõe limitações de layout (sidebar fixa, widgets nativos, radio buttons como tabs). O CSS customizado já supera muitas limitações nativas, mas há inconsistências acumuladas.

**Tema escuro:** funciona bem como base, mas a paleta de destaques é inconsistente — vermelho para filtros ativos, roxo para tags, azul para usuário, laranja para ações, sem semântica clara.

**Densidade:** a sidebar é densa sem separadores. O conteúdo principal usa bem o espaço em Conversa e Diário, mas desperdiça espaço em Tags e Exportar.

**Identidade visual:** a aplicação não tem uma cor primária dominante clara — oscila entre azul, índigo e roxo em diferentes componentes.

---

## 3. Pontos Fortes da Interface Atual

- Tema escuro bem executado como base
- Balões de mensagem com alinhamento left/right funcionam bem visualmente
- Stat bar com ícones coloridos por categoria é eficaz e informativa
- Source badges com cores distintas por tipo de fonte ajudam na diferenciação
- Workspace cards com hover effect mostram boa direção visual
- i18n completo (pt-BR, en, es) é um diferencial de qualidade
- Scroll buttons customizados (cima/baixo) são uma adição útil
- Caching com `@st.cache_data` garante performance mesmo com 500+ sessões
- Expand/collapse de tool calls reduz ruído sem perder informação

---

## 4. Principais Problemas UX/UI

### P1 — Chips de filtro vermelhos parecem erro (ALTA prioridade)

Os chips `agent_sessi...`, `chat_sessi...` na sidebar usam fundo vermelho sólido. Em qualquer sistema de design, vermelho = erro/alerta. Filtros ativos devem usar azul/índigo/roxo primário ou cinza claro com borda destacada.

### P2 — Sidebar sem agrupamento visual (ALTA prioridade)

10+ controles em sequência sem separadores, títulos de seção ou hierarquia visual. Gera carga cognitiva elevada. Precisa de agrupamento em pelo menos 3 seções: **Configuração**, **Filtros** e **Ações**.

### P3 — Telas com espaço vazio excessivo (MÉDIA prioridade)

- **Tags**: uma tag cadastrada, enorme área vazia abaixo
- **Exportar**: formulário ocupa metade superior, lista de sessões abaixo — mas sem estado vazio elegante quando não há sessões no filtro

### P4 — Navegação superior: radio buttons nativos (MÉDIA prioridade)

Os tabs são Streamlit radio buttons com CSS customizado. O estado ativo não tem diferenciação visual suficiente (contraste de cor da label ativa vs inativa é baixo). Os ícones nos labels são emojis que variam por sistema.

### P5 — Falta de escala tipográfica consistente (MÉDIA prioridade)

Títulos de página usam `##` Markdown, metadados usam `<small>`, rótulos de seção usam texto corrido. Não há hierarquia tipográfica clara: H1 > H2 > label > body > caption.

### P6 — Inconsistência de bordas e fundos nos cards (BAIXA prioridade)

Cards de workspace usam `.ws-card` com borda roxa e fundo `#1a1a2e`. Mensagens de assistente usam gradiente `#0d1117` → `#161b22`. Grupos de data no Diário usam bordas laterais coloridas. São três padrões distintos sem sistema unificado.

### P7 — Estados visuais incompletos (BAIXA prioridade)

- Loading state: spinner Streamlit nativo sem feedback contextual
- Empty state: alguns têm mensagem, outros têm espaço em branco
- Hover em linhas de lista: inconsistente entre telas
- Disabled: não há estilo diferenciado para botões desabilitados

### P8 — Chips/labels truncados na sidebar (BAIXA prioridade)

`agent_sessi...`, `chat_sessi...` truncam o nome da fonte. Em telas maiores, poderiam exibir o nome completo ou um label amigável (ex: "Agent Sessions" → "Agente").

---

## 5. Contratos Existentes que Devem ser Preservados

| Elemento | Localização |
|---|---|
| Navegação entre módulos (6 tabs) | `app.py` — radio `view` |
| Filtros da sidebar (source, tags, hide empty) | `app.py` — sidebar section |
| Busca por título/palavra-chave | `app.py` — `search_query` input |
| Seletor de sessão (dropdown com label de data) | `app.py` — `selected_session` |
| Recarregar dados | `app.py` — `load_data.clear()` |
| Executar pipeline | `app.py` — subprocess pipeline |
| Exportar JSON individual | `app.py` — `st.download_button` |
| Exportar sessões em ZIP | `app.py` — tab Exportar |
| Selecionar/desmarcar todas (Exportar) | `app.py` — checkboxes |
| Criar/excluir tags | `app.py` — tab Tags |
| Visualização lista/cards (Workspaces) | `app.py` — `ws_view` radio |
| Timeline por dia com anterior/próximo | `app.py` — tab Timeline |
| Diário agrupado por data | `app.py` — tab Diary |
| Botões de abrir/acessar sessão | `app.py` — session selector |
| Copiar texto (expander) | `app.py` — `render_message` |
| Mostrar tool calls (checkbox) | `app.py` — `show_tool_calls` |
| Salvar no workspace (checkbox) | `app.py` — conversation tab |
| Metadados: data, perguntas, respostas, tags, workspace, status | `app.py` — stat bar + session header |
| Seletor de idioma | `app.py` — sidebar + `i18n.py` |
| Seletor de tema claro/escuro | `app.py` — `_CSS_DARK` / `_CSS_LIGHT` |

---

## 6. Recomendações Gerais de Design

### 6.1 Cor primária única

Adotar **índigo** (`#6366f1`) como cor primária consistente. Usar variações:

- `#6366f1` — primary / filtros ativos / tabs ativos
- `#4f46e5` — primary dark / hover
- `#818cf8` — primary light / ícones secundários

Remover o vermelho de filtros ativos. Vermelho fica reservado para erros e contagens com badge de alerta.

### 6.2 Sidebar em 3 seções

```
┌─────────────────────────┐
│ Chat Viewer             │
│ 579 sessões carregadas  │
├─────────────────────────┤
│ CONFIGURAÇÃO            │
│   Idioma    [pt-BR ▾]  │
│   Tema      [Escuro]    │
├─────────────────────────┤
│ FILTROS                 │
│   Busca: [________]    │
│   Fonte: [multiselect] │
│   ☑ Ocultar vazias    │
│   Tags: [choose ▾]    │
│   232 sessões           │
│   [2026-05-16 — ... ▾] │
├─────────────────────────┤
│ AÇÕES                   │
│   [↺ Recarregar dados] │
│   [▶ Executar pipeline]│
└─────────────────────────┘
```

### 6.3 Chips de filtro: substituir vermelho por índigo

Onde hoje `background: #e53e3e` (vermelho), usar `background: #312e81` com borda `#6366f1` e texto `#c7d2fe`.

### 6.4 Tabs de navegação: reforçar estado ativo

Tab ativo: texto branco + underline `#6366f1` + weight 600. Tab inativo: texto `#94a3b8` + weight 400.

---

## 7. Recomendações por Tela

### 7.1 Conversa

**Diagnóstico:** Tela melhor estruturada. Funciona bem.

**Melhorias:**
- Stat bar: aumentar espaçamento interno, `gap: 12px` (hoje 8px)
- Header de sessão: adicionar linha separadora sutil após o título
- Balões de mensagem: aumentar `border-radius` de 12px para 16px
- Timestamp: alinhar verticalmente com o role indicator
- Tool calls: adicionar ícone antes de "Tool call" para escaneabilidade

**Preservar:** exportar, salvar workspace, copiar, mostrar tool calls.

### 7.2 Diário de Atividades

**Diagnóstico:** Funciona bem. Grupos por data são claros.

**Melhorias:**
- Header de data: fundo `#1e293b` com borda esquerda `#6366f1` de 3px
- Contador: alinhar à direita do header de data
- Item de sessão: hover background `#1e293b` com transição 150ms
- Botão de abrir sessão: mover para extrema direita, mais visível

**Preservar:** busca, filtros de data, exportar JSON, contadores.

### 7.3 Timeline

**Diagnóstico:** Boa estrutura. Navegação anterior/próximo funciona.

**Melhorias:**
- Botões Anterior/Próximo: style secondary com ícones `◀` `▶`
- Data central: tipografia maior (`1.25rem`, weight 600)
- Hora da mensagem: `#94a3b8` → `#cbd5e1` (mais legível)
- Separador visual mais sutil entre conversas diferentes

**Preservar:** navegação dia, toggle de tool calls, agrupamento por conversa.

### 7.4 Workspaces

**Diagnóstico:** Cards funcionam bem. Hover effect é um bom padrão.

**Melhorias:**
- Modo Lista: zebra stripe sutil (`#0f172a` / `#1e293b` alternado)
- Modo Cards: aumentar `min-width` para 320px
- Filtro por pasta: aumentar prominência (hoje input perdido no topo)
- Contador no header: tipografia de subtitle, não body

**Preservar:** toggle lista/cards, sessões expandíveis, tag assignment.

### 7.5 Tags

**Diagnóstico:** Tela com muito espaço vazio.

**Melhorias:**
- Empty state quando sem tags: "Crie tags para categorizar seus workspaces. Ex: cliente-a, financeiro, urgente."
- Com tags: mostrar cards com contagem de uso (não apenas texto + botão Excluir)
- Card de tag: chip colorido, "Usada em X workspace(s)", botão Excluir
- Layout em duas colunas para lista (quando > 3 tags)

**Preservar:** criar tag por input de texto, excluir tag.

### 7.6 Exportar

**Diagnóstico:** Formulário funcional, mas sem empty state elegante quando filtro retorna 0 sessões.

**Melhorias:**
- Layout em duas colunas: filtros (esq) + lista de sessões (dir)
- Empty state: "Nenhuma sessão encontrada. Ajuste as datas ou selecione outro workspace."
- Contador de sessões: pill azul destacado
- Resumo de seleção: "X de Y sessões selecionadas"

**Preservar:** filtro workspace, filtro data, seleção múltipla, export ZIP.

---

## 8. Proposta de Design System Leve

### 8.1 Paleta

```css
/* Neutrals (base dark) */
--bg-base:      #0f172a;   /* página */
--bg-surface:   #1e293b;   /* cards, sidebar */
--bg-raised:    #334155;   /* hover, dropdown */
--bg-overlay:   #475569;   /* tooltip */

/* Borders */
--border-subtle:  #1e293b;
--border-default: #334155;
--border-strong:  #475569;

/* Text */
--text-primary:   #f1f5f9;
--text-secondary: #94a3b8;
--text-muted:     #64748b;
--text-disabled:  #475569;

/* Primary (Indigo) */
--primary-900: #1e1b4b;
--primary-800: #312e81;
--primary-600: #4f46e5;
--primary-500: #6366f1;
--primary-400: #818cf8;
--primary-200: #c7d2fe;

/* Semantic */
--success: #22c55e;
--warning: #f59e0b;
--error:   #ef4444;
--info:    #38bdf8;

/* Source badges */
--badge-agent:    #1d4ed8;   /* azul */
--badge-chat:     #7c3aed;   /* roxo */
--badge-openai:   #065f46;   /* verde escuro */
--badge-copilot:  #1e3a5f;   /* azul marinho */
--badge-claude:   #92400e;   /* âmbar escuro */
```

### 8.2 Tipografia

```css
--text-xs:   0.75rem;    /* 12px — metadata, timestamps */
--text-sm:   0.875rem;   /* 14px — labels, badges */
--text-base: 1rem;       /* 16px — body, mensagens */
--text-lg:   1.125rem;   /* 18px — subtítulos de card */
--text-xl:   1.25rem;    /* 20px — títulos de seção */
--text-2xl:  1.5rem;     /* 24px — títulos de página */

/* Hierarquia */
/* H1 de página:  2xl / semibold / text-primary */
/* H2 de seção:   xl  / medium   / text-secondary */
/* Label:         sm  / medium   / text-secondary */
/* Body:          base / normal  / text-primary */
/* Metadata:      xs  / normal   / text-muted */
```

### 8.3 Espaçamentos (base 4px)

```css
--space-1: 4px;   --space-2: 8px;   --space-3: 12px;
--space-4: 16px;  --space-5: 20px;  --space-6: 24px;

/* Padding interno de card: 16px */
/* Gap entre cards: 12px */
/* Gap entre itens de lista: 8px */
/* Border radius card: 8px */
/* Border radius button: 6px */
/* Border radius chip/badge: 4px */
/* Border radius message bubble: 16px */
```

### 8.4 Botões

```css
/* Primary:   bg=#6366f1, text=white, hover=#4f46e5 */
/* Secondary: bg=transparent, border=#334155, text=#94a3b8, hover-bg=#1e293b */
/* Danger:    bg=transparent, border=#ef4444, text=#ef4444, hover-bg=#1f1315 */
/* Ghost:     bg=transparent, text=#94a3b8, hover text=white */
```

### 8.5 Inputs e Filtros

```css
/* Input base */
/* bg: #1e293b, border: 1px solid #334155 */
/* focus: border-color: #6366f1, box-shadow: 0 0 0 2px #312e81 */

/* Filtro ativo (chip selecionado) */
/* bg: #312e81, border: 1px solid #6366f1, text: #c7d2fe */
/* NAO usar vermelho para estado de filtro ativo */
```

### 8.6 Cards

```css
/* Base:      bg=#1e293b, border=1px solid #334155, border-radius=8px */
/* Hover:     border-color=#6366f1, transition=150ms */
/* Selecionado: border-color=#6366f1, bg=#1e1b4b, border-left=3px solid #6366f1 */
```

### 8.7 Chips/Tags

```css
/* Tag badge: bg=#312e81, text=#c7d2fe, border-radius=4px, padding=2px 8px */
/* Source badge: cores distintas por fonte (paleta acima) */
/* Chip filtro ativo: mesma estética do tag badge (índigo) */
```

### 8.8 Estados Visuais

| Estado | Tratamento proposto |
|---|---|
| Loading | Spinner + texto contextual |
| Empty state | Ícone + título + descrição + ação sugerida |
| Error state | Borda vermelha + ícone + mensagem clara |
| Selected | Borda esquerda índigo 3px + bg `#1e1b4b` |
| Active tab | Underline `#6366f1` 2px + texto white weight 600 |
| Hover (lista) | bg `#1e293b`, transition 100ms |
| Hover (card) | border-color `#6366f1`, transition 150ms |
| Disabled | opacity 0.4, cursor not-allowed |
| Filtro ativo | chip índigo na sidebar |

---

## 9. Oportunidades de Alto Impacto e Baixo Risco

Mudanças no CSS inline (`_CSS_DARK`) sem alterar lógica Python:

1. **Chips de filtro: vermelho → índigo** — 5 linhas de CSS. Impacto imediato, zero risco.
2. **Sidebar: adicionar `st.divider()` entre seções** — 3 linhas Python. Zero risco.
3. **Sidebar: subtítulos de seção** (`st.caption("FILTROS")`) — 3 linhas Python. Zero risco.
4. **Tab ativo: aumentar contraste** — `font-weight: 600` no radio label ativo. 2 linhas CSS.
5. **Message bubbles: border-radius 12px → 16px** — 1 linha CSS. Zero risco.
6. **Empty state na tela Tags** — bloco condicional `if len(tags) == 0`. 5 linhas Python.
7. **Stat bar: aumentar gap interno** — 1 linha CSS. Zero risco.
8. **Labels amigáveis nos chips de fonte** — mapa de display names no i18n. 10 linhas Python.

---

## 10. Melhorias Estruturais

Mudanças que requerem refatoração moderada:

1. **Sidebar com 3 seções explícitas** — reorganizar ordem dos widgets + separadores + captions. Risco baixo.
2. **Design system CSS centralizado** — extrair variáveis para `:root {}` no `_CSS_COMMON`. Risco baixo.
3. **Tags: card view com contagem de uso** — substituir `st.text + st.button` por HTML card. Moderado.
4. **Exportar: layout em duas colunas** — `st.columns([1, 2])` para filtros + lista. Moderado.
5. **Source chips: label completo sem truncamento** — mapa de display names + paleta. Moderado.
6. **Tipografia: escala consistente com CSS variables** — padronizar todos os `font-size`. Alto volume, baixo risco.

---

## 11. Mudanças Sensíveis que Exigem Validação

1. **Reordenar sidebar** — pode confundir usuários com hábito de posição. Validar antes de deploy.
2. **Cor dos source badges** — vermelho pode ter significado semântico para o usuário. Confirmar.
3. **Tabs: migrar de radio para `st.tabs`** — requer reescrita dos blocos de conteúdo. Alto risco.
4. **Tags com cor associável** — adiciona campo novo ao `tags.json`. Precisa de migração.
5. **Layout de Exportar em duas colunas** — em notebooks 1366px pode ficar comprimido. Testar.

---

## 12. Roadmap UX/UI

### Fase 1 — Quick Wins (1-2h)

- [ ] Chips de filtro: vermelho → índigo
- [ ] Sidebar: separadores e subtítulos de seção (CONFIGURAÇÃO / FILTROS / AÇÕES)
- [ ] Tab ativo: font-weight 600 + underline índigo
- [ ] Message bubbles: border-radius 16px
- [ ] Empty state na tela Tags
- [ ] Labels amigáveis nos source chips
- [ ] Stat bar: gap interno maior

### Fase 2 — Design System (2-4h)

- [ ] Criar bloco `:root {}` com CSS variables de cor, tipografia e espaçamento
- [ ] Migrar `_CSS_DARK` e `_CSS_COMMON` para as variables
- [ ] Padronizar card pattern (base, hover, selected)
- [ ] Padronizar tipografia (escala proposta)
- [ ] Padronizar botões (primary / secondary / danger / ghost)

### Fase 3 — Melhorias por Tela (4-8h)

- [ ] Tags: card view com contagem de uso + empty state melhorado
- [ ] Exportar: layout duas colunas + resumo de seleção
- [ ] Workspaces: zebra stripe no modo lista + filtro de pasta proeminente
- [ ] Timeline: botões de navegação melhorados + hora mais legível
- [ ] Diário: header de data com borda esquerda índigo

### Fase 4 — Mudanças Estruturais (validar antes)

- [ ] Avaliar migração de radio tabs para `st.tabs` nativo
- [ ] Tags com cor associável
- [ ] Responsividade em telas estreitas

---

## 13. Checklist de Regressão Visual e Funcional

### Navegação

- [ ] Todos os 6 módulos navegam corretamente
- [ ] Tab ativo é visualmente distinguível
- [ ] Troca de tab não perde estado de filtro da sidebar

### Sidebar

- [ ] Seletor de idioma funciona (pt-BR, en, es)
- [ ] Toggle de tema claro/escuro funciona e persiste
- [ ] Busca por título/palavra-chave filtra sessões corretamente
- [ ] Filtro de fonte (multiselect) funciona
- [ ] Checkbox "Ocultar sessões vazias" funciona
- [ ] Filtro de tags funciona
- [ ] Contador de sessões atualiza conforme filtros
- [ ] Seletor de sessão navega corretamente
- [ ] Botão "Recarregar dados" funciona
- [ ] Botão "Executar pipeline" abre log e executa

### Conversa

- [ ] Mensagens de usuário: alinhadas à direita
- [ ] Mensagens de assistente: alinhadas à esquerda
- [ ] Tool calls: aparecem em expanders
- [ ] Checkbox "Mostrar tool calls" funciona
- [ ] Botão "Copiar texto" funciona
- [ ] Checkbox "Salvar no workspace" funciona
- [ ] Botão "Exportar JSON" baixa arquivo
- [ ] Stat bar exibe todos os campos

### Diário de Atividades

- [ ] Sessões agrupadas por data
- [ ] Busca por título/thread ID funciona
- [ ] Filtros de data (De / Até) funcionam
- [ ] Botão de abrir sessão navega para a conversa
- [ ] Contador total correto

### Timeline

- [ ] Navegação Anterior / Próximo funciona
- [ ] Data central correta
- [ ] Checkbox "Mostrar tool calls" funciona
- [ ] Mensagens agrupadas por conversa
- [ ] Timestamps no fuso local

### Workspaces

- [ ] Toggle Lista / Cards funciona
- [ ] Filtro por pasta funciona
- [ ] Cards expandem para mostrar sessões
- [ ] Tag badges exibem corretamente
- [ ] Tags do workspace podem ser editadas

### Tags

- [ ] Input de nova tag + botão Criar funciona
- [ ] Tag criada aparece imediatamente
- [ ] Botão Excluir remove a tag
- [ ] Contagem "Usada em X workspace(s)" correta

### Exportar

- [ ] Seletor de workspace funciona
- [ ] Filtros de data funcionam
- [ ] Contador de sessões disponíveis atualiza
- [ ] "Selecionar todas" / "Desmarcar todas" funcionam
- [ ] Checkboxes individuais funcionam
- [ ] Download ZIP funciona com sessões selecionadas
- [ ] ZIP contém os JSONs corretos

### Temas

- [ ] Tema escuro: contraste adequado em todos os elementos
- [ ] Tema claro: contraste adequado em todos os elementos
- [ ] Transição entre temas não quebra layout

### Responsividade

- [ ] Em 1920px: sem overflow horizontal
- [ ] Em 1366px: sidebar não colapsa conteúdo principal
- [ ] Em 1024px: layouts de duas colunas não ficam comprimidos

---

## 14. Próximo Passo Recomendado

**Implementar a Fase 1 (Quick Wins)** — edições no CSS inline de `pipeline/viewer/app.py` nas seções `_CSS_DARK` e `_CSS_COMMON`, mais adição de separadores e captions na sidebar.

Estimativa: 1-2h. Impacto visual imediato sem risco funcional.
