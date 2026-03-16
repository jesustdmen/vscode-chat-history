"""
incremental_state.py — Infraestrutura de estado incremental do pipeline.

Esta etapa não altera o comportamento do pipeline. O objetivo é fornecer
um armazenamento local simples, versionado e auditável para futuras
decisões incrementais no ingest/normalize.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.lib.config import (
    INCREMENTAL_INDEX_FILE,
    INCREMENTAL_STATE_SCHEMA_VERSION,
)


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def file_fingerprint(path: Path) -> dict[str, Any]:
    """
    Gera uma fingerprint leve baseada em metadados do arquivo.

    Nesta primeira etapa usamos apenas `mtime_ns` e `size`, que são baratos
    e suficientes para a maioria dos casos de sincronização incremental.
    """
    stat = path.stat()
    return {
        "path": str(path),
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
    }


def default_incremental_state() -> dict[str, Any]:
    return {
        "schema_version": INCREMENTAL_STATE_SCHEMA_VERSION,
        "updated_at": None,
        "files": {},
    }


def load_incremental_state(path: Path | None = None) -> dict[str, Any]:
    state_path = path or INCREMENTAL_INDEX_FILE
    if not state_path.exists():
        return default_incremental_state()

    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_incremental_state()

    if not isinstance(data, dict):
        return default_incremental_state()

    if data.get("schema_version") != INCREMENTAL_STATE_SCHEMA_VERSION:
        return default_incremental_state()

    files = data.get("files")
    if not isinstance(files, dict):
        data["files"] = {}

    if "updated_at" not in data:
        data["updated_at"] = None

    return data


def save_incremental_state(state: dict[str, Any], path: Path | None = None) -> Path:
    state_path = path or INCREMENTAL_INDEX_FILE
    payload = {
        "schema_version": INCREMENTAL_STATE_SCHEMA_VERSION,
        "updated_at": utc_now_iso(),
        "files": state.get("files", {}) if isinstance(state, dict) else {},
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return state_path


def upsert_file_state(
    state: dict[str, Any],
    source_path: str,
    *,
    fingerprint: dict[str, Any],
    file_type: str,
    workspace_hash: str | None = None,
    status: str = "tracked",
    normalized_artifact: str | None = None,
) -> dict[str, Any]:
    files = state.setdefault("files", {})
    if not isinstance(files, dict):
        files = {}
        state["files"] = files

    entry: dict[str, Any] = {
        "path": source_path,
        "file_type": file_type,
        "workspace_hash": workspace_hash,
        "status": status,
        "fingerprint": fingerprint,
    }
    if normalized_artifact:
        entry["normalized_artifact"] = normalized_artifact

    files[source_path] = entry
    return entry


def remove_missing_files(
    state: dict[str, Any],
    existing_paths: set[str],
) -> list[str]:
    files = state.get("files", {})
    if not isinstance(files, dict):
        state["files"] = {}
        return []

    removed = [path for path in files.keys() if path not in existing_paths]
    for path in removed:
        files.pop(path, None)
    return removed
