"""
parsers.py — Parsers especializados por tipo de fonte do VS Code.

Cada função recebe dados brutos de uma fonte específica e retorna
uma lista de ChatMessage no modelo canônico.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

# Raiz do repositório — necessário para imports de pipeline.*
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline.lib.db_reader import iter_jsonl
from pipeline.lib.models import ChatMessage

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utilitários compartilhados
# ---------------------------------------------------------------------------

def _ms_to_iso(ms: int | float | None) -> str | None:
    """Converte timestamp em milissegundos para ISO 8601 UTC."""
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return None


def _stable_id(key: str) -> str:
    """
    Gera UUID determinístico a partir de uma chave estável.
    Garante que o mesmo arquivo/fonte sempre produza o mesmo session_id,
    independente da ordem de execução do pipeline.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"chatsvs:{key}"))


# ---------------------------------------------------------------------------
# Parser: chave openai.chatgpt
# ---------------------------------------------------------------------------

def parse_openai_chatgpt(
    value_str: str,
    source_file: str,
    ws_hash: str | None,
) -> list[ChatMessage]:
    """
    Extrai o histórico de prompts e títulos de thread da chave openai.chatgpt.
    Cada entrada do prompt-history vira um ChatMessage com role='user'.
    """
    try:
        obj = json.loads(value_str)
    except json.JSONDecodeError:
        return []

    persisted = obj.get("persisted-atom-state") or {}
    prompt_history: list = persisted.get("prompt-history") or []

    thread_titles_block = obj.get("thread-titles") or {}
    titles: dict = thread_titles_block.get("titles") or {}
    order: list  = thread_titles_block.get("order") or []

    messages: list[ChatMessage] = []
    session_id = ws_hash or _stable_id(source_file)

    for idx, prompt in enumerate(prompt_history):
        thread_id = order[idx] if idx < len(order) else None
        title = titles.get(thread_id) if thread_id else None
        messages.append(
            ChatMessage(
                source="openai_chatgpt",
                session_id=session_id,
                thread_id=thread_id,
                timestamp=None,
                role="user",
                text=str(prompt),
                raw_source_file=source_file,
            )
        )
        if title and thread_id:
            messages.append(
                ChatMessage(
                    source="openai_chatgpt",
                    session_id=session_id,
                    thread_id=thread_id,
                    timestamp=None,
                    role="system",
                    text=json.dumps({"_type": "thread_title", "title": title}, ensure_ascii=False),
                    raw_source_file=source_file,
                )
            )

    return messages


# ---------------------------------------------------------------------------
# Parser: chave agentSessions.state.cache
# ---------------------------------------------------------------------------

def parse_agent_sessions_state(
    value_str: str,
    source_file: str,
    ws_hash: str | None,
) -> list[ChatMessage]:
    """
    Extrai recursos openai-codex:// e metadados de status de cada sessão.
    Cada entrada vira um ChatMessage com role='system' descrevendo o estado.
    """
    try:
        entries = json.loads(value_str)
    except json.JSONDecodeError:
        return []

    if not isinstance(entries, list):
        return []

    messages: list[ChatMessage] = []
    session_id = ws_hash or _stable_id(source_file)

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw_resource = entry.get("resource")
        if isinstance(raw_resource, dict):
            resource = raw_resource.get("path") or raw_resource.get("fsPath") or json.dumps(raw_resource)
        elif raw_resource is None:
            resource = ""
        else:
            resource = str(raw_resource)
        archived: bool = entry.get("archived", False)

        # Extrai thread_id do recurso openai-codex://route/local/<id>
        thread_id = None
        m = re.search(r"(?:local|openai-codex://[^/]+/[^/]+/)([a-f0-9\-]{32,})", resource)
        if m:
            thread_id = m.group(1)
        elif resource:
            thread_id = resource

        messages.append(
            ChatMessage(
                source="agent_sessions",
                session_id=session_id,
                thread_id=thread_id,
                timestamp=None,
                role="system",
                text=json.dumps(
                    {"_type": "agent_session", "resource": resource, "archived": archived},
                    ensure_ascii=False,
                ),
                raw_source_file=source_file,
            )
        )

    return messages


# ---------------------------------------------------------------------------
# Parser: chave chat.ChatSessionStore.index
# ---------------------------------------------------------------------------

