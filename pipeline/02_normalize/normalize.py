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

from pipeline.lib.config import OUTPUT_NORMALIZED, OUTPUT_RAW
from pipeline.lib.db_reader import iter_jsonl
from pipeline.lib.models import ChatMessage

# Sub-módulos do normalize (importados via sys.path do diretório local)
from parsers import (
    parse_keys_sidecar,
    parse_copilot_jsonl_file,
    parse_chat_session_json,
    parse_chat_session_jsonl,
)
from aggregator import build_summaries


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def _latest_snapshot(raw_dir: Path) -> Path | None:
    snapshots = sorted(raw_dir.glob("snapshot_*"), reverse=True)
    return snapshots[0] if snapshots else None


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

    all_messages: list[ChatMessage] = []

    # ------------------------------------------------------------------
    # 1/4. Processar sidecars .keys.jsonl (vindos do ingest)
    # ------------------------------------------------------------------
    sidecars = sorted(snapshot_dir.rglob("*.keys.jsonl"))
    print(f"\n[1/4] Keys sidecars: {len(sidecars)}")
    for sidecar in sidecars:
        ws_hash = sidecar.parent.name if "workspaceStorage" in str(sidecar) else None
        msgs = parse_keys_sidecar(sidecar, ws_hash)
        print(f"  {sidecar.relative_to(snapshot_dir)} -> {len(msgs)} mensagens")
        all_messages.extend(msgs)

    # ------------------------------------------------------------------
    # 2/4. Processar *.jsonl do workspaceStorage (nível hash/ — excluindo sidecars e manifesto)
    # ------------------------------------------------------------------
    ws_jsonls = [
        p for p in snapshot_dir.rglob("*.jsonl")
        if ".keys.jsonl" not in p.name
        and p.name != "ingest_manifest.jsonl"
        and "chatSessions" not in str(p)
        and "chatEditingSessions" not in str(p)
    ]
    print(f"\n[2/4] JSONL de sessões (nível workspace): {len(ws_jsonls)}")
    for jpath in ws_jsonls:
        ws_hash = jpath.parent.name
        msgs = parse_copilot_jsonl_file(jpath, ws_hash)
        print(f"  {jpath.relative_to(snapshot_dir)} -> {len(msgs)} mensagens")
        all_messages.extend(msgs)

    # ------------------------------------------------------------------
    # 3/4. Processar chatSessions/*.json (estado final consolidado)
    #      Inclui arquivos too_large lidos diretamente da origem
    # ------------------------------------------------------------------
    chat_jsons = sorted(snapshot_dir.rglob("chatSessions/*.json"))

    # Adiciona too_large da origem via manifesto
    manifest_path_local = snapshot_dir / "ingest_manifest.jsonl"
    large_sources_json:  list[tuple[Path, str]] = []
    large_sources_jsonl: list[tuple[Path, str]] = []
    if manifest_path_local.exists():
        for entry in iter_jsonl(manifest_path_local):
            if entry.get("status") == "too_large":
                src = Path(entry["source"])
                ws  = entry.get("workspace_hash") or (src.parts[-3] if len(src.parts) >= 3 else "")
                if entry.get("type") == "chat_session_json" and src.exists():
                    large_sources_json.append((src, ws))
                elif entry.get("type") == "chat_session_jsonl" and src.exists():
                    large_sources_jsonl.append((src, ws))

    print(
        f"\n[3/4] chatSessions .json: {len(chat_jsons)} copiados"
        f" + {len(large_sources_json)} too_large (lidos da origem)"
    )
    for jpath in chat_jsons:
        ws_hash = jpath.parts[-3] if len(jpath.parts) >= 3 else jpath.parent.parent.name
        msgs = parse_chat_session_json(jpath, ws_hash)
        if msgs:
            print(f"  {jpath.relative_to(snapshot_dir)} -> {len(msgs)} msgs")
        all_messages.extend(msgs)

    for src_path, ws_hash in large_sources_json:
        msgs = parse_chat_session_json(src_path, ws_hash)
        if msgs:
            print(f"  [origem .json] {src_path.name} -> {len(msgs)} msgs")
        all_messages.extend(msgs)

    # ------------------------------------------------------------------
    # 4/4. Processar chatSessions/*.jsonl (patches — sem .json correspondente)
    # ------------------------------------------------------------------
    covered_ids = {p.stem for p in chat_jsons} | {p.stem for p, _ in large_sources_json}

    chat_jsonls = [
        p for p in sorted(snapshot_dir.rglob("chatSessions/*.jsonl"))
        if p.stem not in covered_ids
    ]
    large_jsonls = [(p, w) for p, w in large_sources_jsonl if p.stem not in covered_ids]

    print(
        f"\n[4/4] chatSessions .jsonl (patches): {len(chat_jsonls)} copiados"
        f" + {len(large_jsonls)} too_large"
    )
    for jpath in chat_jsonls:
        ws_hash = jpath.parts[-3] if len(jpath.parts) >= 3 else jpath.parent.parent.name
        msgs = parse_chat_session_jsonl(jpath, ws_hash)
        if msgs:
            print(f"  {jpath.relative_to(snapshot_dir)} -> {len(msgs)} msgs")
        all_messages.extend(msgs)

    for src_path, ws_hash in large_jsonls:
        msgs = parse_chat_session_jsonl(src_path, ws_hash)
        if msgs:
            print(f"  [origem .jsonl] {src_path.name} -> {len(msgs)} msgs")
        all_messages.extend(msgs)

    # ------------------------------------------------------------------
    # Gravar saídas
    # ------------------------------------------------------------------
    OUTPUT_NORMALIZED.mkdir(parents=True, exist_ok=True)

    sessions_path = OUTPUT_NORMALIZED / "sessions.jsonl"
    with sessions_path.open("w", encoding="utf-8") as fh:
        for m in all_messages:
            fh.write(m.to_jsonl_line() + "\n")

    summaries = build_summaries(all_messages)
    summaries_path = OUTPUT_NORMALIZED / "summaries.jsonl"
    with summaries_path.open("w", encoding="utf-8") as fh:
        for s in summaries:
            fh.write(s.to_jsonl_line() + "\n")

    print(f"\n{'='*60}")
    print(f"  Mensagens normalizadas : {len(all_messages)}")
    print(f"  Sessões (summaries)    : {len(summaries)}")
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
