"""
launcher.py — Bandeja do sistema para o chatsvs pipeline (Windows).

Fluxo:
  1. Inicia o Streamlit viewer em segundo plano (sem janela de terminal).
  2. Exibe ícone na bandeja do sistema com menu de contexto.
  3. Menu:
       • Executar Sincronização  → roda o pipeline completo (ingest→normalize→report)
       • Abrir Viewer            → abre http://localhost:8501 no navegador padrão
       • ─────────────────────
       • Parar e Fechar          → encerra o Streamlit e remove o ícone da bandeja

Uso normal (via atalho):
    .venv\\Scripts\\pythonw.exe launcher.py

Uso em terminal (para debug):
    .venv\\Scripts\\python.exe launcher.py
"""

from __future__ import annotations

import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import pystray
from PIL import Image

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
VENV_SCRIPTS = ROOT / ".venv" / "Scripts"
PYTHONW       = VENV_SCRIPTS / "pythonw.exe"
STREAMLIT     = VENV_SCRIPTS / "streamlit.exe"
VIEWER_APP    = ROOT / "pipeline" / "viewer" / "app.py"
PIPELINE_SCRIPT = ROOT / "pipeline" / "run_pipeline.py"
ICO_PATH      = ROOT / "VS-Code.ico"

VIEWER_PORT = 8501
VIEWER_URL  = f"http://localhost:{VIEWER_PORT}"

# Suprime janela de console nos subprocessos (Windows-only)
_NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ---------------------------------------------------------------------------
# Ícone
# ---------------------------------------------------------------------------

def make_icon_image() -> Image.Image:
    """Carrega o ícone VS-Code.ico como imagem PIL para a bandeja do sistema."""
    return Image.open(str(ICO_PATH))


def ensure_ico() -> Path:
    """Retorna o caminho do .ico.  Levanta erro se o arquivo não existir."""
    if not ICO_PATH.exists():
        raise FileNotFoundError(
            f"Ícone não encontrado: {ICO_PATH}\n"
            "Coloque o arquivo VS-Code.ico na raiz do repositório."
        )
    return ICO_PATH


# ---------------------------------------------------------------------------
# Gerenciamento do processo Streamlit
# ---------------------------------------------------------------------------

_streamlit_proc: subprocess.Popen | None = None  # type: ignore[type-arg]


def start_streamlit() -> None:
    """Inicia o Streamlit viewer em segundo plano (sem janela)."""
    global _streamlit_proc
    if _streamlit_proc and _streamlit_proc.poll() is None:
        return  # já está rodando

    _streamlit_proc = subprocess.Popen(
        [
            str(STREAMLIT), "run", str(VIEWER_APP),
            "--server.port",       str(VIEWER_PORT),
            "--server.headless",   "true",
            "--server.runOnSave",  "false",
            "--browser.gatherUsageStats", "false",
        ],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_NO_WINDOW,
    )


# ---------------------------------------------------------------------------
# Callbacks do menu de bandeja
# ---------------------------------------------------------------------------

def _on_sync(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    """Executa o pipeline completo em thread separada para não bloquear a bandeja."""

    def _worker() -> None:
        icon.notify("Sincronização iniciada…", "Chat VS Pipeline")
        result = subprocess.run(
            [str(PYTHONW), str(PIPELINE_SCRIPT)],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_NO_WINDOW,
        )
        if result.returncode == 0:
            icon.notify("Sincronização concluída com sucesso!", "Chat VS Pipeline")
        else:
            icon.notify(
                "Erro na sincronização. Verifique os arquivos de log.",
                "Chat VS Pipeline",
            )

    threading.Thread(target=_worker, daemon=True).start()


def _on_open_viewer(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    """Abre o viewer no navegador padrão."""
    webbrowser.open(VIEWER_URL)


def _on_stop(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    """Para o Streamlit e encerra o ícone de bandeja."""
    global _streamlit_proc
    if _streamlit_proc and _streamlit_proc.poll() is None:
        _streamlit_proc.terminate()
        _streamlit_proc = None
    icon.stop()


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    ensure_ico()
    start_streamlit()

    icon = pystray.Icon(
        name="chatsvs",
        icon=make_icon_image(),
        title="Chat VS — Pipeline",
        menu=pystray.Menu(
            pystray.MenuItem("Executar Sincronização", _on_sync),
            pystray.MenuItem("Abrir Viewer",           _on_open_viewer),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Parar e Fechar",         _on_stop, default=True),
        ),
    )
    icon.run()


if __name__ == "__main__":
    main()
