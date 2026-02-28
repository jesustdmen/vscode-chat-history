"""
config.py — Configurações centrais do pipeline.

Todas as constantes de caminho, regex e flags ficam aqui.
Os demais módulos importam deste arquivo; para mudar um path basta alterar aqui.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Validação de ambiente
# ---------------------------------------------------------------------------
if "APPDATA" not in os.environ:
    raise EnvironmentError(
        "Variável de ambiente APPDATA não encontrada.\n"
        "Esta ferramenta foi projetada para Windows (VS Code em %APPDATA%\\Code).\n"
        "Em outros sistemas, defina APPDATA manualmente antes de executar."
    )

# ---------------------------------------------------------------------------
# Raiz do AppData do VS Code (origem — NUNCA escrevemos aqui)
# ---------------------------------------------------------------------------
VSCODE_APPDATA: Path = Path(os.environ["APPDATA"]) / "Code"

GLOBAL_STATE_DB: Path = VSCODE_APPDATA / "User" / "globalStorage" / "state.vscdb"
WORKSPACE_STORAGE_DIR: Path = VSCODE_APPDATA / "User" / "workspaceStorage"

# ---------------------------------------------------------------------------
# Raiz do pipeline (destino de escrita)
# ---------------------------------------------------------------------------
PIPELINE_ROOT: Path = Path(__file__).resolve().parents[1]

OUTPUT_RAW: Path        = PIPELINE_ROOT / "output" / "raw"
OUTPUT_NORMALIZED: Path = PIPELINE_ROOT / "output" / "normalized"
OUTPUT_REPORTS: Path    = PIPELINE_ROOT / "output" / "reports"

# ---------------------------------------------------------------------------
# Chaves SQLite de interesse (mesmo padrão do monitor PowerShell)
# ---------------------------------------------------------------------------
KEY_REGEX: str = (
    r"(?i)openai\.chatgpt"
    r"|agentSessions"
    r"|chat\."
    r"|codex"
    r"|memento/webviewView\.chatgpt"
    r"|workbench\.find\.history"
)

# Subconjunto de chaves com parsing especializado no normalize
KNOWN_KEYS = {
    "openai.chatgpt",
    "agentSessions.model.cache",
    "agentSessions.state.cache",
    "chat.ChatSessionStore.index",
}

# ---------------------------------------------------------------------------
# Parâmetros de ingestão
# ---------------------------------------------------------------------------
# Extensões de arquivo copiadas do workspaceStorage (nível direto de hash)
INGEST_FILE_EXTENSIONS = {".vscdb", ".jsonl", ".json"}

# Subpastas de sessão de chat a serem ingeridas (dentro de <hash>/)
CHAT_SESSION_DIRS = ["chatSessions"]

# Tamanho máximo de arquivo de sessão a ser COPIADO para raw/ (em MB).
# Arquivos maiores são registrados no manifesto com status="too_large"
# e lidos diretamente da origem durante o normalize.
MAX_CHAT_SESSION_FILE_MB: int = 50
