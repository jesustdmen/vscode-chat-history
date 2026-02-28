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

# Raiz do repositório — necessário para imports de pipeline.*
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline.lib.models import ChatMessage, SessionSummary

_log = logging.getLogger(__name__)


def build_summaries(all_messages: list[ChatMessage]) -> list[SessionSummary]:
    """
    Agrupa mensagens por (source, session_id, thread_id) e produz
    um SessionSummary por grupo.

    Extração de título:
    - Mensagens system com _type='thread_title' → título da sessão
    - Mensagens system com _type='session_index' → título do índice
    Ambos os formatos usam JSON estruturado (sem regex frágil).
    """
    groups: dict[tuple, list[ChatMessage]] = defaultdict(list)
    for m in all_messages:
        groups[(m.source, m.session_id, m.thread_id)].append(m)

    summaries: list[SessionSummary] = []

    for (source, session_id, thread_id), msgs in groups.items():
        timestamps = sorted(m.timestamp for m in msgs if m.timestamp)

        files_all: list[str] = []
        for m in msgs:
            files_all.extend(m.files_changed)

        # Extrai título a partir de mensagens system com JSON estruturado
        title: str | None = None
        for m in msgs:
            if m.role != "system" or not m.text:
                continue
            try:
                meta = json.loads(m.text)
                t = meta.get("_type", "")
                if t in ("thread_title", "session_index"):
                    candidate = (meta.get("title") or "").strip()
                    if candidate:
                        title = candidate
                        break
            except (json.JSONDecodeError, AttributeError):
                # Mensagem system em formato legado (texto livre) — ignora
                pass

        user_turns      = sum(1 for m in msgs if m.role == "user")
        assistant_turns = sum(1 for m in msgs if m.role == "assistant")
        tool_calls_cnt  = sum(1 for m in msgs if m.role == "tool")

        # workspace_hash: prefere o hash de 32 chars (MD5 do path do workspace)
        ws_hash = next(
            (m.workspace_hash for m in msgs if m.workspace_hash),
            session_id if len(session_id) == 32 else None,
        )

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