def parse_chat_session_index(
    value_str: str,
    source_file: str,
    ws_hash: str | None,
) -> list[ChatMessage]:
    """
    Extrai entradas do índice de sessões Copilot Chat.
    Cada sessão vira um ChatMessage com role='system' contendo título e datas
    em formato JSON estruturado (evita regex frágil na extração posterior).
    """
    try:
        obj = json.loads(value_str)
    except json.JSONDecodeError:
        return []

    entries: dict = obj.get("entries") or {}
    if not isinstance(entries, dict):
        return []

    messages: list[ChatMessage] = []

    for session_id, meta in entries.items():
        if not isinstance(meta, dict):
            continue
        title = meta.get("title")
        last_msg_date = _ms_to_iso(meta.get("lastMessageDate"))
        messages.append(
            ChatMessage(
                source="chat_session_index",
                session_id=session_id,
                thread_id=session_id,
                timestamp=last_msg_date,
                role="system",
                text=json.dumps(
                    {"_type": "session_index", "title": title, "last_message": last_msg_date},
                    ensure_ascii=False,
                ),
                workspace_hash=ws_hash or None,
                raw_source_file=source_file,
            )
        )

    return messages


# ---------------------------------------------------------------------------
# Parser: arquivo *.jsonl do workspaceStorage (Copilot Chat sessions — formato legado)
# ---------------------------------------------------------------------------

_COPILOT_ROLE_MAP = {
    "user": "user",
    "assistant": "assistant",
    "human": "user",
    "bot": "assistant",
    "tool": "tool",
    "system": "system",
}


def _parse_copilot_jsonl_line(line: dict, source_file: str, ws_hash: str) -> list[ChatMessage]:
    """
    Tenta múltiplos formatos conhecidos de JSONL do VS Code/Copilot.
    Retorna uma lista de ChatMessage (normalmente 1, às vezes 2 para request+response).
    """
    messages: list[ChatMessage] = []

    # --- Formato 1: {role, content/text, timestamp?, id?, sessionId?} ---
    if "role" in line:
        role = _COPILOT_ROLE_MAP.get(str(line.get("role", "")).lower(), "system")
        text = str(line.get("content") or line.get("text") or "")
        ts = _ms_to_iso(line.get("timestamp")) or str(line.get("createdAt") or "")
        thread_id = str(line.get("sessionId") or line.get("threadId") or line.get("id") or "")
        tool_calls = line.get("toolCalls") or []
        files: list[str] = []
        for tc in (tool_calls if isinstance(tool_calls, list) else []):
            if isinstance(tc, dict) and "function" in tc:
                fn = tc["function"]
                if isinstance(fn, dict) and fn.get("name") in {"str_replace_editor", "create_file", "write_file"}:
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                        if "path" in args:
                            files.append(args["path"])
                    except Exception:
                        pass
        messages.append(
            ChatMessage(
                source="copilot_jsonl",
                session_id=ws_hash,
                thread_id=thread_id or None,
                timestamp=ts or None,
                role=role,
                text=text,
                files_changed=files,
                raw_source_file=source_file,
            )
        )
        return messages

    # --- Formato 2: {type: "request"|"response", message: {text, ...}, ...} ---
    if "type" in line and "message" in line:
        msg  = line["message"]
        kind = str(line.get("type", ""))
        role = "user" if kind == "request" else "assistant"
        text = str(msg.get("text") or msg.get("content") or "")
        ts   = _ms_to_iso(line.get("timestamp") or msg.get("timestamp"))
        thread_id = str(line.get("sessionId") or line.get("id") or "")
        messages.append(
            ChatMessage(
                source="copilot_jsonl",
                session_id=ws_hash,
                thread_id=thread_id or None,
                timestamp=ts or None,
                role=role,
                text=text,
                raw_source_file=source_file,
            )
        )
        return messages

    # --- Formato 3: {requestId, request: {...}, response: {...}} ---
    if "requestId" in line:
        req  = line.get("request") or {}
        resp = line.get("response") or {}
        ts_req  = _ms_to_iso(req.get("timestamp"))
        ts_resp = _ms_to_iso(resp.get("timestamp"))
        thread_id = str(line.get("sessionId") or line.get("requestId") or "")
        req_text  = str(req.get("message") or req.get("text") or req.get("content") or "")
        resp_text = str(resp.get("value") or resp.get("text") or resp.get("content") or "")
        if req_text:
            messages.append(
                ChatMessage(
                    source="copilot_jsonl",
                    session_id=ws_hash,
                    thread_id=thread_id or None,
                    timestamp=ts_req,
                    role="user",
                    text=req_text,
                    raw_source_file=source_file,
                )
            )
        if resp_text:
            messages.append(
                ChatMessage(
                    source="copilot_jsonl",
                    session_id=ws_hash,
                    thread_id=thread_id or None,
                    timestamp=ts_resp,
                    role="assistant",
                    text=resp_text,
                    raw_source_file=source_file,
                )
            )
        return messages

    # --- Fallback: linha desconhecida → grava como raw para inspeção ---
    messages.append(
        ChatMessage(
            source="copilot_jsonl_raw",
            session_id=ws_hash,
            thread_id=None,
            timestamp=None,
            role="system",
            text=f"[unparsed] {json.dumps(line, ensure_ascii=False)[:300]}",
            raw_source_file=source_file,
        )
    )
    return messages


