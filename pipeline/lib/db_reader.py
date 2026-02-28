"""
db_reader.py — Leitura segura de arquivos SQLite e JSONL do VS Code.

Regras de segurança:
  - SQLite sempre aberto com URI mode=ro (read-only).
  - Nenhuma escrita nos arquivos de origem.
  - Conexões fechadas explicitamente pelo caller (context manager).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Generator

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQLite — leitura de chaves
# ---------------------------------------------------------------------------

def open_vscdb_readonly(db_path: Path) -> sqlite3.Connection:
    """
    Abre um state.vscdb em modo read-only via URI.
    Retorna uma Connection; caller deve fechar com .close() ou usar 'with'.
    Levanta FileNotFoundError se o arquivo não existir.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"DB não encontrado: {db_path}")

    uri = db_path.as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def read_vscdb_keys(db_path: Path, key_regex: str) -> dict[str, str]:
    """
    Lê todas as linhas de ItemTable cujo key bata com key_regex.

    Retorna dict { key: value_as_str }.
    Valores bytes são decodificados como UTF-8 (replace).
    """
    rx = re.compile(key_regex)
    result: dict[str, str] = {}

    conn = open_vscdb_readonly(db_path)
    try:
        cur = conn.cursor()
        for row in cur.execute("SELECT key, value FROM ItemTable"):
            key: str = row["key"]
            if not rx.search(key):
                continue
            val = row["value"]
            if val is None:
                result[key] = ""
            elif isinstance(val, bytes):
                result[key] = val.decode("utf-8", "replace")
            else:
                result[key] = str(val)
    finally:
        conn.close()

    return result


# ---------------------------------------------------------------------------
# JSONL — leitura linha a linha
# ---------------------------------------------------------------------------

def iter_jsonl(path: Path) -> Generator[dict, None, None]:
    """
    Itera sobre linhas de um arquivo JSONL, ignorando linhas vazias e
    linhas que não sejam JSON válido (loga e continua).
    """
    with path.open(encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError as exc:
                _log.warning("JSONL parse error em %s:%d — %s", path, lineno, exc)


def read_jsonl(path: Path) -> list[dict]:
    """Carrega todo o JSONL em memória. Conveniente para arquivos pequenos."""
    return list(iter_jsonl(path))


# ---------------------------------------------------------------------------
# Descoberta de workspaceStorage
# ---------------------------------------------------------------------------

def find_workspace_vscdb_files(workspace_storage_dir: Path) -> list[Path]:
    """
    Retorna todos os state.vscdb encontrados em workspaceStorage/<hash>/.
    Ordena por data de modificação (mais recente primeiro).
    """
    files = list(workspace_storage_dir.glob("*/state.vscdb"))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def find_workspace_jsonl_files(workspace_storage_dir: Path) -> list[Path]:
    """
    Retorna todos os *.jsonl encontrados em workspaceStorage/<hash>/.
    Ordena por data de modificação (mais recente primeiro).
    """
    files = list(workspace_storage_dir.glob("*/*.jsonl"))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files
