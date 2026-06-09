"""
01_ingest/ingest.py — Bloco 1: Snapshot dos artefatos do VS Code.

O que faz:
  1. Descobre globalStorage/state.vscdb e todos os arquivos relevantes
     em workspaceStorage/<hash>/.
  2. Copia para output/raw/snapshot_<YYYYMMDD_HHmmss>/ preservando
     a estrutura de subpastas. NUNCA escreve nos originais.
  3. Para cada .vscdb copiado, extrai as chaves de interesse e grava
     um sidecar <nome>.keys.jsonl ao lado do .vscdb na pasta raw.
  4. Grava ingest_manifest.jsonl com metadados da execução.

Uso:
    python pipeline/01_ingest/ingest.py
    python pipeline/01_ingest/ingest.py --snapshot-dir output/raw/snapshot_custom
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Raiz do repositório — necessário para imports de pipeline.*
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline.lib.config import (
    CHAT_EDITING_SESSION_DIR,
    CHAT_SESSION_DIRS,
    CLAUDE_PROJECTS_DIR,
    CODEX_ARCHIVED_SESSIONS_DIR,
    CODEX_SESSION_INDEX,
    CODEX_SESSIONS_DIR,
    EMPTY_WINDOW_CHAT_SESSIONS_DIR,
    GLOBAL_STATE_DB,
    INGEST_FILE_EXTENSIONS,
    KEY_REGEX,
    MAX_CHAT_SESSION_FILE_MB,
    OUTPUT_RAW,
    WORKSPACE_STORAGE_DIR,
)
from pipeline.lib.db_reader import (
    find_workspace_jsonl_files,
    find_workspace_vscdb_files,
    read_vscdb_keys,
)
from pipeline.lib.incremental_state import (
    file_fingerprint,
    load_incremental_state,
    remove_missing_files,
    save_incremental_state,
    upsert_file_state,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
)
_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")


def _copy_file(src: Path, dest: Path) -> bool:
    """Copia src → dest, criando diretórios intermediários. Retorna True se ok."""
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return True
    except Exception as exc:
        _log.warning("Não foi possível copiar %s: %s", src, exc)
        return False


def _cleanup_old_snapshots(raw_dir: Path, keep: int = 2) -> None:
    """
    Remove snapshots antigos de output/raw/, mantendo apenas os `keep` mais recentes.

    Os diretórios são ordenados pelo nome (snapshot_YYYYMMDD_HHMMSS),
    que é lexicograficamente equivalente à ordem cronológica.
    """
    snapshots = sorted(
        [p for p in raw_dir.iterdir() if p.is_dir() and p.name.startswith("snapshot_")],
        reverse=True,  # mais recente primeiro
    )
    to_delete = snapshots[keep:]
    if not to_delete:
        _log.info("Limpeza: nenhum snapshot antigo para remover (total: %d).", len(snapshots))
        return

    print(f"\n[cleanup] Mantendo {keep} snapshot(s) mais recente(s). Removendo {len(to_delete)}:")
    for old in to_delete:
        try:
            shutil.rmtree(old)
            print(f"  🗑  {old.name}")
            _log.info("Snapshot removido: %s", old.name)
        except Exception as exc:
            _log.warning("Falha ao remover snapshot %s: %s", old.name, exc)


def _dump_keys_sidecar(db_copy: Path, key_regex: str) -> Path:
    """
    Lê chaves do .vscdb copiado e grava <db_copy>.keys.jsonl ao lado.
    Retorna o caminho do sidecar.
    """
    sidecar = db_copy.with_suffix(".vscdb.keys.jsonl")
    try:
        keys = read_vscdb_keys(db_copy, key_regex)
    except Exception as exc:
        _log.warning("Falha ao ler chaves de %s: %s", db_copy.name, exc)
        keys = {}

    with sidecar.open("w", encoding="utf-8") as fh:
        for k, v in keys.items():
            fh.write(json.dumps({"key": k, "value": v}, ensure_ascii=False) + "\n")

    _log.info("    → %d chaves → %s", len(keys), sidecar.name)
    return sidecar


def _change_status(
    previous_state: dict,
    source_path: Path,
    fingerprint: dict,
) -> str:
    files = previous_state.get("files", {})
    if not isinstance(files, dict):
        return "new"

    prev = files.get(str(source_path))
    if not isinstance(prev, dict):
        return "new"

    prev_fp = prev.get("fingerprint", {})
    if not isinstance(prev_fp, dict):
        return "changed"

    if (
        prev_fp.get("mtime_ns") == fingerprint.get("mtime_ns")
        and prev_fp.get("size") == fingerprint.get("size")
    ):
        return "unchanged"
    return "changed"


# ---------------------------------------------------------------------------
# Lógica principal
# ---------------------------------------------------------------------------

def run_ingest(snapshot_dir: Path | None = None) -> Path:
    """
    Executa a ingestão completa e retorna o caminho da pasta de snapshot criada.
    """
    ts = _ts_now()
    snapshot_dir = snapshot_dir or (OUTPUT_RAW / f"snapshot_{ts}")
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  INGEST — snapshot: {snapshot_dir.name}")
    print(f"{'='*60}")

    manifest: list[dict] = []
    copied_count = 0
    skipped_count = 0
    state = load_incremental_state()
    seen_paths: set[str] = set()
    changed_count = 0
    unchanged_count = 0
    new_count = 0

    # ------------------------------------------------------------------
    # 1/6. globalStorage/state.vscdb
    # ------------------------------------------------------------------
    print("\n[1/6] globalStorage/state.vscdb")
    if GLOBAL_STATE_DB.exists():
        rel = Path("globalStorage") / "state.vscdb"
        dest = snapshot_dir / rel
        fingerprint = file_fingerprint(GLOBAL_STATE_DB)
        change = _change_status(state, GLOBAL_STATE_DB, fingerprint)
        if _copy_file(GLOBAL_STATE_DB, dest):
            sidecar = _dump_keys_sidecar(dest, KEY_REGEX)
            manifest.append({
                "type": "vscdb",
                "source": str(GLOBAL_STATE_DB),
                "dest": str(dest.relative_to(snapshot_dir)),
                "sidecar": sidecar.name,
                "workspace_hash": None,
                "change": change,
            })
            upsert_file_state(
                state,
                str(GLOBAL_STATE_DB),
                fingerprint=fingerprint,
                file_type="vscdb",
                workspace_hash=None,
                status=change,
            )
            seen_paths.add(str(GLOBAL_STATE_DB))
            if change == "new":
                new_count += 1
            elif change == "unchanged":
                unchanged_count += 1
            else:
                changed_count += 1
            copied_count += 1
    else:
        _log.warning("Não encontrado: %s", GLOBAL_STATE_DB)
        skipped_count += 1

    # ------------------------------------------------------------------
    # 2/6. workspaceStorage — state.vscdb de cada hash
    # ------------------------------------------------------------------
    print("\n[2/6] workspaceStorage — state.vscdb")
    if WORKSPACE_STORAGE_DIR.exists():
        ws_dbs = find_workspace_vscdb_files(WORKSPACE_STORAGE_DIR)
        print(f"  Encontrados: {len(ws_dbs)} workspace(s)")
        for src_db in ws_dbs:
            ws_hash = src_db.parent.name
            rel = Path("workspaceStorage") / ws_hash / "state.vscdb"
            dest = snapshot_dir / rel
            fingerprint = file_fingerprint(src_db)
            change = _change_status(state, src_db, fingerprint)
            if _copy_file(src_db, dest):
                sidecar = _dump_keys_sidecar(dest, KEY_REGEX)
                manifest.append({
                    "type": "vscdb",
                    "source": str(src_db),
                    "dest": str(dest.relative_to(snapshot_dir)),
                    "sidecar": sidecar.name,
                    "workspace_hash": ws_hash,
                    "change": change,
                })
                upsert_file_state(
                    state,
                    str(src_db),
                    fingerprint=fingerprint,
                    file_type="vscdb",
                    workspace_hash=ws_hash,
                    status=change,
                )
                seen_paths.add(str(src_db))
                if change == "new":
                    new_count += 1
                elif change == "unchanged":
                    unchanged_count += 1
                else:
                    changed_count += 1
                copied_count += 1
    else:
        _log.warning("Pasta não encontrada: %s", WORKSPACE_STORAGE_DIR)
        skipped_count += 1

    # ------------------------------------------------------------------
    # 3/6. workspaceStorage — *.jsonl e outros arquivos de interesse (nível direto)
    # ------------------------------------------------------------------
    print("\n[3/6] workspaceStorage — *.jsonl / state.json (nível hash/)")
    if WORKSPACE_STORAGE_DIR.exists():
        for ext in INGEST_FILE_EXTENSIONS - {".vscdb"}:
            files = list(WORKSPACE_STORAGE_DIR.glob(f"*/*{ext}"))
            for src_file in files:
                ws_hash = src_file.parent.name
                rel = Path("workspaceStorage") / ws_hash / src_file.name
                dest = snapshot_dir / rel
                fingerprint = file_fingerprint(src_file)
                change = _change_status(state, src_file, fingerprint)
                if _copy_file(src_file, dest):
                    manifest.append({
                        "type": ext.lstrip("."),
                        "source": str(src_file),
                        "dest": str(dest.relative_to(snapshot_dir)),
                        "sidecar": None,
                        "workspace_hash": ws_hash,
                        "change": change,
                    })
                    upsert_file_state(
                        state,
                        str(src_file),
                        fingerprint=fingerprint,
                        file_type=ext.lstrip("."),
                        workspace_hash=ws_hash,
                        status=change,
                    )
                    seen_paths.add(str(src_file))
                    if change == "new":
                        new_count += 1
                    elif change == "unchanged":
                        unchanged_count += 1
                    else:
                        changed_count += 1
                    copied_count += 1

    # ------------------------------------------------------------------
    # 4/6. workspaceStorage — chatSessions/<uuid>.json e .jsonl
    # ------------------------------------------------------------------
    max_bytes = MAX_CHAT_SESSION_FILE_MB * 1024 * 1024
    print(f"\n[4/6] chatSessions — .json/.jsonl (limite {MAX_CHAT_SESSION_FILE_MB} MB por arquivo)")
    if WORKSPACE_STORAGE_DIR.exists():
        for session_dir_name in CHAT_SESSION_DIRS:
            # Prefere .json (estado final); ignora .jsonl quando .json existe
            seen_ids: set[str] = set()
            for src_file in sorted(WORKSPACE_STORAGE_DIR.glob(f"*/{session_dir_name}/*.json")):
                ws_hash = src_file.parts[-3]
                session_id = src_file.stem
                seen_ids.add(session_id)
                size = src_file.stat().st_size
                fingerprint = file_fingerprint(src_file)
                change = _change_status(state, src_file, fingerprint)
                rel = Path("workspaceStorage") / ws_hash / session_dir_name / src_file.name
                dest = snapshot_dir / rel
                if size > max_bytes:
                    manifest.append({
                        "type": "chat_session_json",
                        "source": str(src_file),
                        "dest": None,
                        "sidecar": None,
                        "workspace_hash": ws_hash,
                        "session_id": session_id,
                        "status": "too_large",
                        "size_mb": round(size / 1024 / 1024, 1),
                        "change": change,
                    })
                    upsert_file_state(
                        state,
                        str(src_file),
                        fingerprint=fingerprint,
                        file_type="chat_session_json",
                        workspace_hash=ws_hash,
                        status="too_large",
                    )
                    seen_paths.add(str(src_file))
                    if change == "new":
                        new_count += 1
                    elif change == "unchanged":
                        unchanged_count += 1
                    else:
                        changed_count += 1
                    skipped_count += 1
                    _log.warning(
                        "[too_large %d MB] %s/%s/%s",
                        size // 1024 // 1024, ws_hash[:8], session_dir_name, src_file.name,
                    )
                    continue
                if _copy_file(src_file, dest):
                    manifest.append({
                        "type": "chat_session_json",
                        "source": str(src_file),
                        "dest": str(dest.relative_to(snapshot_dir)),
                        "sidecar": None,
                        "workspace_hash": ws_hash,
                        "session_id": session_id,
                        "status": "copied",
                        "size_mb": round(size / 1024 / 1024, 1),
                        "change": change,
                    })
                    upsert_file_state(
                        state,
                        str(src_file),
                        fingerprint=fingerprint,
                        file_type="chat_session_json",
                        workspace_hash=ws_hash,
                        status=change,
                    )
                    seen_paths.add(str(src_file))
                    if change == "new":
                        new_count += 1
                    elif change == "unchanged":
                        unchanged_count += 1
                    else:
                        changed_count += 1
                    copied_count += 1

            # Copia .jsonl mesmo quando existe .json correspondente.
            # Sessões ativas podem manter patches mais recentes no .jsonl.
            for src_file in sorted(WORKSPACE_STORAGE_DIR.glob(f"*/{session_dir_name}/*.jsonl")):
                ws_hash = src_file.parts[-3]
                session_id = src_file.stem
                size = src_file.stat().st_size
                fingerprint = file_fingerprint(src_file)
                change = _change_status(state, src_file, fingerprint)
                rel = Path("workspaceStorage") / ws_hash / session_dir_name / src_file.name
                dest = snapshot_dir / rel
                if size > max_bytes:
                    manifest.append({
                        "type": "chat_session_jsonl",
                        "source": str(src_file),
                        "dest": None,
                        "sidecar": None,
                        "workspace_hash": ws_hash,
                        "session_id": session_id,
                        "status": "too_large",
                        "size_mb": round(size / 1024 / 1024, 1),
                        "change": change,
                    })
                    upsert_file_state(
                        state,
                        str(src_file),
                        fingerprint=fingerprint,
                        file_type="chat_session_jsonl",
                        workspace_hash=ws_hash,
                        status="too_large",
                    )
                    seen_paths.add(str(src_file))
                    if change == "new":
                        new_count += 1
                    elif change == "unchanged":
                        unchanged_count += 1
                    else:
                        changed_count += 1
                    skipped_count += 1
                    continue
                if _copy_file(src_file, dest):
                    manifest.append({
                        "type": "chat_session_jsonl",
                        "source": str(src_file),
                        "dest": str(dest.relative_to(snapshot_dir)),
                        "sidecar": None,
                        "workspace_hash": ws_hash,
                        "session_id": session_id,
                        "status": "copied",
                        "size_mb": round(size / 1024 / 1024, 1),
                        "change": change,
                    })
                    upsert_file_state(
                        state,
                        str(src_file),
                        fingerprint=fingerprint,
                        file_type="chat_session_jsonl",
                        workspace_hash=ws_hash,
                        status=change,
                    )
                    seen_paths.add(str(src_file))
                    if change == "new":
                        new_count += 1
                    elif change == "unchanged":
                        unchanged_count += 1
                    else:
                        changed_count += 1
                    copied_count += 1

        total_chat = sum(1 for m in manifest if m.get("type") in ("chat_session_json", "chat_session_jsonl"))
        too_large  = sum(1 for m in manifest if m.get("status") == "too_large")
        print(f"  Total sessões: {total_chat} ({too_large} too_large, lidas da origem)")

    # ------------------------------------------------------------------
    # 5/6. workspaceStorage — chatEditingSessions/<uuid>/state.json
    # ------------------------------------------------------------------
    print(f"\n[5/6] {CHAT_EDITING_SESSION_DIR}/<uuid>/state.json")
    if WORKSPACE_STORAGE_DIR.exists():
        editing_count = 0
        editing_too_large = 0
        for src_file in sorted(WORKSPACE_STORAGE_DIR.glob(f"*/{CHAT_EDITING_SESSION_DIR}/*/state.json")):
            ws_hash = src_file.parts[-4]
            session_id = src_file.parent.name
            size = src_file.stat().st_size
            fingerprint = file_fingerprint(src_file)
            change = _change_status(state, src_file, fingerprint)
            rel = Path("workspaceStorage") / ws_hash / CHAT_EDITING_SESSION_DIR / session_id / src_file.name
            dest = snapshot_dir / rel
            if size > max_bytes:
                manifest.append({
                    "type": "chat_editing_state",
                    "source": str(src_file),
                    "dest": None,
                    "sidecar": None,
                    "workspace_hash": ws_hash,
                    "session_id": session_id,
                    "status": "too_large",
                    "size_mb": round(size / 1024 / 1024, 1),
                    "change": change,
                })
                upsert_file_state(
                    state,
                    str(src_file),
                    fingerprint=fingerprint,
                    file_type="chat_editing_state",
                    workspace_hash=ws_hash,
                    status="too_large",
                )
                seen_paths.add(str(src_file))
                if change == "new":
                    new_count += 1
                elif change == "unchanged":
                    unchanged_count += 1
                else:
                    changed_count += 1
                editing_too_large += 1
                skipped_count += 1
                continue
            if _copy_file(src_file, dest):
                manifest.append({
                    "type": "chat_editing_state",
                    "source": str(src_file),
                    "dest": str(dest.relative_to(snapshot_dir)),
                    "sidecar": None,
                    "workspace_hash": ws_hash,
                    "session_id": session_id,
                    "status": "copied",
                    "size_mb": round(size / 1024 / 1024, 1),
                    "change": change,
                })
                upsert_file_state(
                    state,
                    str(src_file),
                    fingerprint=fingerprint,
                    file_type="chat_editing_state",
                    workspace_hash=ws_hash,
                    status=change,
                )
                seen_paths.add(str(src_file))
                if change == "new":
                    new_count += 1
                elif change == "unchanged":
                    unchanged_count += 1
                else:
                    changed_count += 1
                editing_count += 1
                copied_count += 1
        print(f"  Total edit sessions: {editing_count} ({editing_too_large} too_large, lidas da origem)")

    # ------------------------------------------------------------------
    # 6/6. globalStorage/emptyWindowChatSessions — sessões sem workspace
    # ------------------------------------------------------------------
    print(f"\n[6/6] globalStorage/emptyWindowChatSessions")
    if EMPTY_WINDOW_CHAT_SESSIONS_DIR.exists():
        ew_seen_ids: set[str] = set()
        for src_file in sorted(EMPTY_WINDOW_CHAT_SESSIONS_DIR.glob("*.json")):
            session_id = src_file.stem
            ew_seen_ids.add(session_id)
            size = src_file.stat().st_size
            fingerprint = file_fingerprint(src_file)
            change = _change_status(state, src_file, fingerprint)
            rel = Path("globalStorage") / "emptyWindowChatSessions" / src_file.name
            dest = snapshot_dir / rel
            if size > max_bytes:
                manifest.append({
                    "type": "chat_session_json",
                    "source": str(src_file),
                    "dest": None,
                    "sidecar": None,
                    "workspace_hash": None,
                    "session_id": session_id,
                    "status": "too_large",
                    "size_mb": round(size / 1024 / 1024, 1),
                    "change": change,
                })
                upsert_file_state(
                    state,
                    str(src_file),
                    fingerprint=fingerprint,
                    file_type="chat_session_json",
                    workspace_hash=None,
                    status="too_large",
                )
                seen_paths.add(str(src_file))
                if change == "new":
                    new_count += 1
                elif change == "unchanged":
                    unchanged_count += 1
                else:
                    changed_count += 1
                skipped_count += 1
                _log.warning("[too_large %d MB] emptyWindowChatSessions/%s", size // 1024 // 1024, src_file.name)
                continue
            if _copy_file(src_file, dest):
                manifest.append({
                    "type": "chat_session_json",
                    "source": str(src_file),
                    "dest": str(dest.relative_to(snapshot_dir)),
                    "sidecar": None,
                    "workspace_hash": None,
                    "session_id": session_id,
                    "status": "copied",
                    "size_mb": round(size / 1024 / 1024, 1),
                    "change": change,
                })
                upsert_file_state(
                    state,
                    str(src_file),
                    fingerprint=fingerprint,
                    file_type="chat_session_json",
                    workspace_hash=None,
                    status=change,
                )
                seen_paths.add(str(src_file))
                if change == "new":
                    new_count += 1
                elif change == "unchanged":
                    unchanged_count += 1
                else:
                    changed_count += 1
                copied_count += 1

        for src_file in sorted(EMPTY_WINDOW_CHAT_SESSIONS_DIR.glob("*.jsonl")):
            session_id = src_file.stem
            size = src_file.stat().st_size
            fingerprint = file_fingerprint(src_file)
            change = _change_status(state, src_file, fingerprint)
            rel = Path("globalStorage") / "emptyWindowChatSessions" / src_file.name
            dest = snapshot_dir / rel
            if size > max_bytes:
                manifest.append({
                    "type": "chat_session_jsonl",
                    "source": str(src_file),
                    "dest": None,
                    "sidecar": None,
                    "workspace_hash": None,
                    "session_id": session_id,
                    "status": "too_large",
                    "size_mb": round(size / 1024 / 1024, 1),
                    "change": change,
                })
                upsert_file_state(
                    state,
                    str(src_file),
                    fingerprint=fingerprint,
                    file_type="chat_session_jsonl",
                    workspace_hash=None,
                    status="too_large",
                )
                seen_paths.add(str(src_file))
                if change == "new":
                    new_count += 1
                elif change == "unchanged":
                    unchanged_count += 1
                else:
                    changed_count += 1
                skipped_count += 1
                _log.warning("[too_large %d MB] emptyWindowChatSessions/%s", size // 1024 // 1024, src_file.name)
                continue
            if _copy_file(src_file, dest):
                manifest.append({
                    "type": "chat_session_jsonl",
                    "source": str(src_file),
                    "dest": str(dest.relative_to(snapshot_dir)),
                    "sidecar": None,
                    "workspace_hash": None,
                    "session_id": session_id,
                    "status": "copied",
                    "size_mb": round(size / 1024 / 1024, 1),
                    "change": change,
                })
                upsert_file_state(
                    state,
                    str(src_file),
                    fingerprint=fingerprint,
                    file_type="chat_session_jsonl",
                    workspace_hash=None,
                    status=change,
                )
                seen_paths.add(str(src_file))
                if change == "new":
                    new_count += 1
                elif change == "unchanged":
                    unchanged_count += 1
                else:
                    changed_count += 1
                copied_count += 1

        ew_total = sum(
            1 for m in manifest
            if m.get("workspace_hash") is None and m.get("type") in ("chat_session_json", "chat_session_jsonl")
            and "emptyWindowChatSessions" in (m.get("source") or "")
        )
        print(f"  Total sessões (janela vazia): {ew_total}")
    else:
        _log.info("emptyWindowChatSessions não encontrado em globalStorage — ignorado")

    # ------------------------------------------------------------------
    # 6/6. ~/.codex/sessions — sessões do Codex CLI / extensão openai.chatgpt
    # ------------------------------------------------------------------
    print(f"\n[6/6] ~/.codex/sessions — sessões Codex")
    if CODEX_SESSIONS_DIR.exists():
        codex_files = sorted(CODEX_SESSIONS_DIR.rglob("*.jsonl"))
        print(f"  Encontrados: {len(codex_files)} arquivo(s)")
        for src_file in codex_files:
            # Extrai UUID da sessão do nome do arquivo (rollout-<date>-<uuid>.jsonl)
            session_id = src_file.stem
            m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$",
                          src_file.stem, re.IGNORECASE)
            if m:
                session_id = m.group(1)
            # Preserva a hierarquia year/month/day/
            try:
                rel_to_sessions = src_file.relative_to(CODEX_SESSIONS_DIR)
            except ValueError:
                rel_to_sessions = Path(src_file.name)
            rel = Path("codex_sessions") / rel_to_sessions
            dest = snapshot_dir / rel
            size = src_file.stat().st_size
            fingerprint = file_fingerprint(src_file)
            change = _change_status(state, src_file, fingerprint)
            if _copy_file(src_file, dest):
                manifest.append({
                    "type": "codex_session",
                    "source": str(src_file),
                    "dest": str(dest.relative_to(snapshot_dir)),
                    "sidecar": None,
                    "workspace_hash": None,
                    "session_id": session_id,
                    "status": "copied",
                    "size_mb": round(size / 1024 / 1024, 3),
                    "change": change,
                })
                upsert_file_state(
                    state,
                    str(src_file),
                    fingerprint=fingerprint,
                    file_type="codex_session",
                    workspace_hash=None,
                    status=change,
                )
                seen_paths.add(str(src_file))
                if change == "new":
                    new_count += 1
                elif change == "unchanged":
                    unchanged_count += 1
                else:
                    changed_count += 1
                copied_count += 1
        # Também ingere archived_sessions/ (sessões arquivadas pelo Codex)
        archived_files = sorted(CODEX_ARCHIVED_SESSIONS_DIR.rglob("*.jsonl")) if CODEX_ARCHIVED_SESSIONS_DIR.exists() else []
        if archived_files:
            print(f"  Arquivadas: {len(archived_files)} arquivo(s)")
        for src_file in archived_files:
            session_id = src_file.stem
            m2 = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$",
                           src_file.stem, re.IGNORECASE)
            if m2:
                session_id = m2.group(1)
            rel = Path("codex_sessions") / "archived" / src_file.name
            dest = snapshot_dir / rel
            size = src_file.stat().st_size
            fingerprint = file_fingerprint(src_file)
            change = _change_status(state, src_file, fingerprint)
            if _copy_file(src_file, dest):
                manifest.append({
                    "type": "codex_session",
                    "source": str(src_file),
                    "dest": str(dest.relative_to(snapshot_dir)),
                    "sidecar": None,
                    "workspace_hash": None,
                    "session_id": session_id,
                    "status": "copied",
                    "size_mb": round(size / 1024 / 1024, 3),
                    "change": change,
                })
                upsert_file_state(
                    state,
                    str(src_file),
                    fingerprint=fingerprint,
                    file_type="codex_session",
                    workspace_hash=None,
                    status=change,
                )
                seen_paths.add(str(src_file))
                if change == "new":
                    new_count += 1
                elif change == "unchanged":
                    unchanged_count += 1
                else:
                    changed_count += 1
                copied_count += 1

        # Copia session_index.jsonl (títulos AI-generated por sessão)
        if CODEX_SESSION_INDEX.exists():
            dest_idx = snapshot_dir / "codex_sessions" / "session_index.jsonl"
            _copy_file(CODEX_SESSION_INDEX, dest_idx)

        codex_total = sum(1 for m in manifest if m.get("type") == "codex_session")
        print(f"  Total sessões Codex: {codex_total}")
    else:
        _log.info("~/.codex/sessions não encontrado — extensão Codex não instalada ou sem sessões")

    # ------------------------------------------------------------------
    # 7/7. ~/.claude/projects — sessões do Claude Code CLI
    # ------------------------------------------------------------------
    print(f"\n[7/7] ~/.claude/projects — sessões Claude Code")
    if CLAUDE_PROJECTS_DIR.exists():
        claude_files: list[Path] = []
        for project_dir in sorted(CLAUDE_PROJECTS_DIR.iterdir()):
            if not project_dir.is_dir():
                continue
            # Apenas filhos directos do dir de projeto (não sub-dirs de subagentes)
            for src_file in sorted(project_dir.glob("*.jsonl")):
                claude_files.append(src_file)
        print(f"  Encontrados: {len(claude_files)} arquivo(s)")
        for src_file in claude_files:
            project_slug = src_file.parent.name
            session_id = src_file.stem
            rel = Path("claude_code") / project_slug / src_file.name
            dest = snapshot_dir / rel
            size = src_file.stat().st_size
            fingerprint = file_fingerprint(src_file)
            change = _change_status(state, src_file, fingerprint)
            if _copy_file(src_file, dest):
                manifest.append({
                    "type": "claude_code_session",
                    "source": str(src_file),
                    "dest": str(dest.relative_to(snapshot_dir)),
                    "sidecar": None,
                    "workspace_hash": None,
                    "session_id": session_id,
                    "status": "copied",
                    "size_mb": round(size / 1024 / 1024, 3),
                    "change": change,
                })
                upsert_file_state(
                    state,
                    str(src_file),
                    fingerprint=fingerprint,
                    file_type="claude_code_session",
                    workspace_hash=None,
                    status=change,
                )
                seen_paths.add(str(src_file))
                if change == "new":
                    new_count += 1
                elif change == "changed":
                    changed_count += 1
                else:
                    unchanged_count += 1
                copied_count += 1

        claude_total = sum(1 for m in manifest if m.get("type") == "claude_code_session")
        print(f"  Total sessões Claude Code: {claude_total}")
    else:
        _log.info("~/.claude/projects não encontrado — Claude Code CLI não instalado ou sem sessões")

    # ------------------------------------------------------------------
    # Grava manifesto
    # ------------------------------------------------------------------
    manifest_path = snapshot_dir / "ingest_manifest.jsonl"
    meta = {
        "event": "ingest_run",
        "snapshot_dir": str(snapshot_dir),
        "ts_utc": datetime.now(tz=timezone.utc).isoformat(),
        "files_copied": copied_count,
        "files_skipped": skipped_count,
        "files_new": new_count,
        "files_changed": changed_count,
        "files_unchanged": unchanged_count,
    }
    with manifest_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for entry in manifest:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    removed_paths = remove_missing_files(state, seen_paths)
    save_incremental_state(state)

    # ------------------------------------------------------------------
    # Limpeza de snapshots antigos (mantém atual + anterior)
    # ------------------------------------------------------------------
    _cleanup_old_snapshots(OUTPUT_RAW, keep=2)

    print(f"\n{'='*60}")
    print(f"  Copiados : {copied_count}")
    print(f"  Ignorados: {skipped_count}")
    print(f"  Novos    : {new_count}")
    print(f"  Alterados: {changed_count}")
    print(f"  Iguais   : {unchanged_count}")
    print(f"  Removidos: {len(removed_paths)}")
    print(f"  Manifesto: {manifest_path}")
    print(f"{'='*60}\n")

    return snapshot_dir


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingestão: snapshot dos artefatos do VS Code para output/raw/"
    )
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=None,
        help="Pasta de destino do snapshot (padrão: output/raw/snapshot_<ts>)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_ingest(snapshot_dir=args.snapshot_dir)
