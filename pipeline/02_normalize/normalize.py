"""
02_normalize/normalize.py — Bloco 2: Orquestração da normalização.

O que faz:
  1. Localiza o snapshot mais recente em output/raw/ (ou aceita caminho via arg).
  2. Processa sidecars .keys.jsonl, *.jsonl de workspace e chatSessions/*.json/.jsonl.
  3. Delega parsing para parsers.py e reconstrução de patches para pipeline.lib.patch.
  4. Agrega summaries via aggregator.py.
  5. Emite:
       output/normalized/sessions.jsonl   — uma linha por ChatMessage
       output/normalized/summaries.jsonl  — uma linha por SessionSummary

Uso:
    python pipeline/02_normalize/normalize.py
    python pipeline/02_normalize/normalize.py --snapshot-dir output/raw/snapshot_20260222_120000
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# Raiz do repositório — necessário para imports de pipeline.*
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Adiciona o diretório do normalize ao path para importar sub-módulos locais
_NORMALIZE_DIR = Path(__file__).resolve().parent
if str(_NORMALIZE_DIR) not in sys.path:
    sys.path.insert(0, str(_NORMALIZE_DIR))

from pipeline.lib.config import (
    OUTPUT_NORMALIZED,
    OUTPUT_NORMALIZED_MESSAGE_SHARDS,
    OUTPUT_NORMALIZED_SUMMARY_SHARDS,
    OUTPUT_RAW,
)
from pipeline.lib.db_reader import iter_jsonl
from pipeline.lib.models import ChatMessage, SessionSummary

# Sub-módulos do normalize (importados via sys.path do diretório local)
from parsers import (
    parse_keys_sidecar,
    parse_copilot_jsonl_file,
    parse_chat_editing_state,
    parse_chat_session_json,
    parse_chat_session_jsonl,
    parse_codex_session_jsonl,
    parse_claude_code_session,
)
from aggregator import build_summaries, _build_ws_path_to_hash, _normalize_cwd


# Bump when parser logic or ChatMessage/SessionSummary serialization changes.
_SHARD_SCHEMA_VERSION = "4"


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

_CLI_SOURCES = {"codex_session", "claude_code_session"}


def _codex_workspace_fixup(
    messages: list[ChatMessage], summaries: list[SessionSummary]
) -> None:
    """Preenche workspace_hash para sessões CLI cujo cwd ainda não foi resolvido.

    Necessário porque shards reutilizados do cache não chamam build_summaries
    novamente, portanto qualquer lógica nova no aggregator só afeta shards novos.
    Este pós-passo roda sempre e corrige summaries na memória antes de escrever
    summaries.jsonl.
    """
    ws_path_to_hash = _build_ws_path_to_hash()
    if not ws_path_to_hash:
        return

    # Extrai cwd de mensagens system session_workspace por session_id
    cwd_by_session: dict[str, str] = {}
    for m in messages:
        if (
            m.source in _CLI_SOURCES
            and m.role == "system"
            and m.text
            and m.session_id not in cwd_by_session
        ):
            try:
                meta = json.loads(m.text)
                if meta.get("_type") == "session_workspace":
                    cwd = meta.get("cwd") or ""
                    if cwd:
                        cwd_by_session[m.session_id] = cwd
            except (json.JSONDecodeError, AttributeError):
                pass

    if not cwd_by_session:
        return

    fixed = 0
    for s in summaries:
        if s.source not in _CLI_SOURCES or s.workspace_hash:
            continue
        cwd = cwd_by_session.get(s.session_id or "") or ""
        if not cwd:
            continue
        normalized = _normalize_cwd(cwd)
        ws_hash = ws_path_to_hash.get(normalized.lower())
        if ws_hash:
            s.workspace_hash = ws_hash
            fixed += 1

    if fixed:
        print(f"  [cli-ws-fixup] {fixed} sessão(ões) CLI vinculadas a workspace.")


def _latest_snapshot(raw_dir: Path) -> Path | None:
    snapshots = sorted(raw_dir.glob("snapshot_*"), reverse=True)
    return snapshots[0] if snapshots else None


def _manifest_entries(snapshot_dir: Path) -> list[dict]:
    manifest_path = snapshot_dir / "ingest_manifest.jsonl"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifesto do ingest não encontrado: {manifest_path}")
    return list(iter_jsonl(manifest_path))


def _shard_key(source_path: str, file_type: str) -> str:
    raw = f"v{_SHARD_SCHEMA_VERSION}:{file_type}:{source_path}".encode("utf-8", errors="replace")
    return hashlib.sha1(raw).hexdigest()


def _message_shard_path(shard_key: str) -> Path:
    return OUTPUT_NORMALIZED_MESSAGE_SHARDS / f"{shard_key}.jsonl"


def _summary_shard_path(shard_key: str) -> Path:
    return OUTPUT_NORMALIZED_SUMMARY_SHARDS / f"{shard_key}.jsonl"


def _write_message_shard(path: Path, messages: list[ChatMessage]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for message in messages:
            fh.write(message.to_jsonl_line() + "\n")


def _write_summary_shard(path: Path, summaries: list[SessionSummary]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for summary in summaries:
            fh.write(summary.to_jsonl_line() + "\n")


def _load_message_shard(path: Path) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    for row in iter_jsonl(path):
        messages.append(ChatMessage(**row))
    return messages


def _load_summary_shard(path: Path) -> list[SessionSummary]:
    summaries: list[SessionSummary] = []
    for row in iter_jsonl(path):
        summaries.append(SessionSummary(**row))
    return summaries


def _remove_stale_shards(valid_keys: set[str]) -> int:
    removed = 0
    for folder in (OUTPUT_NORMALIZED_MESSAGE_SHARDS, OUTPUT_NORMALIZED_SUMMARY_SHARDS):
        if not folder.exists():
            continue
        for shard in folder.glob("*.jsonl"):
            if shard.stem in valid_keys:
                continue
            shard.unlink(missing_ok=True)
            removed += 1
    return removed


def _collect_normalize_targets(snapshot_dir: Path) -> list[dict]:
    entries = _manifest_entries(snapshot_dir)
    targets: list[dict] = []
    allowed_types = {
        "vscdb",
        "jsonl",
        "chat_session_json",
        "chat_session_jsonl",
        "chat_editing_state",
        "codex_session",
        "claude_code_session",
    }
    for entry in entries:
        if entry.get("event") == "ingest_run":
            continue
        file_type = entry.get("type")
        source_path = entry.get("source")
        if not file_type or not source_path or file_type not in allowed_types:
            continue
        change = entry.get("change") or "new"
        if file_type == "vscdb":
            rel_dest = entry.get("dest")
            if not rel_dest:
                continue
            rel_path = Path(rel_dest)
            raw_path = snapshot_dir / rel_path
            parse_type = "keys_sidecar"
            parse_path = raw_path.with_suffix(".vscdb.keys.jsonl")
        elif entry.get("status") == "too_large":
            parse_type = file_type
            parse_path = Path(source_path)
        else:
            rel_dest = entry.get("dest")
            if not rel_dest:
                continue
            parse_type = file_type
            parse_path = snapshot_dir / Path(rel_dest)

        targets.append({
            "source_path": source_path,
            "file_type": file_type,
            "parse_type": parse_type,
            "parse_path": parse_path,
            "workspace_hash": entry.get("workspace_hash"),
            "change": change,
        })
    return targets


def _parse_target(target: dict) -> list[ChatMessage]:
    parse_type = target["parse_type"]
    parse_path: Path = target["parse_path"]
    ws_hash = target.get("workspace_hash")

    if parse_type == "keys_sidecar":
        sidecar_ws_hash = parse_path.parent.name if "workspaceStorage" in str(parse_path) else None
        return parse_keys_sidecar(parse_path, sidecar_ws_hash)
    if parse_type == "jsonl":
        return parse_copilot_jsonl_file(parse_path, ws_hash or "")
    if parse_type == "chat_session_json":
        return parse_chat_session_json(parse_path, ws_hash or "")
    if parse_type == "chat_session_jsonl":
        return parse_chat_session_jsonl(parse_path, ws_hash or "")
    if parse_type == "chat_editing_state":
        return parse_chat_editing_state(parse_path, ws_hash or "")
    if parse_type == "codex_session":
        return parse_codex_session_jsonl(parse_path)
    if parse_type == "claude_code_session":
        return parse_claude_code_session(parse_path)
    return []


# ---------------------------------------------------------------------------
# Lógica principal
# ---------------------------------------------------------------------------

def run_normalize(snapshot_dir: Path | None = None) -> tuple[Path, Path]:
    """
    Normaliza o snapshot indicado (ou o mais recente).
    Retorna (sessions_path, summaries_path).
    """
    if snapshot_dir is None:
        snapshot_dir = _latest_snapshot(OUTPUT_RAW)
    if snapshot_dir is None or not snapshot_dir.exists():
        raise FileNotFoundError(
            "Nenhum snapshot encontrado em output/raw/. Execute o ingest primeiro."
        )

    print(f"\n{'='*60}")
    print(f"  NORMALIZE — snapshot: {snapshot_dir.name}")
    print(f"{'='*60}")

    OUTPUT_NORMALIZED.mkdir(parents=True, exist_ok=True)
    OUTPUT_NORMALIZED_MESSAGE_SHARDS.mkdir(parents=True, exist_ok=True)
    OUTPUT_NORMALIZED_SUMMARY_SHARDS.mkdir(parents=True, exist_ok=True)

    targets = _collect_normalize_targets(snapshot_dir)
    valid_keys = {
        _shard_key(target["source_path"], target["file_type"])
        for target in targets
    }

    print(f"\n[1/3] Alvos do manifesto: {len(targets)}")

    all_messages: list[ChatMessage] = []
    all_summaries: list[SessionSummary] = []
    processed_count = 0
    reused_count = 0
    reparsed_count = 0

    for target in targets:
        shard_key = _shard_key(target["source_path"], target["file_type"])
        message_shard = _message_shard_path(shard_key)
        summary_shard = _summary_shard_path(shard_key)

        reuse_shard = (
            target.get("change") == "unchanged"
            and message_shard.exists()
            and summary_shard.exists()
        )

        if reuse_shard:
            shard_messages = _load_message_shard(message_shard)
            shard_summaries = _load_summary_shard(summary_shard)
            reused_count += 1
        else:
            shard_messages = _parse_target(target)
            shard_summaries = build_summaries(shard_messages)
            _write_message_shard(message_shard, shard_messages)
            _write_summary_shard(summary_shard, shard_summaries)
            reparsed_count += 1

        processed_count += 1
        all_messages.extend(shard_messages)
        all_summaries.extend(shard_summaries)

    removed_shards = _remove_stale_shards(valid_keys)

    # ------------------------------------------------------------------
    # Pós-passo: preenche workspace_hash para sessões Codex via cwd lookup
    # (necessário porque shards reutilizados não chamam build_summaries novamente)
    # ------------------------------------------------------------------
    _codex_workspace_fixup(all_messages, all_summaries)

    # ------------------------------------------------------------------
    # Gravar saídas
    # ------------------------------------------------------------------
    sessions_path = OUTPUT_NORMALIZED / "sessions.jsonl"
    with sessions_path.open("w", encoding="utf-8") as fh:
        for m in all_messages:
            fh.write(m.to_jsonl_line() + "\n")

    summaries_path = OUTPUT_NORMALIZED / "summaries.jsonl"
    with summaries_path.open("w", encoding="utf-8") as fh:
        for s in all_summaries:
            fh.write(s.to_jsonl_line() + "\n")

    print(f"\n{'='*60}")
    print(f"  Alvos processados      : {processed_count}")
    print(f"  Shards reutilizados    : {reused_count}")
    print(f"  Shards reprocessados   : {reparsed_count}")
    print(f"  Shards removidos       : {removed_shards}")
    print(f"  Mensagens normalizadas : {len(all_messages)}")
    print(f"  Sessões (summaries)    : {len(all_summaries)}")
    print(f"  sessions.jsonl   -> {sessions_path}")
    print(f"  summaries.jsonl  -> {summaries_path}")
    print(f"{'='*60}\n")

    return sessions_path, summaries_path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalização: converte raw snapshot para modelo canônico."
    )
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=None,
        help="Pasta do snapshot (padrão: mais recente em output/raw/)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_normalize(snapshot_dir=args.snapshot_dir)