def parse_copilot_jsonl_file(path: Path, ws_hash: str) -> list[ChatMessage]:
    """Parseia um arquivo *.jsonl do workspaceStorage (formato legado)."""
    messages: list[ChatMessage] = []
    for line in iter_jsonl(path):
        messages.extend(_parse_copilot_jsonl_line(line, str(path), ws_hash))
    return messages


# ---------------------------------------------------------------------------
# Parser: chatSessions/<uuid>.json — extração de partes de resposta
# ---------------------------------------------------------------------------

def extract_response_text(response_parts: list) -> str:
    """
    Extrai o texto markdown da resposta a partir da lista de parts.

    Hierarquia de extração:
    - kind=None / kind='unknown'  → texto principal da resposta
    - kind='thinking' + generatedTitle → fallback para agentes MCP/codex
    - kind='questionCarousel'     → Gemini: lista de opções
    """
    parts_text: list[str] = []
    thinking_fallback: list[str] = []

    for part in response_parts:
        if not isinstance(part, dict):
            continue
        kind  = part.get("kind")
        value = part.get("value")

        if (not kind or kind == "unknown") and isinstance(value, str) and value.strip():
            parts_text.append(value)

        elif (
            kind == "thinking"
            and isinstance(value, str)
            and value.strip()
            and "generatedTitle" in part
        ):
            thinking_fallback.append(value)

        elif kind == "questionCarousel":
            carousel_parts: list[str] = []
            title = part.get("title") or part.get("label") or ""
            if isinstance(title, str) and title.strip():
                carousel_parts.append(title.strip())
            items = part.get("items") or part.get("questions") or part.get("options") or []
            for item in (items if isinstance(items, list) else []):
                if isinstance(item, dict):
                    text = str(item.get("content") or item.get("text") or item.get("label") or "")
                    if text.strip():
                        carousel_parts.append(f"- {text.strip()}")
            if carousel_parts:
                parts_text.append("\n".join(carousel_parts))

    if parts_text:
        return "\n\n".join(parts_text).strip()
    return "\n\n".join(thinking_fallback).strip()


def extract_tool_calls(response_parts: list) -> list[dict]:
    """Extrai chamadas de ferramenta (toolInvocationSerialized)."""
    tools: list[dict] = []
    for part in response_parts:
        if not isinstance(part, dict):
            continue
        if part.get("kind") == "toolInvocationSerialized":
            invocation = part.get("invocation") or {}
            tools.append({
                "name": invocation.get("toolId") or invocation.get("name") or "",
                "input": invocation.get("parameters") or invocation.get("input"),
                "result_summary": str(invocation.get("result") or "")[:200],
            })
    return tools


def extract_files_changed(response_parts: list) -> list[str]:
    """Extrai caminhos de arquivo de textEditGroup e toolInvocations."""
    files: set[str] = set()
    for part in response_parts:
        if not isinstance(part, dict):
            continue
        kind = part.get("kind", "")
        if kind == "textEditGroup":
            uri  = part.get("uri") or {}
            path = uri.get("path") or uri.get("fsPath") if isinstance(uri, dict) else str(uri)
            if path:
                files.add(str(path))
        elif kind == "toolInvocationSerialized":
            invocation = part.get("invocation") or {}
            params = invocation.get("parameters") or {}
            if isinstance(params, dict):
                for key in ("path", "filePath", "file_path", "target"):
                    if key in params:
                        files.add(str(params[key]))
    return sorted(files)


# ---------------------------------------------------------------------------
# Parser compartilhado: dict de sessão → lista de ChatMessage
# ---------------------------------------------------------------------------

