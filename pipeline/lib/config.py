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
EMPTY_WINDOW_CHAT_SESSIONS_DIR: Path = VSCODE_APPDATA / "User" / "globalStorage" / "emptyWindowChatSessions"
WORKSPACE_STORAGE_DIR: Path = VSCODE_APPDATA / "User" / "workspaceStorage"

# ---------------------------------------------------------------------------
# Codex CLI / extensão openai.chatgpt — sessões em ~/.codex/sessions/
# ---------------------------------------------------------------------------
CODEX_SESSIONS_DIR: Path          = Path.home() / ".codex" / "sessions"
CODEX_ARCHIVED_SESSIONS_DIR: Path = Path.home() / ".codex" / "archived_sessions"
CODEX_SESSION_INDEX: Path         = Path.home() / ".codex" / "session_index.jsonl"

# ---------------------------------------------------------------------------
# Claude Code CLI — projetos e sessões em ~/.claude/projects/
# ---------------------------------------------------------------------------
CLAUDE_PROJECTS_DIR: Path = Path.home() / ".claude" / "projects"

# ---------------------------------------------------------------------------
# Raiz do pipeline (destino de escrita)
# ---------------------------------------------------------------------------
PIPELINE_ROOT: Path = Path(__file__).resolve().parents[1]

OUTPUT_RAW: Path        = PIPELINE_ROOT / "output" / "raw"
OUTPUT_NORMALIZED: Path = PIPELINE_ROOT / "output" / "normalized"
OUTPUT_REPORTS: Path    = PIPELINE_ROOT / "output" / "reports"
OUTPUT_STATE: Path      = PIPELINE_ROOT / "output" / "state"
OUTPUT_NORMALIZED_SHARDS: Path = OUTPUT_NORMALIZED / "shards"
OUTPUT_NORMALIZED_MESSAGE_SHARDS: Path = OUTPUT_NORMALIZED_SHARDS / "messages"
OUTPUT_NORMALIZED_SUMMARY_SHARDS: Path = OUTPUT_NORMALIZED_SHARDS / "summaries"

# Estado incremental local
INCREMENTAL_STATE_SCHEMA_VERSION: str = "1.0"
INCREMENTAL_INDEX_FILE: Path          = OUTPUT_STATE / "incremental_index.json"

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
CHAT_EDITING_SESSION_DIR = "chatEditingSessions"

# Tamanho máximo de arquivo de sessão a ser COPIADO para raw/ (em MB).
# Arquivos maiores são registrados no manifesto com status="too_large"
# e lidos diretamente da origem durante o normalize.
MAX_CHAT_SESSION_FILE_MB: int = 50
