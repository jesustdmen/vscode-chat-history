"""
03_report/report.py — Bloco 3: Geração de relatórios a partir do modelo canônico.

Produtos gerados em output/reports/:
  conversations_by_thread.jsonl — mensagens agrupadas por (session_id, thread_id)
  topics_summary.txt            — visão humana: uma linha por sessão com título e datas
  tool_calls.jsonl              — apenas eventos com role='tool'
  timeline.jsonl                — todas as mensagens com timestamp, ordem cronológica

Uso:
    python pipeline/03_report/report.py
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Raiz do repositório — necessário para imports de pipeline.*
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline.lib.config import OUTPUT_NORMALIZED, OUTPUT_REPORTS
from pipeline.lib.db_reader import iter_jsonl

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Leitura dos normalizados
# ---------------------------------------------------------------------------

def _load_sessions(sessions_path: Path) -> list[dict]:
    return list(iter_jsonl(sessions_path))


def _load_summaries(summaries_path: Path) -> list[dict]:
    return list(iter_jsonl(summaries_path))


# ---------------------------------------------------------------------------
# Relatório 1: conversations_by_thread.jsonl
# ---------------------------------------------------------------------------

def _report_conversations(messages: list[dict], out_dir: Path) -> Path:
    """Agrupa mensagens por (session_id, thread_id) e emite um bloco por grupo."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for m in messages:
        key = (m.get("session_id", ""), m.get("thread_id") or "__no_thread__")
        groups[key].append(m)

    out_path = out_dir / "conversations_by_thread.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for (session_id, thread_id), msgs in sorted(groups.items()):
            msgs.sort(key=lambda m: m.get("timestamp") or "9999")
            block = {
                "session_id": session_id,
                "thread_id": thread_id if thread_id != "__no_thread__" else None,
                "message_count": len(msgs),
                "messages": msgs,
            }
            fh.write(json.dumps(block, ensure_ascii=False) + "\n")

    return out_path


# ---------------------------------------------------------------------------
# Relatório 2: topics_summary.txt
# ---------------------------------------------------------------------------

def _report_topics(summaries: list[dict], out_dir: Path) -> Path:
    """
    Visão tabular em texto simples: uma linha por sessão.

    Estratégia de mesclagem:
    - Pares (chat_session_index, chat_session_json/jsonl) com o mesmo thread_id
      são colapsados: título vem do índice (ou do json), contagens do json.
    - Demais fontes são exibidas como estão.
    """
    relevant = [
        s for s in summaries
        if s.get("source") not in {"agent_sessions"} and s.get("message_count", 0) > 0
    ]

    css_index: dict[str, dict] = {}
    css_json:  dict[str, dict] = {}
    others: list[dict] = []

    for s in relevant:
        src = s.get("source", "")
        tid = s.get("thread_id") or s.get("session_id") or ""
        if src == "chat_session_index":
            css_index[tid] = s
        elif src in ("chat_session_json", "chat_session_jsonl"):
            css_json[tid] = s
        else:
            others.append(s)

    merged: list[dict] = list(others)
    all_tids = set(css_index) | set(css_json)

    for tid in all_tids:
        idx = css_index.get(tid)
        jsn = css_json.get(tid)

        if jsn and idx:
            title = (idx.get("title") or "").strip() or (jsn.get("title") or "").strip()
            msg_count   = jsn.get("message_count", 0)
            user_turns  = jsn.get("user_turns", 0)
            asst_turns  = jsn.get("assistant_turns", 0)
            system_msgs = msg_count - user_turns - asst_turns - jsn.get("tool_calls", 0)
            if system_msgs < 0:
                _log.warning(
                    "Contagem inconsistente para thread %s: system_msgs=%d", tid[:16], system_msgs
                )
            visible_count = msg_count - max(0, system_msgs)
            merged.append({**jsn, "source": "chat_session", "title": title, "message_count": visible_count})
        elif jsn:
            title = (jsn.get("title") or "").strip()
            msg_count   = jsn.get("message_count", 0)
            user_turns  = jsn.get("user_turns", 0)
            asst_turns  = jsn.get("assistant_turns", 0)
            system_msgs = msg_count - user_turns - asst_turns - jsn.get("tool_calls", 0)
            if system_msgs < 0:
                _log.warning(
                    "Contagem inconsistente para thread %s: system_msgs=%d", tid[:16], system_msgs
                )
            visible_count = msg_count - max(0, system_msgs)
            merged.append({**jsn, "source": "chat_session", "title": title, "message_count": visible_count})
        elif idx is not None:
            # Sessão apenas no índice (sem arquivo parseado correspondente)
            merged.append(idx)

    merged.sort(key=lambda s: s.get("last_ts") or "", reverse=True)

    out_path = out_dir / "topics_summary.txt"
    lines = [
        f"{'SOURCE':<22} {'SESSION/THREAD':<36} {'MSGS':>5} {'U':>4} {'A':>4} {'LAST_TS':<26} TITLE",
        "-" * 120,
    ]
    for s in merged:
        thread  = (s.get("thread_id") or s.get("session_id") or "")[:36]
        title   = (s.get("title") or "")[:60]
        last_ts = (s.get("last_ts") or "—")[:26]
        source  = (s.get("source") or "")[:22]
        msgs    = s.get("message_count", 0)
        u       = s.get("user_turns", 0)
        a       = s.get("assistant_turns", 0)
        lines.append(f"{source:<22} {thread:<36} {msgs:>5} {u:>4} {a:>4} {last_ts:<26} {title}")

    lines.append("")
    lines.append(f"Total de sessoes: {len(merged)}")
    lines.append(f"Gerado em: {datetime.now(tz=timezone.utc).isoformat()}")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Relatório 3: tool_calls.jsonl
