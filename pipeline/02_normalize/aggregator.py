"""
aggregator.py — Agregação de ChatMessages em SessionSummary.

Recebe a lista completa de mensagens normalizadas e produz
um resumo por (source, session_id, thread_id).
"""

from __future__ import annotations

import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote

# Raiz do repositório — necessário para imports de pipeline.*
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline.lib.config import CODEX_SESSION_INDEX, WORKSPACE_STORAGE_DIR
from pipeline.lib.models import ChatMessage, SessionSummary

_log = logging.getLogger(__name__)


def _build_ws_path_to_hash() -> dict[str, str]:
    """Mapa reverso: caminho_normalizado_lower → workspace_hash.

    Lê workspace.json de cada workspaceStorage/<hash>/ e normaliza o path
    da mesma forma que load_workspace_paths() no viewer (file:///... → C:\\...).
    """
    result: dict[str, str] = {}
    if not WORKSPACE_STORAGE_DIR.exists():
        return result
    for d in WORKSPACE_STORAGE_DIR.iterdir():
        if not d.is_dir():
            continue
        wf = d / "workspace.json"
        if not wf.is_file():
            continue
        try:
            data = json.loads(wf.read_text(encoding="utf-8"))
            raw = data.get("folder") or data.get("workspace") or ""
            if raw.startswith("file:///"):
                raw = raw[8:]
            path = unquote(raw).replace("/", "\\").strip("\\")
            if len(path) >= 2 and path[1] == ":":
                path = path[0].upper() + path[1:]
            if path:
                result[path.lower()] = d.name
        except Exception:
            pass
    return result


def _normalize_cwd(cwd: str) -> str:
    """Normaliza um cwd do Codex para o mesmo formato dos paths do workspace.json."""
    path = cwd.replace("/", "\\").strip("\\")
    if len(path) >= 2 and path[1] == ":":
        path = path[0].upper() + path[1:]
    return path


def _load_codex_thread_names() -> dict[str, str]:
    """Carrega session_index.jsonl do Codex retornando {session_id: thread_name}."""
    result: dict[str, str] = {}
    if not CODEX_SESSION_INDEX.exists():
        return result
    try:
        for line in CODEX_SESSION_INDEX.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                sid = d.get("id", "")
                name = (d.get("thread_name") or "").strip()
                if sid and name:
                    result[sid] = name  # última entrada vence (ordem crescente)
            except json.JSONDecodeError:
                pass
    except OSError:
        _log.warning("Não foi possível ler session_index.jsonl")
    return result


def build_summaries(all_messages: list[ChatMessage]) -> list[SessionSummary]:
    """
    Agrupa mensagens por (source, session_id, thread_id) e produz
    um SessionSummary por grupo.

    Extração de título:
    - Mensagens system com _type='thread_title' → título da sessão
    - Mensagens system com _type='session_index' → título do índice
    Ambos os formatos usam JSON estruturado (sem regex frágil).
    """
    codex_names = _load_codex_thread_names()
    ws_path_to_hash = _build_ws_path_to_hash()

    groups: dict[tuple, list[ChatMessage]] = defaultdict(list)
    for m in all_messages:
        groups[(m.source, m.session_id, m.thread_id)].append(m)

    summaries: list[SessionSummary] = []

    for (source, session_id, thread_id), msgs in groups.items():
        timestamps = sorted(m.timestamp for m in msgs if m.timestamp)

        files_all: list[str] = []
        for m in msgs:
            files_all.extend(m.files_changed)

        # 0. Título AI-generated do Codex (session_index.jsonl) — máxima prioridade
        title: str | None = codex_names.get(session_id) if session_id else None

        # 1. Extrai título a partir de mensagens system com JSON estruturado
        if not title:
            title_candidates: list[tuple[int, str]] = []
            for m in msgs:
                if m.role != "system" or not m.text:
                    continue
                try:
                    meta = json.loads(m.text)
                    t = meta.get("_type", "")
                    if t in ("thread_title", "session_index"):
                        candidate = (meta.get("title") or "").strip()
                        if candidate:
                            if source == "claude_code_session" and t == "thread_title":
                                title_source = meta.get("title_source")
                                priority = 0 if title_source == "custom-title" else 1
                                title_candidates.append((priority, candidate))
                            else:
                                title = candidate
                                break
                except (json.JSONDecodeError, AttributeError):
                    # Mensagem system em formato legado (texto livre) — ignora
                    pass
            if not title and title_candidates:
                title = sorted(title_candidates, key=lambda item: item[0])[0][1]

        # Fallback: primeira mensagem do usuário como título
        if not title:
            for m in sorted(msgs, key=lambda x: x.timestamp or ""):
                if m.role == "user" and m.text and m.text.strip():
                    raw = m.text.strip().splitlines()[0].strip()
                    if raw:
                        title = raw[:80] + ("…" if len(raw) > 80 else "")
                        break

        user_turns      = sum(1 for m in msgs if m.role == "user")
        assistant_turns = sum(1 for m in msgs if m.role == "assistant")
        tool_calls_cnt  = sum(1 for m in msgs if m.role == "tool")

        # workspace_hash: prefere o hash de 32 chars (MD5 do path do workspace)
        ws_hash = next(
            (m.workspace_hash for m in msgs if m.workspace_hash),
            session_id if len(session_id) == 32 else None,
        )

        # Para sessões Codex e Claude Code, deriva workspace_hash via lookup cwd → workspaceStorage
        if not ws_hash and source in ("codex_session", "claude_code_session"):
            for m in msgs:
                if m.role == "system" and m.text:
                    try:
                        meta = json.loads(m.text)
                        if meta.get("_type") == "session_workspace":
                            cwd = meta.get("cwd") or ""
                            if cwd:
                                normalized = _normalize_cwd(cwd)
                                ws_hash = ws_path_to_hash.get(normalized.lower())
                                if ws_hash:
                                    break
                    except (json.JSONDecodeError, AttributeError):
                        pass

        summaries.append(
            SessionSummary(
                session_id=session_id,
                thread_id=thread_id,
                source=source,
                title=title,
                first_ts=timestamps[0] if timestamps else None,
                last_ts=timestamps[-1] if timestamps else None,
                message_count=len(msgs),
                user_turns=user_turns,
                assistant_turns=assistant_turns,
                tool_calls=tool_calls_cnt,
                files_changed=sorted(set(files_all)),
                workspace_hash=ws_hash,
            )
        )

    return summaries
