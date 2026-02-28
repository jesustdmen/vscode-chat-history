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
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Raiz do repositório — necessário para imports de pipeline.*
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline.lib.config import (
    CHAT_SESSION_DIRS,
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

    # ------------------------------------------------------------------
    # 1/4. globalStorage/state.vscdb
    # ------------------------------------------------------------------
    print("\n[1/4] globalStorage/state.vscdb")
    if GLOBAL_STATE_DB.exists():
        rel = Path("globalStorage") / "state.vscdb"
        dest = snapshot_dir / rel
        if _copy_file(GLOBAL_STATE_DB, dest):
            sidecar = _dump_keys_sidecar(dest, KEY_REGEX)
            manifest.append({
                "type": "vscdb",
                "source": str(GLOBAL_STATE_DB),
                "dest": str(dest.relative_to(snapshot_dir)),
                "sidecar": sidecar.name,
                "workspace_hash": None,
            })
            copied_count += 1
    else:
        _log.warning("Não encontrado: %s", GLOBAL_STATE_DB)
        skipped_count += 1

    # ------------------------------------------------------------------
    # 2/4. workspaceStorage — state.vscdb de cada hash
    # ------------------------------------------------------------------
    print("\n[2/4] workspaceStorage — state.vscdb")
    if WORKSPACE_STORAGE_DIR.exists():
        ws_dbs = find_workspace_vscdb_files(WORKSPACE_STORAGE_DIR)
        print(f"  Encontrados: {len(ws_dbs)} workspace(s)")
        for src_db in ws_dbs:
            ws_hash = src_db.parent.name
            rel = Path("workspaceStorage") / ws_hash / "state.vscdb"
            dest = snapshot_dir / rel
            if _copy_file(src_db, dest):
                sidecar = _dump_keys_sidecar(dest, KEY_REGEX)
                manifest.append({
                    "type": "vscdb",
                    "source": str(src_db),
                    "dest": str(dest.relative_to(snapshot_dir)),
                    "sidecar": sidecar.name,
                    "workspace_hash": ws_hash,
                })
                copied_count += 1
    else:
        _log.warning("Pasta não encontrada: %s", WORKSPACE_STORAGE_DIR)
        skipped_count += 1

    # ------------------------------------------------------------------
    # 3/4. workspaceStorage — *.jsonl e outros arquivos de interesse (nível direto)
    # ------------------------------------------------------------------
    print("\n[3/4] workspaceStorage — *.jsonl / state.json (nível hash/)")
    if WORKSPACE_STORAGE_DIR.exists():
        for ext in INGEST_FILE_EXTENSIONS - {".vscdb"}:
            files = list(WORKSPACE_STORAGE_DIR.glob(f"*/*{ext}"))
            for src_file in files:
                ws_hash = src_file.parent.name
                rel = Path("workspaceStorage") / ws_hash / src_file.name
                dest = snapshot_dir / rel
                if _copy_file(src_file, dest):
                    manifest.append({
                        "type": ext.lstrip("."),
                        "source": str(src_file),
                        "dest": str(dest.relative_to(snapshot_dir)),
                        "sidecar": None,
                        "workspace_hash": ws_hash,
                    })
                    copied_count += 1

    # ------------------------------------------------------------------
    # 4/4. workspaceStorage — chatSessions/<uuid>.json e .jsonl
    # ------------------------------------------------------------------
    max_bytes = MAX_CHAT_SESSION_FILE_MB * 1024 * 1024
    print(f"\n[4/4] chatSessions — .json/.jsonl (limite {MAX_CHAT_SESSION_FILE_MB} MB por arquivo)")
    if WORKSPACE_STORAGE_DIR.exists():
        for session_dir_name in CHAT_SESSION_DIRS:
            # Prefere .json (estado final); ignora .jsonl quando .json existe
            seen_ids: set[str] = set()
            for src_file in sorted(WORKSPACE_STORAGE_DIR.glob(f"*/{session_dir_name}/*.json")):
                ws_hash = src_file.parts[-3]
                session_id = src_file.stem
                seen_ids.add(session_id)
                size = src_file.stat().st_size
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
                    })
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
                    })
                    copied_count += 1

            # Copia .jsonl apenas se NÃO existe .json correspondente
            for src_file in sorted(WORKSPACE_STORAGE_DIR.glob(f"*/{session_dir_name}/*.jsonl")):
                ws_hash = src_file.parts[-3]
                session_id = src_file.stem
                if session_id in seen_ids:
                    continue  # .json já capturado
                size = src_file.stat().st_size
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
                    })
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
                    })
                    copied_count += 1

        total_chat = sum(1 for m in manifest if m.get("type") in ("chat_session_json", "chat_session_jsonl"))
        too_large  = sum(1 for m in manifest if m.get("status") == "too_large")
        print(f"  Total sessões: {total_chat} ({too_large} too_large, lidas da origem)")

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
    }
    with manifest_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for entry in manifest:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # Limpeza de snapshots antigos (mantém atual + anterior)
    # ------------------------------------------------------------------
    _cleanup_old_snapshots(OUTPUT_RAW, keep=2)

    print(f"\n{'='*60}")
    print(f"  Copiados : {copied_count}")
    print(f"  Ignorados: {skipped_count}")
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