# ---------------------------------------------------------------------------

def _report_tool_calls(messages: list[dict], out_dir: Path) -> Path:
    """Extrai apenas as mensagens onde role='tool' ou tool != None."""
    tool_msgs = [
        m for m in messages
        if m.get("role") == "tool" or m.get("tool")
    ]
    tool_msgs.sort(key=lambda m: m.get("timestamp") or "")

    out_path = out_dir / "tool_calls.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for m in tool_msgs:
            fh.write(json.dumps(m, ensure_ascii=False) + "\n")

    return out_path


# ---------------------------------------------------------------------------
# Relatório 4: timeline.jsonl
# ---------------------------------------------------------------------------

def _report_timeline(messages: list[dict], out_dir: Path) -> Path:
    """
    Apenas mensagens com timestamp conhecida, ordenadas cronologicamente.
    Campos emitidos: timestamp, session_id, thread_id, role, source, text (truncado).
    """
    timed = [m for m in messages if m.get("timestamp")]
    timed.sort(key=lambda m: m["timestamp"])

    out_path = out_dir / "timeline.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for m in timed:
            slim = {
                "timestamp":    m["timestamp"],
                "session_id":   m.get("session_id"),
                "thread_id":    m.get("thread_id"),
                "role":         m.get("role"),
                "source":       m.get("source"),
                "text":         (m.get("text") or "")[:200],
                "tool":         m.get("tool"),
                "files_changed": m.get("files_changed") or [],
            }
            fh.write(json.dumps(slim, ensure_ascii=False) + "\n")

    return out_path


# ---------------------------------------------------------------------------
# Lógica principal
# ---------------------------------------------------------------------------

def run_report(
    sessions_path: Path | None = None,
    summaries_path: Path | None = None,
) -> dict[str, Path]:
    sessions_path  = sessions_path  or (OUTPUT_NORMALIZED / "sessions.jsonl")
    summaries_path = summaries_path or (OUTPUT_NORMALIZED / "summaries.jsonl")

    if not sessions_path.exists():
        raise FileNotFoundError(
            f"sessions.jsonl não encontrado: {sessions_path}\n"
            "Execute o normalize primeiro."
        )
    if not summaries_path.exists():
        raise FileNotFoundError(
            f"summaries.jsonl não encontrado: {summaries_path}\n"
            "Execute o normalize primeiro."
        )

    print(f"\n{'='*60}")
    print(f"  REPORT")
    print(f"{'='*60}")

    messages  = _load_sessions(sessions_path)
    summaries = _load_summaries(summaries_path)
    print(f"  Mensagens carregadas : {len(messages)}")
    print(f"  Sessões carregadas   : {len(summaries)}")

    OUTPUT_REPORTS.mkdir(parents=True, exist_ok=True)

    conv_path   = _report_conversations(messages, OUTPUT_REPORTS)
    topics_path = _report_topics(summaries, OUTPUT_REPORTS)
    tool_path   = _report_tool_calls(messages, OUTPUT_REPORTS)
    tl_path     = _report_timeline(messages, OUTPUT_REPORTS)

    print(f"\n  conversations_by_thread.jsonl → {conv_path}")
    print(f"  topics_summary.txt            → {topics_path}")
    print(f"  tool_calls.jsonl              → {tool_path}")
    print(f"  timeline.jsonl                → {tl_path}")
    print(f"{'='*60}\n")

    return {
        "conversations": conv_path,
        "topics":        topics_path,
        "tool_calls":    tool_path,
        "timeline":      tl_path,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report: gera relatórios a partir do modelo canônico normalizado."
    )
    parser.add_argument("--sessions",  type=Path, default=None)
    parser.add_argument("--summaries", type=Path, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_report(sessions_path=args.sessions, summaries_path=args.summaries)
