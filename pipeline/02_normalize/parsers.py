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
from urllib.parse import unquote, urlparse

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


def _normalize_windows_path(path: str) -> str:
    normalized = unquote(path).replace("/", "\\").strip("\\")
    if len(normalized) >= 2 and normalized[1] == ":":
        normalized = normalized[0].upper() + normalized[1:]
    return normalized


def _uri_to_path(uri) -> str:
    if isinstance(uri, dict):
        if uri.get("fsPath"):
            return str(uri.get("fsPath"))
        if uri.get("path"):
            return _normalize_windows_path(str(uri.get("path")))
        if uri.get("external"):
            return _uri_to_path(uri.get("external"))
        return ""
    if isinstance(uri, str):
        if uri.startswith("file://"):
            parsed = urlparse(uri)
            return _normalize_windows_path(parsed.path)
        return uri
    return ""


def _short_preview(text: str, limit: int = 160) -> str:
    flat = text.replace("\r", " ").replace("\n", " ").strip()
    if len(flat) <= limit:
        return flat
    return flat[:limit] + "…"


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
# Parser: chatEditingSessions/<uuid>/state.json
# ---------------------------------------------------------------------------

def parse_chat_editing_state(path: Path, ws_hash: str = "") -> list[ChatMessage]:
    """Extrai checkpoints, operações e recentSnapshot de chatEditingSessions/state.json."""
    try:
        obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return []

    timeline = obj.get("timeline") or {}
    checkpoints = timeline.get("checkpoints") or []
    operations = timeline.get("operations") or []
    recent_entries = ((obj.get("recentSnapshot") or {}).get("entries") or [])

    session_id = path.parent.name
    source_file = str(path)
    messages: list[ChatMessage] = []

    for checkpoint in checkpoints:
        if not isinstance(checkpoint, dict):
            continue
        payload = {
            "_type": "chat_edit_checkpoint",
            "checkpoint_id": checkpoint.get("checkpointId"),
            "epoch": checkpoint.get("epoch"),
            "label": checkpoint.get("label"),
            "description": checkpoint.get("description"),
        }
        messages.append(
            ChatMessage(
                source="chat_editing_state",
                session_id=session_id,
                thread_id=session_id,
                timestamp=None,
                role="system",
                text=json.dumps(payload, ensure_ascii=False),
                workspace_hash=ws_hash or None,
                request_id=checkpoint.get("requestId") or None,
                raw_source_file=source_file,
            )
        )

    for operation in operations:
        if not isinstance(operation, dict):
            continue
        telemetry = operation.get("telemetryInfo") or {}
        op_type = operation.get("type") or "unknown"
        path_str = _uri_to_path(operation.get("uri"))
        edits = operation.get("edits") or []
        preview = []
        if isinstance(edits, list):
            for edit in edits[:3]:
                if not isinstance(edit, dict):
                    continue
                text = edit.get("text")
                if isinstance(text, str) and text:
                    preview.append(_short_preview(text, limit=120))
        payload = {
            "_type": "chat_edit_operation",
            "op_type": op_type,
            "epoch": operation.get("epoch"),
            "path": path_str or None,
            "edit_count": len(edits) if isinstance(edits, list) else None,
            "initial_content_len": len(operation.get("initialContent") or ""),
            "preview": preview or None,
        }
        messages.append(
            ChatMessage(
                source="chat_editing_state",
                session_id=session_id,
                thread_id=session_id,
                timestamp=None,
                role="system",
                text=json.dumps(payload, ensure_ascii=False),
                files_changed=[path_str] if path_str else [],
                workspace_hash=ws_hash or None,
                request_id=operation.get("requestId") or telemetry.get("requestId") or None,
                model_id=telemetry.get("modelId") or None,
                agent_id=telemetry.get("agentId") or None,
                mode_name=telemetry.get("modeId") or None,
                raw_source_file=source_file,
            )
        )

    for entry in recent_entries:
        if not isinstance(entry, dict):
            continue
        telemetry = entry.get("telemetryInfo") or {}
        path_str = _uri_to_path(entry.get("resource"))
        payload = {
            "_type": "chat_edit_snapshot",
            "path": path_str or None,
            "language_id": entry.get("languageId"),
            "state": entry.get("state"),
            "original_hash": entry.get("originalHash"),
            "current_hash": entry.get("currentHash"),
        }
        messages.append(
            ChatMessage(
                source="chat_editing_state",
                session_id=session_id,
                thread_id=session_id,
                timestamp=None,
                role="system",
                text=json.dumps(payload, ensure_ascii=False),
                files_changed=[path_str] if path_str else [],
                workspace_hash=ws_hash or None,
                request_id=telemetry.get("requestId") or None,
                model_id=telemetry.get("modelId") or None,
                agent_id=telemetry.get("agentId") or None,
                mode_name=telemetry.get("modeId") or None,
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
    - kind='inlineReference'      → referência de arquivo inline (nome do arquivo)
    - kind='thinking' + generatedTitle → fallback para agentes MCP/codex
    - kind='questionCarousel'     → Gemini: lista de opções

    Pre-processing: removes incremental-patch duplicates where a text part is a
    strict prefix of the next text part (VS Code streams tokens via kind=2
    patches so partial snapshots accumulate in the list).
    Internal streaming-only kinds (thinking, mcpServersStarting) are transparent
    to this lookahead — they do NOT act as barriers.
    """
    # Kinds that are internal VS Code streaming state — transparent to dedup lookahead
    _STREAMING_INTERNAL = {"thinking", "mcpServersStarting"}

    # De-dup: for each text part, look ahead (past internal/thinking parts) to
    # find the next text part. If that text part starts with the current value
    # and is strictly longer, the current part is a streaming partial → skip it.
    deduped: list = []
    for i, part in enumerate(response_parts):
        if not isinstance(part, dict):
            deduped.append(part)
            continue
        kind = part.get("kind")
        if not kind or kind == "unknown":
            val = part.get("value") or ""
            next_val: str | None = None
            for j in range(i + 1, len(response_parts)):
                nxt = response_parts[j]
                if not isinstance(nxt, dict):
                    continue
                nkind = nxt.get("kind")
                if not nkind or nkind == "unknown":
                    next_val = nxt.get("value") or ""
                    break
                if nkind in _STREAMING_INTERNAL:
                    continue  # transparent: keep scanning past thinking parts
                # Real content barrier (inlineReference, toolCall, …) — stop
                break
            if (
                next_val is not None
                and isinstance(val, str)
                and isinstance(next_val, str)
                and next_val.startswith(val)
                and val != next_val
            ):
                continue  # skip this truncated/partial streaming duplicate
        deduped.append(part)
    response_parts = deduped

    parts_text: list[str] = []
    thinking_fallback: list[str] = []
    _pending_ref: str | None = None  # filename waiting to be inlined
    _pending_codeblock_path: str | None = None  # path do codeblockUri (precede textEditGroup)

    def _uri_to_path(u) -> str:
        """Extrai fsPath/path de uma URI VS Code (dict ou string)."""
        if isinstance(u, dict):
            sub = u.get("uri") if isinstance(u.get("uri"), dict) else {}
            return (
                u.get("fsPath")
                or u.get("path")
                or (sub.get("fsPath") if isinstance(sub, dict) else "")
                or (sub.get("path") if isinstance(sub, dict) else "")
                or ""
            )
        return str(u or "")

    for part in response_parts:
        if not isinstance(part, dict):
            continue
        kind  = part.get("kind")
        value = part.get("value")

        if (not kind or kind == "unknown") and isinstance(value, str) and value.strip():
            if _pending_ref is not None:
                # A reference was pending — decide inline vs. new paragraph
                if value[:1] in (" ", "\t", ",", ".", ":", ";", ")", "!", "?", "'", "\u2019", "|", "\n"):
                    # Continuation: attach ref+value inline to the previous segment
                    if parts_text:
                        parts_text[-1] = parts_text[-1] + _pending_ref + value
                    else:
                        parts_text.append(_pending_ref + value)
                else:
                    # New paragraph: flush ref into previous segment, then start new
                    if parts_text:
                        parts_text[-1] = parts_text[-1] + _pending_ref
                    parts_text.append(value)
                _pending_ref = None
            elif parts_text and value[:1] in (" ", "\t"):
                # This text continues the previous paragraph inline (no ref in between)
                parts_text[-1] = parts_text[-1] + value
            else:
                parts_text.append(value)

        elif kind == "inlineReference":
            ref = part.get("inlineReference") or {}
            # VS Code URI can be a flat dict or have a nested 'uri' sub-object
            path_str: str = (
                ref.get("fsPath")
                or ref.get("path")
                or (ref.get("uri") or {}).get("fsPath")
                or (ref.get("uri") or {}).get("path")
                or _uri_to_path(ref.get("location"))
                or ""
            )
            if isinstance(path_str, str) and path_str:
                fname = Path(path_str).name
                if fname:
                    _pending_ref = (_pending_ref or "") + fname

        elif kind == "codeblockUri":
            # Path do arquivo cujo conteúdo aparecerá no próximo textEditGroup
            uri = part.get("uri") or {}
            p = _uri_to_path(uri)
            _pending_codeblock_path = p or None

        elif kind == "textEditGroup":
            # Edits propostos pelo assistente — recupera o texto completo das edições
            edits = part.get("edits") or []
            edit_texts: list[str] = []
            for batch in edits:
                if not isinstance(batch, list):
                    continue
                for e in batch:
                    if isinstance(e, dict):
                        t = e.get("text")
                        if isinstance(t, str) and t:
                            edit_texts.append(t)
            if edit_texts:
                body = "".join(edit_texts)
                # Se houver path pendente do codeblockUri, prefixa como cabeçalho
                if _pending_codeblock_path:
                    fname = Path(_pending_codeblock_path).name or _pending_codeblock_path
                    body = f"// {fname}\n{body}"
                parts_text.append(body)
            _pending_codeblock_path = None

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

    # Flush any trailing ref that wasn't followed by a text part
    if _pending_ref is not None and parts_text:
        parts_text[-1] = parts_text[-1] + _pending_ref

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

        request_id = str(req.get("requestId") or "").strip() or None
        response_id = str(req.get("responseId") or "").strip() or None
        model_id = str(req.get("modelId") or "").strip() or None

        agent = req.get("agent") or {}
        if isinstance(agent, dict):
            agent_id = str(agent.get("id") or "").strip() or None
            agent_name = str(agent.get("name") or agent.get("fullName") or "").strip() or None
        else:
            agent_id = None
            agent_name = None

        mode_info = req.get("modeInfo") or {}
        if isinstance(mode_info, dict):
            mode_name = str(mode_info.get("modeName") or mode_info.get("modeId") or "").strip() or None
        else:
            mode_name = None

        # ts_user: quando o usuário enviou a mensagem
        # ts_resp: quando o assistente terminou de responder (modelState.completedAt)
        # Usar timestamps separados corrige sessões com Restore Checkpoint, onde a
        # resposta é gerada muito depois da mensagem original (novo dia/horário).
        ts_user = _ms_to_iso(req.get("timestamp")) or creation_ts
        _model_state = req.get("modelState") or {}
        _completed_at = _model_state.get("completedAt") if isinstance(_model_state, dict) else None
        ts_resp = _ms_to_iso(_completed_at) or ts_user

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
                    timestamp=ts_user,
                    role="user",
                    text=user_text,
                    workspace_hash=_ws,
                    request_id=request_id,
                    response_id=response_id,
                    model_id=model_id,
                    agent_id=agent_id,
                    agent_name=agent_name,
                    mode_name=mode_name,
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
                    timestamp=ts_resp,
                    role="assistant",
                    text=resp_text,
                    files_changed=files_changed,
                    workspace_hash=_ws,
                    request_id=request_id,
                    response_id=response_id,
                    model_id=model_id,
                    agent_id=agent_id,
                    agent_name=agent_name,
                    mode_name=mode_name,
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
                        timestamp=ts_resp,
                        role="tool",
                        text=tc.get("result_summary") or "",
                        tool=tc.get("name"),
                        tool_input=(
                            json.dumps(tc.get("input"), ensure_ascii=False)
                            if tc.get("input") else None
                        ),
                        workspace_hash=_ws,
                        request_id=request_id,
                        response_id=response_id,
                        model_id=model_id,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        mode_name=mode_name,
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
# Parser: ~/.codex/sessions/**/*.jsonl — sessões Codex CLI / extensão openai.chatgpt
# ---------------------------------------------------------------------------

# Padrões de injeção de sistema a ignorar em mensagens de usuário
_CODEX_SYSTEM_PREFIXES = (
    "<environment_context",
    "# AGENTS.md",
    "<INSTRUCTIONS>",
    "<AGENTS.MD",
    "# Context from my IDE setup:",
)


def _codex_content_text(content: list) -> str:
    """
    Extrai e concatena texto de content items, ignorando injeções de sistema.
    Retorna string vazia se não sobrar conteúdo real.
    """
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        if any(text.startswith(prefix) for prefix in _CODEX_SYSTEM_PREFIXES):
            continue
        # Stripa cabeçalhos automáticos como "## My request for Codex:\n..."
        # e usa apenas o conteúdo após o cabeçalho
        if text.startswith("## My request for Codex:"):
            rest = text[len("## My request for Codex:"):].strip()
            if rest:
                parts.append(rest)
            continue
        parts.append(text)
    return "\n\n".join(parts)


def parse_codex_session_jsonl(path: Path) -> list[ChatMessage]:
    """
    Parseia um arquivo .jsonl do Codex (~/.codex/sessions/<year>/<month>/<day>/<uuid>.jsonl).

    Formato de cada linha:
      {"timestamp": "<iso>", "type": "session_meta|response_item|event_msg|...", "payload": {...}}

    Extrai:
      - session_meta  → thread_id (UUID da sessão), workspace path
      - response_item role=user      → mensagens reais do usuário (filtra injeções de sistema)
      - response_item role=assistant → respostas do assistente
    """
    source = str(path)
    thread_id: str | None = None
    session_ts: str | None = None
    workspace: str | None = None
    messages: list[ChatMessage] = []

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        _log.warning("Falha ao ler sessão Codex %s: %s", path, exc)
        return []

    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue

        event_type = event.get("type")
        payload = event.get("payload") or {}
        ts = event.get("timestamp")

        if event_type == "session_meta":
            thread_id = str(payload.get("id") or "")
            session_ts = str(payload.get("timestamp") or ts or "")
            workspace = str(payload.get("cwd") or "")
            # Emite um marker de título com o path do workspace
            if workspace and thread_id:
                messages.append(
                    ChatMessage(
                        source="codex_session",
                        session_id=thread_id,
                        thread_id=thread_id,
                        timestamp=session_ts or None,
                        role="system",
                        text=json.dumps(
                            {"_type": "session_workspace", "cwd": workspace},
                            ensure_ascii=False,
                        ),
                        workspace_hash=None,
                        raw_source_file=source,
                    )
                )
            continue

        if event_type != "response_item":
            continue

        role = str(payload.get("role") or "")
        content: list = payload.get("content") or []

        if role == "user":
            text = _codex_content_text(content)
            if not text:
                continue
            messages.append(
                ChatMessage(
                    source="codex_session",
                    session_id=thread_id or path.stem,
                    thread_id=thread_id or path.stem,
                    timestamp=ts or session_ts or None,
                    role="user",
                    text=text,
                    workspace_hash=None,
                    raw_source_file=source,
                )
            )

        elif role == "assistant":
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "output_text":
                    t = str(item.get("text") or "").strip()
                    if t:
                        parts.append(t)
            text = "\n\n".join(parts)
            if not text:
                continue
            messages.append(
                ChatMessage(
                    source="codex_session",
                    session_id=thread_id or path.stem,
                    thread_id=thread_id or path.stem,
                    timestamp=ts or session_ts or None,
                    role="assistant",
                    text=text,
                    workspace_hash=None,
                    raw_source_file=source,
                )
            )

    return messages


# ---------------------------------------------------------------------------
# Parser: ~/.claude/projects/<project>/<uuid>.jsonl
# ---------------------------------------------------------------------------

_CLAUDE_IGNORED_EVENTS = {
    "queue-operation",
    "attachment",
    "file-history-snapshot",
    "last-prompt",
    "mode",
    "system",
}


def _first_str(*values) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _claude_content_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            text = item.strip()
            if text:
                parts.append(text)
            continue
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type in (None, "text", "input_text", "output_text"):
            text = _first_str(item.get("text"), item.get("content"))
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def _claude_title(event: dict) -> str | None:
    return _first_str(
        event.get("customTitle"),
        event.get("custom_title"),
        event.get("title"),
        event.get("aiTitle"),
        event.get("ai_title"),
        event.get("text"),
        (event.get("message") or {}).get("title")
        if isinstance(event.get("message"), dict)
        else None,
        (event.get("message") or {}).get("content")
        if isinstance(event.get("message"), dict)
        else None,
    )


def parse_claude_code_session(path: Path) -> list[ChatMessage]:
    """Parseia JSONL do Claude Code CLI em mensagens canônicas."""
    source = str(path)
    project_slug = path.parent.name
    session_uuid = path.stem
    session_id = f"claude-code:/{session_uuid}"
    thread_id = session_id
    messages: list[ChatMessage] = []
    workspace_emitted = False

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        _log.warning("Falha ao ler sessão Claude Code %s: %s", path, exc)
        return []

    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("isSidechain") is True:
            continue

        event_type = str(event.get("type") or "")
        if event_type in _CLAUDE_IGNORED_EVENTS:
            continue

        ts = _first_str(event.get("timestamp"), event.get("createdAt"), event.get("created_at"))
        request_id = _first_str(event.get("requestId"), event.get("request_id"))
        response_id = _first_str(event.get("responseId"), event.get("response_id"))
        model_id = _first_str(event.get("model"), event.get("modelId"), event.get("model_id"))

        cwd = _first_str(event.get("cwd"))
        if cwd and not workspace_emitted:
            messages.append(
                ChatMessage(
                    source="claude_code_session",
                    session_id=session_id,
                    thread_id=thread_id,
                    timestamp=ts,
                    role="system",
                    text=json.dumps(
                        {"_type": "session_workspace", "cwd": cwd, "project": project_slug},
                        ensure_ascii=False,
                    ),
                    raw_source_file=source,
                )
            )
            workspace_emitted = True

        if event_type in ("ai-title", "custom-title"):
            title = _claude_title(event)
            if title:
                messages.append(
                    ChatMessage(
                        source="claude_code_session",
                        session_id=session_id,
                        thread_id=thread_id,
                        timestamp=ts,
                        role="system",
                        text=json.dumps(
                            {
                                "_type": "thread_title",
                                "title": title,
                                "project": project_slug,
                                "title_source": event_type,
                            },
                            ensure_ascii=False,
                        ),
                        request_id=request_id,
                        response_id=response_id,
                        model_id=model_id,
                        raw_source_file=source,
                    )
                )
            continue

        message = event.get("message") or {}
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or event_type or "").strip()
        content = message.get("content")
        request_id = request_id or _first_str(message.get("requestId"), message.get("request_id"))
        response_id = response_id or _first_str(message.get("id"), message.get("responseId"))
        model_id = model_id or _first_str(message.get("model"), message.get("modelId"))

        if role == "user":
            text = _claude_content_text(content)
            if text:
                messages.append(
                    ChatMessage(
                        source="claude_code_session",
                        session_id=session_id,
                        thread_id=thread_id,
                        timestamp=ts,
                        role="user",
                        text=text,
                        request_id=request_id,
                        response_id=response_id,
                        model_id=model_id,
                        raw_source_file=source,
                    )
                )

        elif role == "assistant":
            text = _claude_content_text(content)
            if text:
                messages.append(
                    ChatMessage(
                        source="claude_code_session",
                        session_id=session_id,
                        thread_id=thread_id,
                        timestamp=ts,
                        role="assistant",
                        text=text,
                        request_id=request_id,
                        response_id=response_id,
                        model_id=model_id,
                        raw_source_file=source,
                    )
                )

            if isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict) or item.get("type") != "tool_use":
                        continue
                    tool_name = _first_str(item.get("name"), item.get("tool"), item.get("id"))
                    tool_input = item.get("input")
                    messages.append(
                        ChatMessage(
                            source="claude_code_session",
                            session_id=session_id,
                            thread_id=thread_id,
                            timestamp=ts,
                            role="tool",
                            text="",
                            tool=tool_name,
                            tool_input=json.dumps(tool_input, ensure_ascii=False)
                            if tool_input is not None
                            else None,
                            request_id=request_id,
                            response_id=response_id,
                            model_id=model_id,
                            raw_source_file=source,
                        )
                    )

    return messages


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
