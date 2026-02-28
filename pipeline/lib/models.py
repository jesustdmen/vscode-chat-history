"""
models.py — Modelo canônico de mensagem de chat.

Todas as fontes (JSONL do workspaceStorage, chaves SQLite) são normalizadas
para uma lista de ChatMessage antes de qualquer análise ou relatório.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal, Optional
import json


# Fontes de dados reconhecidas pelo pipeline
SourceType = Literal[
    "chat_session_json",    # chatSessions/<uuid>.json  — estado final consolidado
    "chat_session_jsonl",   # chatSessions/<uuid>.jsonl — patches de sessão ativa
    "chat_session_index",   # globalStorage/state.vscdb → chat.ChatSessionStore.index
    "openai_chatgpt",       # globalStorage/state.vscdb → openai.chatgpt
    "agent_sessions",       # globalStorage/state.vscdb → agentSessions.state.cache
    "copilot_jsonl",        # workspaceStorage/<hash>/*.jsonl (formato legado)
    "copilot_jsonl_raw",    # linhas não parseadas do formato acima
    "chat_session",         # fonte mesclada usada apenas nos relatórios
]

# Papéis válidos de mensagem
RoleType = Literal["user", "assistant", "tool", "system"]


@dataclass
class ChatMessage:
    """Unidade mínima de uma troca de chat, independente de fonte."""

    # Identificação
    source: str                          # ver SourceType acima
    session_id: str                      # hash do workspace ou UUID estável
    thread_id: str | None                # id da thread/conversa, quando disponível

    # Temporal
    timestamp: str | None                # ISO 8601 ou None

    # Conteúdo
    role: str                            # ver RoleType acima
    text: str

    # Contexto de ferramenta (tool calls)
    tool: str | None = None              # nome da ferramenta, quando role == "tool"
    tool_input: str | None = None        # JSON serializado dos argumentos

    # Arquivos tocados durante a sessão
    files_changed: list[str] = field(default_factory=list)

    # Workspace de origem
    workspace_hash: str | None = None    # hash da pasta workspaceStorage

    # Rastreabilidade
    raw_source_file: str = ""            # caminho do arquivo raw que originou este registro

    def to_dict(self) -> dict:
        return asdict(self)

    def to_jsonl_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class SessionSummary:
    """Resumo agregado de uma sessão inteira."""

    session_id: str
    thread_id: str | None
    source: str
    title: str | None
    first_ts: str | None
    last_ts: str | None
    message_count: int
    user_turns: int
    assistant_turns: int
    tool_calls: int
    files_changed: list[str] = field(default_factory=list)
    workspace_hash: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_jsonl_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)
