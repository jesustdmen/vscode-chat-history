"""
patch.py — Reconstrução de estado de sessões chatSessions a partir de patches JSONL.

Formato dos patches:
  kind=0  v=dict   → estado base (snapshot completo)
  kind=1  k=path   v=scalar → base[path] = value
  kind=2  k=path   v=list   → base[path].extend(items)

Suporta caminhos mistos dict/lista: ex. ['requests', 0, 'response'].
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Navegação de caminhos mistos dict/lista
# ---------------------------------------------------------------------------

def _set_nested(obj: dict, path: list, value: object) -> None:
    """
    Define value em obj navegando pelo path.
    Suporta caminhos mistos dict/lista: ex. ['requests', 0, 'response'].
    """
    if not path:
        return
    node = obj
    for i, key in enumerate(path[:-1]):
        next_key = path[i + 1]
        if isinstance(node, dict):
            str_key = str(key)
            if str_key not in node:
                node[str_key] = [] if isinstance(next_key, int) else {}
            node = node[str_key]
        elif isinstance(node, list):
            try:
                idx = int(key)
                if 0 <= idx < len(node):
                    node = node[idx]
                else:
                    return
            except (ValueError, TypeError):
                return
        else:
            return
    last = path[-1]
    if isinstance(node, dict):
        node[str(last)] = value
    elif isinstance(node, list):
        try:
            idx = int(last)
            if 0 <= idx < len(node):
                node[idx] = value
        except (ValueError, TypeError):
            pass


def _extend_nested(obj: dict, path: list, items: list) -> None:
    """
    Extende a lista em obj[path] com items.
    Suporta caminhos mistos dict/lista: ex. ['requests', 0, 'response'].
    """
    if not path:
        return
    node = obj
    for i, key in enumerate(path[:-1]):
        if isinstance(node, dict):
            str_key = str(key)
            if str_key not in node:
                next_key = path[i + 1]
                node[str_key] = [] if isinstance(next_key, int) else {}
            node = node[str_key]
        elif isinstance(node, list):
            try:
                idx = int(key)
                if 0 <= idx < len(node):
                    node = node[idx]
                else:
                    return
            except (ValueError, TypeError):
                return
        else:
            return
    last = path[-1]
    if isinstance(node, dict):
        existing = node.setdefault(str(last), [])
        if isinstance(existing, list):
            existing.extend(items)
    elif isinstance(node, list):
        try:
            idx = int(last)
            if 0 <= idx < len(node) and isinstance(node[idx], list):
                node[idx].extend(items)
        except (ValueError, TypeError):
            pass


# ---------------------------------------------------------------------------
# Reconstrução de estado final
# ---------------------------------------------------------------------------

def reconstruct_chat_session_jsonl(path: Path) -> dict | None:
    """
    Reconstrói o estado final de uma sessão chatSessions a partir de .jsonl.

    Aplica patches em ordem:
      kind=0  v=dict   → substitui a base inteira
      kind=1  k=path   v=scalar → set_nested(base, path, value)
      kind=2  k=path   v=list   → extend_nested(base, path, items)

    Retorna o dict final ou None se o arquivo estiver vazio/inválido.
    """
    try:
        lines = path.read_bytes().decode("utf-8", errors="replace").splitlines()
    except Exception as exc:
        _log.warning("Falha ao ler %s: %s", path, exc)
        return None

    base: dict = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = obj.get("kind")
        if kind == 0:
            v = obj.get("v")
            if isinstance(v, dict):
                base = v
        elif kind == 1:
            k = obj.get("k")
            v = obj.get("v")
            if isinstance(k, list) and k:
                _set_nested(base, k, v)
        elif kind == 2:
            k = obj.get("k")
            v = obj.get("v")
            if isinstance(k, list) and k and isinstance(v, list):
                _extend_nested(base, k, v)

    return base if base else None