def parse_chat_session_obj(
    obj: dict,
    source_file: str,
    source_label: str,
    ws_hash: str = "",
) -> list[ChatMessage]:
    """Extrai mensagens de um dict de sessão já deserializado."""
    session_id   = str(obj.get("sessionId") or Path(source_file).stem)
    creation_ts  = _ms_to_iso(obj.get("creationDate"))
    custom_title = str(obj.get("customTitle") or "").strip()
    requests: list = obj.get("requests") or []
    messages: list[ChatMessage] = []
    _ws = ws_hash or None

    if custom_title and custom_title.lower() not in ("new chat", ""):
        messages.append(
            ChatMessage(
                source=source_label,
                session_id=session_id,
                thread_id=session_id,
                timestamp=creation_ts,
                role="system",
                text=json.dumps(
                    {"_type": "thread_title", "title": custom_title},
                    ensure_ascii=False,
                ),
                workspace_hash=_ws,
                raw_source_file=source_file,
            )
        )

    for req in requests:
        if not isinstance(req, dict):
            continue

        ts = _ms_to_iso(req.get("timestamp")) or creation_ts

        # Mensagem do usuário
        msg = req.get("message") or {}
        if isinstance(msg, str):
            user_text = msg
        elif isinstance(msg, dict):
            user_text = str(msg.get("text") or "")
        else:
            user_text = ""

        if user_text.strip():
            messages.append(
                ChatMessage(
                    source=source_label,
                    session_id=session_id,
                    thread_id=session_id,
                    timestamp=ts,
                    role="user",
                    text=user_text,
                    workspace_hash=_ws,
                    raw_source_file=source_file,
                )
            )

        # Resposta do assistente
        response_parts = req.get("response") or []
        if not isinstance(response_parts, list):
            response_parts = []

        resp_text    = extract_response_text(response_parts)
        tool_calls   = extract_tool_calls(response_parts)
        files_changed = extract_files_changed(response_parts)

        if resp_text.strip():
            messages.append(
                ChatMessage(
                    source=source_label,
                    session_id=session_id,
                    thread_id=session_id,
                    timestamp=ts,
                    role="assistant",
                    text=resp_text,
                    files_changed=files_changed,
                    workspace_hash=_ws,
                    raw_source_file=source_file,
                )
            )

        for tc in tool_calls:
            if tc.get("name"):
                messages.append(
                    ChatMessage(
                        source=source_label,
                        session_id=session_id,
                        thread_id=session_id,
                        timestamp=ts,
                        role="tool",
                        text=tc.get("result_summary") or "",
                        tool=tc.get("name"),
                        tool_input=(
                            json.dumps(tc.get("input"), ensure_ascii=False)
                            if tc.get("input") else None
                        ),
                        workspace_hash=_ws,
                        raw_source_file=source_file,
                    )
                )

    return messages


def parse_chat_session_json(path: Path, ws_hash: str = "") -> list[ChatMessage]:
    """Faz parse do estado final de um arquivo chatSessions/<uuid>.json."""
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            obj = json.load(f)
    except Exception as exc:
        _log.warning("Falha ao ler %s: %s", path, exc)
        return []
    return parse_chat_session_obj(obj, str(path), "chat_session_json", ws_hash)


def parse_chat_session_jsonl(path: Path, ws_hash: str = "") -> list[ChatMessage]:
    """Reconstrói e parseia um arquivo chatSessions/<uuid>.jsonl."""
    from pipeline.lib.patch import reconstruct_chat_session_jsonl
    obj = reconstruct_chat_session_jsonl(path)
    if not obj:
        return []
    return parse_chat_session_obj(obj, str(path), "chat_session_jsonl", ws_hash)


# ---------------------------------------------------------------------------
# Dispatcher: keys.jsonl sidecar → chama parser correto por chave
# ---------------------------------------------------------------------------

_KEY_PARSERS = {
    "openai.chatgpt":              parse_openai_chatgpt,
    "agentSessions.state.cache":   parse_agent_sessions_state,
    "chat.ChatSessionStore.index": parse_chat_session_index,
}


def parse_keys_sidecar(sidecar_path: Path, ws_hash: str | None) -> list[ChatMessage]:
    """Processa um arquivo .keys.jsonl e despacha para o parser correto por chave."""
    messages: list[ChatMessage] = []
    for entry in iter_jsonl(sidecar_path):
        key    = entry.get("key", "")
        value  = entry.get("value", "")
        parser = _KEY_PARSERS.get(key)
        if parser:
            messages.extend(parser(value, str(sidecar_path), ws_hash))
    return messages
