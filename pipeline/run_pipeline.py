"""
run_pipeline.py — Orquestrador: executa ingest → normalize → report em sequência.

Uso:
    # Pipeline completo (snapshot novo):
    python pipeline/run_pipeline.py

    # Só normalize + report sobre um snapshot existente:
    python pipeline/run_pipeline.py --skip-ingest --snapshot-dir output/raw/snapshot_20260222_120000

    # Só report (normalized já existe):
    python pipeline/run_pipeline.py --only-report
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

# Raiz do repositório (c:/Sandbox/_chatsvs) — necessário para imports de pipeline.*
# Após `pip install -e .` este bloco torna-se no-op.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_PIPELINE_ROOT = Path(__file__).resolve().parent


def _import_stage(name: str, path: Path):
    """
    Importa um módulo de estágio do pipeline por caminho absoluto.
    Necessário porque os diretórios 01_ingest/, 02_normalize/, 03_report/
    começam com dígito e não são identificadores Python válidos.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)    # type: ignore[arg-type]
    spec.loader.exec_module(mod)                   # type: ignore[union-attr]
    return mod


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pipeline completo: ingest → normalize → report"
    )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Pula o ingest e usa o snapshot mais recente (ou --snapshot-dir)",
    )
    parser.add_argument(
        "--only-report",
        action="store_true",
        help="Executa apenas o report (normalized já deve existir)",
    )
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=None,
        help="Snapshot específico para o normalize (padrão: mais recente em output/raw/)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    snapshot_dir: Path | None = args.snapshot_dir

    # ------------------------------------------------------------------
    # Bloco 1 — Ingestão
    # ------------------------------------------------------------------
    if not args.skip_ingest and not args.only_report:
        ingest_mod = _import_stage(
            "ingest", _PIPELINE_ROOT / "01_ingest" / "ingest.py"
        )
        snapshot_dir = ingest_mod.run_ingest(snapshot_dir=snapshot_dir)

    # ------------------------------------------------------------------
    # Bloco 2 — Normalização
    # ------------------------------------------------------------------
    if not args.only_report:
        norm_mod = _import_stage(
            "normalize", _PIPELINE_ROOT / "02_normalize" / "normalize.py"
        )
        sessions_path, summaries_path = norm_mod.run_normalize(snapshot_dir=snapshot_dir)
    else:
        # _ROOT já está em sys.path — import direto funciona em qualquer contexto
        from pipeline.lib.config import OUTPUT_NORMALIZED
        sessions_path = OUTPUT_NORMALIZED / "sessions.jsonl"
        summaries_path = OUTPUT_NORMALIZED / "summaries.jsonl"

    # ------------------------------------------------------------------
    # Bloco 3 — Report
    # ------------------------------------------------------------------
    report_mod = _import_stage(
        "report", _PIPELINE_ROOT / "03_report" / "report.py"
    )
    report_mod.run_report(sessions_path=sessions_path, summaries_path=summaries_path)

    print("\nPipeline concluído com sucesso.")


if __name__ == "__main__":
    main()
