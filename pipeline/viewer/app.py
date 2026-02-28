"""
pipeline/viewer/app.py — Visualizador de conversas do Copilot Chat

Uso:
    cd C:\\Sandbox\\_chatsvs
    .venv\\Scripts\\streamlit.exe run pipeline/viewer/app.py
"""

from __future__ import annotations

import html as _html
import json
import locale
import os
import re
import subprocess
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import unquote

import markdown as _markdown
import streamlit as st

# ---------------------------------------------------------------------------
# Markdown helper
# ---------------------------------------------------------------------------
def _md_to_html(text: str, nl2br: bool = False) -> str:
    exts = ["tables", "fenced_code", "sane_lists"]
    if nl2br:
        exts.append("nl2br")
    return _markdown.markdown(text or "", extensions=exts)


# ---------------------------------------------------------------------------
# Configuração de página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Chat Viewer",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Badges de fonte
# ---------------------------------------------------------------------------
_SOURCE_STYLE: dict[str, tuple[str, str]] = {
    "chat_session_json":  ("#5b21b6", "#ede9fe"),
    "chat_session_jsonl": ("#1d4ed8", "#dbeafe"),
    "chat_session":       ("#4338ca", "#e0e7ff"),
    "openai_chatgpt":     ("#065f46", "#d1fae5"),
    "chat_session_index": ("#374151", "#f3f4f6"),
    "copilot_jsonl":      ("#0e7490", "#cffafe"),
    "copilot_jsonl_raw":  ("#92400e", "#fef3c7"),
    "agent_sessions":     ("#7f1d1d", "#fee2e2"),
}
_SOURCE_LABEL: dict[str, str] = {
    "chat_session_json":  "json",
    "chat_session_jsonl": "jsonl",
    "chat_session":       "session",
    "openai_chatgpt":     "openai",
    "chat_session_index": "index",
    "copilot_jsonl":      "copilot",
    "copilot_jsonl_raw":  "raw",
    "agent_sessions":     "agent",
}


def _source_badge(source: str) -> str:
    bg, fg = _SOURCE_STYLE.get(source, ("#374151", "#f3f4f6"))
    label  = _SOURCE_LABEL.get(source, source.replace("chat_session_", "").replace("_", " "))
    return (
        f'<span style="background:{bg};color:{fg};padding:1px 7px;'
        f'border-radius:10px;font-size:0.70rem;font-weight:600;">'
        f'{_html.escape(label)}</span>'
    )


# ---------------------------------------------------------------------------
# Locale / formato de data
# ---------------------------------------------------------------------------
def _get_date_format() -> str:
    import warnings
    loc = ""
    try:
        loc = locale.getlocale()[0] or ""
    except Exception:
        pass
    if not loc:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            try:
                loc = (locale.getdefaultlocale()[0] or "")  # type: ignore[attr-defined]
            except Exception:
                pass
    if not loc:
        loc = os.environ.get("LANG", os.environ.get("LANGUAGE", "")).split(".")[0]
    if loc.startswith("en_US") or loc in ("en_PH", "en_AG", "en_MH"):
        return "MM/DD/YYYY"
    if loc.startswith(("zh_", "ja_", "ko_", "hu_")):
        return "YYYY/MM/DD"
    return "DD/MM/YYYY"


_DATE_FMT = _get_date_format()

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
_ROOT           = Path(__file__).resolve().parents[2]
_SESSIONS_FILE  = _ROOT / "pipeline" / "output" / "normalized" / "sessions.jsonl"
_SUMMARIES_FILE = _ROOT / "pipeline" / "output" / "normalized" / "summaries.jsonl"
_WS_STORAGE     = Path(os.environ.get("APPDATA", "")) / "Code" / "User" / "workspaceStorage"

# ---------------------------------------------------------------------------
# Timezone BRT
# ---------------------------------------------------------------------------
_BRT = timezone(timedelta(hours=-3))


def _to_utc_aware(ts_iso: str) -> datetime:
    dt = datetime.fromisoformat(ts_iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def ts_to_label(ts: str | None) -> str:
    if not ts:
        return ""
    try:
        return _to_utc_aware(ts).astimezone(_BRT).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return ts[:16]


def ts_to_date_brt(ts: str | None) -> str:
    if not ts:
        return ""
    try:
        return _to_utc_aware(ts).astimezone(_BRT).strftime("%Y-%m-%d")
    except Exception:
        return ts[:10]


def _to_brt(ts_iso: str | None) -> str | None:
    if not ts_iso:
        return None
    try:
        return _to_utc_aware(ts_iso).astimezone(_BRT).isoformat(timespec="seconds")
    except Exception:
        return ts_iso


# ---------------------------------------------------------------------------
# Carregamento de dados (cache)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Carregando dados...")
def load_data() -> tuple[list[dict], list[dict]]:
    def read_jsonl(path: Path) -> list[dict]:
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return out
    return read_jsonl(_SESSIONS_FILE), read_jsonl(_SUMMARIES_FILE)


@st.cache_data(show_spinner=False)
def load_workspace_paths() -> dict[str, str]:
    result: dict[str, str] = {}
    if not _WS_STORAGE.exists():
        return result
    for d in _WS_STORAGE.iterdir():
        wf = d / "workspace.json"
        if not wf.is_file():
            continue
        try:
            data = json.loads(wf.read_text(encoding="utf-8"))
            raw  = data.get("folder") or data.get("workspace") or ""
            if raw.startswith("file:///"):
                raw = raw[8:]
            path = unquote(raw).replace("/", "\\").strip("\\")
            if len(path) >= 2 and path[1] == ":":
                path = path[0].upper() + path[1:]
            result[d.name] = path
        except Exception:
            pass
    return result


@st.cache_data(show_spinner=False)
def build_workspace_index(summaries: list[dict], ws_paths: dict[str, str]) -> list[dict]:
    by_hash: dict[str, dict] = {}
    for s in summaries:
        h   = s.get("workspace_hash") or ""
        src = s.get("source", "")
        if not h or src == "agent_sessions":
            continue
        if h not in by_hash:
            by_hash[h] = {
                "hash": h, "folder": ws_paths.get(h, "—"),
                "first_ts": s.get("first_ts") or "", "last_ts": s.get("last_ts") or "",
                "sessions": [], "total_user": 0, "total_assistant": 0,
            }
        entry = by_hash[h]
        ft, lt = s.get("first_ts") or "", s.get("last_ts") or ""
        if ft and (not entry["first_ts"] or ft < entry["first_ts"]):
            entry["first_ts"] = ft
        if lt and lt > entry["last_ts"]:
            entry["last_ts"] = lt
        entry["total_user"]      += s.get("user_turns", 0)
        entry["total_assistant"] += s.get("assistant_turns", 0)
        entry["sessions"].append({
            "thread_id": s.get("thread_id") or "", "title": (s.get("title") or "").strip() or "Sem título",
            "last_ts": lt, "user_turns": s.get("user_turns", 0),
            "assistant_turns": s.get("assistant_turns", 0), "source": src,
        })
    for entry in by_hash.values():
        entry["sessions"].sort(key=lambda x: x["last_ts"], reverse=True)
    return sorted(by_hash.values(), key=lambda x: x["last_ts"], reverse=True)


@st.cache_data(show_spinner=False)
def build_session_index(messages: list[dict], summaries: list[dict]) -> dict[str, dict]:
    """
    Retorna dict: thread_id → session dict.
    Inclui '_search_text' pré-computado para busca eficiente (sem iterar
    por mensagens a cada keystroke — O(n_sessions) em vez de O(n*m)).
    """
    by_thread: dict[str, list[dict]] = defaultdict(list)
    for m in messages:
        tid = m.get("thread_id") or m.get("session_id") or ""
        if tid:
            by_thread[tid].append(m)

    def _make(s: dict, src: str) -> dict:
        tid        = s.get("thread_id") or s.get("session_id") or ""
        title      = (s.get("title") or "").strip() or "Sem título"
        last_ts    = s.get("last_ts") or ""
        date_label = ts_to_date_brt(last_ts) if last_ts else "—"
        msgs = sorted(
            [m for m in by_thread.get(tid, []) if m.get("role") != "system"],
            key=lambda m: m.get("timestamp") or "",
        )
        search_text = " ".join([
            title.lower(), tid.lower(), src.lower(),
            " ".join((m.get("text") or "").lower() for m in msgs),
        ])
        return {
            "thread_id": tid, "title": title, "source": src,
            "last_ts": last_ts, "date_label": date_label,
            "user_turns": s.get("user_turns", 0), "assistant_turns": s.get("assistant_turns", 0),
            "tool_calls": s.get("tool_calls", 0), "message_count": len(msgs),
            "messages": msgs, "workspace_hash": s.get("workspace_hash") or "",
            "_search_text": search_text,
        }

    sessions: dict[str, dict] = {}
    for s in summaries:
        src = s.get("source", "")
        if src in ("chat_session_index", "agent_sessions"):
            continue
        tid = s.get("thread_id") or s.get("session_id") or ""
        if tid:
            sessions[tid] = _make(s, src)

    for s in summaries:
        if s.get("source") != "chat_session_index":
            continue
        tid = s.get("thread_id") or s.get("session_id") or ""
        if tid and tid not in sessions:
            sessions[tid] = _make(s, "chat_session_index")

    return sessions


# ---------------------------------------------------------------------------
# CSS — Dark e Light themes
# ---------------------------------------------------------------------------
_CSS_COMMON = """
<style>
@keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}

.msg-user,.msg-assistant{
    border-radius:14px;padding:10px 14px;
    word-break:break-word;overflow-x:auto;
    animation:fadeIn .15s ease-in;
}
.msg-user{border-radius:14px 14px 4px 14px;margin:6px 0 6px 60px}
.msg-assistant{border-radius:14px 14px 14px 4px;margin:6px 60px 6px 0}

.msg-user p,.msg-assistant p{margin:.35em 0}
.msg-user p:first-child,.msg-assistant p:first-child{margin-top:0}
.msg-user p:last-child,.msg-assistant p:last-child{margin-bottom:0}
.msg-user h1,.msg-user h2,.msg-user h3,.msg-user h4,
.msg-assistant h1,.msg-assistant h2,.msg-assistant h3,.msg-assistant h4{
    font-size:1.05em;font-weight:700;margin:.7em 0 .3em;padding-bottom:2px;
}
.msg-user h1,.msg-assistant h1{font-size:1.15em}
.msg-user ul,.msg-user ol,.msg-assistant ul,.msg-assistant ol{margin:.3em 0 .3em 1.4em;padding:0}
.msg-user li,.msg-assistant li{margin:.15em 0}
.msg-user table,.msg-assistant table{border-collapse:collapse;width:100%;margin:.6em 0;font-size:.88em}
.msg-user th,.msg-assistant th{padding:5px 10px;text-align:left}
.msg-user td,.msg-assistant td{padding:4px 10px}
.msg-user pre,.msg-assistant pre{border-radius:6px;padding:10px 12px;overflow-x:auto;margin:.5em 0}
.msg-user pre code,.msg-assistant pre code{font-family:'Cascadia Code','Fira Code',Consolas,monospace;font-size:.85em;padding:0;background:transparent}
.msg-user code,.msg-assistant code{border-radius:3px;padding:1px 5px;font-family:'Cascadia Code','Fira Code',Consolas,monospace;font-size:.88em}
.msg-user blockquote,.msg-assistant blockquote{margin:.4em 0;padding:2px 12px}
.msg-user hr,.msg-assistant hr{border:none;margin:.6em 0}
.msg-role{font-size:.70rem;color:#888;margin-bottom:2px;margin-top:8px}
.msg-role-right{text-align:right}

.stat-bar{display:flex;gap:16px;flex-wrap:wrap;border-radius:8px;padding:10px 16px;margin-bottom:8px}
.stat-item{display:flex;flex-direction:column;align-items:center;min-width:70px}
.stat-value{font-size:1.4rem;font-weight:700;line-height:1.1}
.stat-label{font-size:.68rem;margin-top:2px;text-transform:uppercase;letter-spacing:.05em}
.stat-blue{color:#3b82f6}.stat-green{color:#10b981}.stat-yellow{color:#f59e0b}.stat-gray{color:#6b7280}

.sess-header{border-radius:8px;padding:10px 14px;margin-bottom:10px}
.sess-header-title{font-size:1.05rem;font-weight:600;margin-bottom:4px}
.sess-header-meta{font-size:.76rem}

.ws-card{border-radius:8px;padding:12px 16px;margin-bottom:10px;transition:border-color .15s ease,box-shadow .15s ease}
.ws-hash{font-family:monospace;font-size:.85rem}
.ws-folder{font-weight:600;font-size:.95rem;word-break:break-all}
.ws-meta{font-size:.78rem;margin-top:4px}
.ws-sess-item{font-size:.82rem;padding:2px 0 2px 12px;margin:3px 0}
.ws-sess-meta{font-size:.74rem}

.day-header{padding:6px 12px;border-radius:6px;font-weight:600;font-size:.95rem;margin-top:12px}
.diary-session{margin:4px 0 4px 16px;font-size:.87rem}
.diary-session-title{font-weight:500}
.diary-meta{font-size:.76rem}

.empty-state{text-align:center;padding:40px 20px;border-radius:8px;margin:20px 0}
.empty-state-icon{font-size:2.5rem;margin-bottom:8px}
.empty-state-text{font-size:.9rem}
</style>
"""

_CSS_DARK = """
<style>
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:#0e0e1a}
::-webkit-scrollbar-thumb{background:#3a3a5c;border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:#5a5a8c}

.msg-user{background:linear-gradient(135deg,#1e3a5f,#1a3356);color:#e8f0fe;box-shadow:0 1px 3px rgba(0,0,0,.3)}
.msg-assistant{background:linear-gradient(135deg,#1e1e2e,#1a1a28);color:#d4d4d8;box-shadow:0 1px 3px rgba(0,0,0,.3)}
.msg-user h1,.msg-user h2,.msg-user h3,.msg-user h4,
.msg-assistant h1,.msg-assistant h2,.msg-assistant h3,.msg-assistant h4{border-bottom:1px solid #3a3a5c}
.msg-user th,.msg-assistant th{background:#2a2a3e;color:#a78bfa;border:1px solid #4a4a6a}
.msg-user td,.msg-assistant td{border:1px solid #3a3a5c}
.msg-user tr:nth-child(even),.msg-assistant tr:nth-child(even){background:#272736}
.msg-user pre,.msg-assistant pre{background:#0d0d1a;border:1px solid #3a3a5c}
.msg-user pre code,.msg-assistant pre code{color:#b4d4ff}
.msg-user code,.msg-assistant code{background:#1a1a2e;color:#f8b4ff}
.msg-user blockquote,.msg-assistant blockquote{border-left:3px solid #a78bfa;color:#aaa}
.msg-user hr,.msg-assistant hr{border-top:1px solid #3a3a5c}

.stat-bar{background:#1a1a2e}
.stat-label{color:#888}

.sess-header{background:#1e1e2e;border:1px solid #3a3a5c}
.sess-header-title{color:#e8e8f0}
.sess-header-meta{color:#888}

.ws-card{background:#1e1e2e;border:1px solid #3a3a5c}
.ws-card:hover{border-color:#5a5a8c}
.ws-hash{color:#7c6fcd}
.ws-folder{color:#e8e8f0}
.ws-meta{color:#888}
.ws-sess-item{color:#c4c4cf;border-left:2px solid #3a3a5c}
.ws-sess-meta{color:#888}

.day-header{background:linear-gradient(90deg,#2d2d3e,#252535);color:#a78bfa;border-left:3px solid #7c3aed}
.diary-session{color:#c4c4cf}
.diary-session-title{color:#e8e8f0}
.diary-meta{color:#999}

.empty-state{color:#666;border:1px dashed #3a3a5c}
</style>
"""

_CSS_LIGHT = """
<style>
/* ── Streamlit chrome overrides (light) ── */
[data-testid="stAppViewContainer"],[data-testid="stMainBlockContainer"]{background:#f8fafc !important}
[data-testid="stHeader"]{background:#f8fafc !important;border-bottom:1px solid #e2e8f0 !important}

/* Sidebar */
[data-testid="stSidebar"]{background:#ffffff !important;border-right:1px solid #e2e8f0 !important}
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] .stMarkdown span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stCaption{color:#1e293b !important}
[data-testid="stSidebar"] .stButton > button{
    background:#f1f5f9 !important;color:#1e293b !important;
    border:1px solid #e2e8f0 !important}
[data-testid="stSidebar"] .stButton > button:hover{background:#e2e8f0 !important}

/* Text inputs */
input[type="text"],input[type="search"],input[type="date"],
[data-testid="stTextInput"] input,
[data-testid="stDateInput"] input{
    background:#ffffff !important;color:#1e293b !important;
    border-color:#e2e8f0 !important}

/* Selectbox & Multiselect */
[data-baseweb="select"] > div:first-child{
    background:#ffffff !important;border-color:#e2e8f0 !important}
[data-baseweb="select"] span,[data-baseweb="select"] div[class*="placeholder"]{
    color:#1e293b !important}
[data-baseweb="popover"] [role="listbox"]{
    background:#ffffff !important;border-color:#e2e8f0 !important}
[data-baseweb="popover"] [role="option"]{color:#1e293b !important}
[data-baseweb="popover"] [role="option"]:hover{background:#f1f5f9 !important}

/* Checkboxes */
[data-testid="stCheckbox"] label,[data-testid="stCheckbox"] span{color:#1e293b !important}

/* Buttons (main area) */
.stButton > button{
    background:#f1f5f9 !important;color:#1e293b !important;
    border:1px solid #e2e8f0 !important}
.stButton > button:hover{background:#e2e8f0 !important}
[data-testid="stDownloadButton"] > button{
    background:#3b82f6 !important;color:#ffffff !important;border:none !important}
[data-testid="stDownloadButton"] > button:hover{background:#2563eb !important}

/* Tabs */
[data-testid="stTab"]{color:#64748b !important}
[data-testid="stTab"][aria-selected="true"]{color:#4338ca !important;border-bottom-color:#4338ca !important}
[data-testid="stTabsContent"]{background:#f8fafc !important}

/* Expanders */
[data-testid="stExpander"]{border-color:#e2e8f0 !important;background:#ffffff !important}
[data-testid="stExpander"] summary p,[data-testid="stExpander"] summary span{color:#1e293b !important}

/* Code blocks */
[data-testid="stCode"]{background:#f1f5f9 !important}
[data-testid="stCode"] code{color:#1e293b !important}

/* General text */
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] span{color:#1e293b !important}
.stCaption p,.stCaption span{color:#64748b !important}

/* Alerts */
.stInfo{background:#eff6ff !important;color:#1e40af !important}
.stSuccess{background:#f0fdf4 !important;color:#166534 !important}
.stError{background:#fef2f2 !important;color:#991b1b !important}
.stWarning{background:#fffbeb !important;color:#92400e !important}

/* Divider */
hr{border-color:#e2e8f0 !important}

/* ── scrollbar ── */
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:#f1f5f9}
::-webkit-scrollbar-thumb{background:#cbd5e1;border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:#94a3b8}

.msg-user{background:linear-gradient(135deg,#dbeafe,#bfdbfe);color:#1e3a5f;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.msg-assistant{background:linear-gradient(135deg,#f8fafc,#f1f5f9);color:#1e293b;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.msg-user h1,.msg-user h2,.msg-user h3,.msg-user h4,
.msg-assistant h1,.msg-assistant h2,.msg-assistant h3,.msg-assistant h4{border-bottom:1px solid #cbd5e1}
.msg-user th,.msg-assistant th{background:#e0e7ff;color:#4338ca;border:1px solid #c7d2fe}
.msg-user td,.msg-assistant td{border:1px solid #e2e8f0}
.msg-user tr:nth-child(even),.msg-assistant tr:nth-child(even){background:#f8fafc}
.msg-user pre,.msg-assistant pre{background:#f1f5f9;border:1px solid #e2e8f0}
.msg-user pre code,.msg-assistant pre code{color:#1d4ed8}
.msg-user code,.msg-assistant code{background:#ede9fe;color:#6d28d9}
.msg-user blockquote,.msg-assistant blockquote{border-left:3px solid #818cf8;color:#64748b}
.msg-user hr,.msg-assistant hr{border-top:1px solid #e2e8f0}

.stat-bar{background:#f8fafc;border:1px solid #e2e8f0}
.stat-label{color:#64748b}

.sess-header{background:#ffffff;border:1px solid #e2e8f0}
.sess-header-title{color:#1e293b}
.sess-header-meta{color:#64748b}

.ws-card{background:#ffffff;border:1px solid #e2e8f0}
.ws-card:hover{border-color:#818cf8;box-shadow:0 2px 8px rgba(99,102,241,.1)}
.ws-hash{color:#6366f1}
.ws-folder{color:#1e293b}
.ws-meta{color:#64748b}
.ws-sess-item{color:#475569;border-left:2px solid #e2e8f0}
.ws-sess-meta{color:#94a3b8}

.day-header{background:linear-gradient(90deg,#ede9fe,#e0e7ff);color:#4338ca;border-left:3px solid #6366f1}
.diary-session{color:#475569}
.diary-session-title{color:#1e293b}
.diary-meta{color:#64748b}

.empty-state{color:#94a3b8;border:1px dashed #cbd5e1}
</style>
"""


def _inject_css(theme: str = "dark") -> None:
    st.markdown(_CSS_COMMON, unsafe_allow_html=True)
    st.markdown(_CSS_DARK if theme == "dark" else _CSS_LIGHT, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Exportação JSON (schema v1.0)
# ---------------------------------------------------------------------------

def _safe_filename(title: str) -> str:
    s = title.strip()
    s = re.sub(r'[/\\:*?"<>|]', '-', s)
    s = re.sub(r'\s+', '_', s)
    s = re.sub(r'-{2,}', '-', s)
    return s[:120]


def build_session_json(session: dict) -> dict:
    """
    Monta o payload JSON conforme schema_version 1.0.
    exchange_id é determinístico via uuid5 — exportações do mesmo conteúdo
    produzem IDs idênticos, facilitando deduplicação.
    """
    msgs = [m for m in session["messages"] if m.get("role") in ("user", "assistant", "tool")]
    exchanges: list[dict] = []
    current_user: dict | None = None
    current_responses: list[dict] = []
    user_idx = 0
    asst_idx = 0

    for m in msgs:
        role = m.get("role")
        if role == "user":
            if current_user is not None:
                exchanges.append({
                    "exchange_id": str(uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"{session['thread_id']}:exchange:{user_idx}",
                    )),
                    "user_message":        current_user,
                    "assistant_responses": current_responses,
                })
            user_idx += 1
            current_user = {
                "message_id": f"u-{user_idx:04d}",
                "content":    (m.get("text") or "").strip(),
                "sent_at":    _to_brt(m.get("timestamp")),
            }
            current_responses = []
        elif role in ("assistant", "tool") and current_user is not None:
            asst_idx += 1
            entry: dict = {
                "message_id": f"a-{asst_idx:04d}",
                "role":       role,
                "content":    (m.get("text") or "").strip(),
                "sent_at":    _to_brt(m.get("timestamp")),
            }
            if role == "tool" and m.get("tool"):
                entry["tool_name"] = m["tool"]
            current_responses.append(entry)

    if current_user is not None:
        exchanges.append({
            "exchange_id": str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{session['thread_id']}:exchange:{user_idx}",
            )),
            "user_message":        current_user,
            "assistant_responses": current_responses,
        })

    first_ts = next((m.get("timestamp") for m in msgs if m.get("timestamp")), None)
    return {
        "schema_version": "1.0",
        "source": "chat_viewer",
        "session": {
            "session_id":          session["thread_id"],
            "session_name":        session["title"],
            "session_date":        session["date_label"],
            "created_at":          _to_brt(first_ts),
            "last_interaction_at": _to_brt(session.get("last_ts")),
            "stats": {
                "user_turns":      session["user_turns"],
                "assistant_turns": session["assistant_turns"],
                "tool_calls":      session["tool_calls"],
            },
            "exchanges": exchanges,
        },
    }


# ---------------------------------------------------------------------------
# Componente: mensagem de chat
# ---------------------------------------------------------------------------
def render_message(m: dict) -> None:
    role = m.get("role", "")
    text = m.get("text") or ""
    ts   = ts_to_label(m.get("timestamp"))
    tool = m.get("tool")

    if role == "user":
        html_content = _md_to_html(text, nl2br=True)
        st.markdown(
            f'<div class="msg-role msg-role-right">Você · {_html.escape(ts)}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(f'<div class="msg-user">{html_content}</div>', unsafe_allow_html=True)
        with st.expander("📋 Copiar texto", expanded=False):
            st.code(text, language=None)

    elif role == "assistant":
        html_content = _md_to_html(text, nl2br=False)
        st.markdown(
            f'<div class="msg-role">Assistente · {_html.escape(ts)}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(f'<div class="msg-assistant">{html_content}</div>', unsafe_allow_html=True)
        with st.expander("📋 Copiar texto", expanded=False):
            st.code(text, language=None)

    elif role == "tool":
        with st.expander(f"🔧 {tool or 'tool'} · {_html.escape(ts)}", expanded=False):
            st.code(text, language=None)
            if m.get("tool_input"):
                st.caption("Argumentos:")
                try:
                    st.json(json.loads(m["tool_input"]))
                except Exception:
                    st.code(m["tool_input"], language=None)


# ---------------------------------------------------------------------------
# Tab 1: Conversa
# ---------------------------------------------------------------------------
def tab_conversa(session: dict, ws_paths: dict[str, str] | None = None) -> None:
    # Header da sessão
    ws_hash   = session.get("workspace_hash", "")
    ws_folder = (ws_paths or {}).get(ws_hash, "") if ws_hash else ""
    src_badge = _source_badge(session["source"])
    ws_info   = f" · 📁 <code>{_html.escape(Path(ws_folder).name or ws_folder)}</code>" if ws_folder else ""
    tid_short = session["thread_id"][:16]

    st.markdown(
        f'<div class="sess-header">'
        f'<div class="sess-header-title">{_html.escape(session["title"])}</div>'
        f'<div class="sess-header-meta">'
        f'{src_badge}{ws_info} · '
        f'<span style="font-family:monospace;font-size:.72rem;color:#666">{tid_short}…</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # Stats bar colorida
    st.markdown(
        f'<div class="stat-bar">'
        f'<div class="stat-item"><span class="stat-value stat-blue">{session["user_turns"]}</span>'
        f'<span class="stat-label">Perguntas</span></div>'
        f'<div class="stat-item"><span class="stat-value stat-green">{session["assistant_turns"]}</span>'
        f'<span class="stat-label">Respostas</span></div>'
        f'<div class="stat-item"><span class="stat-value stat-yellow">{session["tool_calls"]}</span>'
        f'<span class="stat-label">Tool calls</span></div>'
        f'<div class="stat-item"><span class="stat-value stat-gray">{_html.escape(session["date_label"])}</span>'
        f'<span class="stat-label">Data</span></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Exportação JSON
    payload    = build_session_json(session)
    safe_title = _safe_filename(session["title"])
    fname      = f"{session['date_label']}_{safe_title}.json"
    json_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    n_exchanges = len(payload["session"]["exchanges"])
    ws_chat_dir = Path(ws_folder) / "_chatsession" if ws_folder else None

    bcol, ccol = st.columns([1, 5])
    save_local = bcol.checkbox(
        "📂 Salvar no workspace",
        value=False,
        disabled=ws_chat_dir is None,
        help=str(ws_chat_dir) if ws_chat_dir else "Workspace não identificado para esta sessão.",
    )

    if save_local and ws_chat_dir is not None:
        if bcol.button("⬇️ Salvar arquivo", use_container_width=True):
            try:
                ws_chat_dir.mkdir(parents=True, exist_ok=True)
                dest = ws_chat_dir / fname
                dest.write_bytes(json_bytes)
                st.success(f"✅ Salvo em: `{dest}`")
            except Exception as exc:
                st.error(f"Erro ao salvar: {exc}")
        ccol.caption(f"`{fname}` · {n_exchanges} exchange(s) · schema v1.0\n\n📁 `{ws_chat_dir}`")
    else:
        bcol.download_button(
            label="⬇️ Exportar JSON",
            data=json_bytes,
            file_name=fname,
            mime="application/json",
            use_container_width=True,
        )
        ccol.caption(
            f"`{fname}` · {n_exchanges} exchange(s) · schema v1.0 · BRT -03:00"
            + (f" · `{Path(ws_folder).name}`" if ws_folder else "")
        )

    st.divider()

    msgs = session["messages"]
    if not msgs:
        st.markdown(
            '<div class="empty-state">'
            '<div class="empty-state-icon">💬</div>'
            '<div class="empty-state-text">Nenhuma mensagem encontrada para esta sessão.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    show_tools = st.checkbox("Mostrar tool calls", value=False)
    for m in msgs:
        if m.get("role") == "tool" and not show_tools:
            continue
        render_message(m)


# ---------------------------------------------------------------------------
# Tab 2: Diário de Atividades
# ---------------------------------------------------------------------------
def tab_diario(sessions: dict[str, dict]) -> None:
    st.subheader("Diário de Atividades")
    st.caption("Sessões agrupadas por dia — ideal para documentar o que foi feito.")

    search_col, from_col, to_col = st.columns([2, 1, 1])
    text_filter = search_col.text_input("🔍 Buscar por título ou thread ID", "", key="diario_search")
    date_from_val = from_col.date_input("De:", value=None, key="diario_from", format=_DATE_FMT)
    date_to_val   = to_col.date_input("Até:", value=None, key="diario_to", format=_DATE_FMT)

    date_from = date_from_val.isoformat() if date_from_val else None
    date_to   = date_to_val.isoformat() if date_to_val else None

    def _matches(s: dict) -> bool:
        if not text_filter:
            return True
        q = text_filter.lower()
        return q in s["title"].lower() or q in s["thread_id"].lower() or q in s.get("source", "").lower()

    by_date: dict[str, list[dict]] = defaultdict(list)
    for s in sessions.values():
        d = s["date_label"]
        if not d or d == "—":
            continue
        if date_from and d < date_from:
            continue
        if date_to and d > date_to:
            continue
        if not _matches(s):
            continue
        by_date[d].append(s)

    ordered_dates = sorted(by_date.keys(), reverse=True)

    if not ordered_dates:
        st.markdown(
            '<div class="empty-state">'
            '<div class="empty-state-icon">🔍</div>'
            '<div class="empty-state-text">Nenhuma sessão encontrada para os filtros aplicados.<br>'
            'Tente ampliar o intervalo de datas ou limpar a busca.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    total_found = sum(len(v) for v in by_date.values())
    st.caption(f"{total_found} sessão(ões) em {len(ordered_dates)} dia(s)")

    for day in ordered_dates:
        day_sessions = sorted(by_date[day], key=lambda s: s["last_ts"], reverse=True)
        day_user  = sum(s["user_turns"] for s in day_sessions)
        day_asst  = sum(s["assistant_turns"] for s in day_sessions)
        try:
            day_dt = datetime.fromisoformat(day)
            wk_map = {
                "Monday": "Segunda-feira", "Tuesday": "Terça-feira",
                "Wednesday": "Quarta-feira", "Thursday": "Quinta-feira",
                "Friday": "Sexta-feira", "Saturday": "Sábado", "Sunday": "Domingo",
            }
            day_label = f"{wk_map.get(day_dt.strftime('%A'), day_dt.strftime('%A'))}, {day_dt.strftime('%d/%m/%Y')}"
        except Exception:
            day_label = day

        st.markdown(
            f'<div class="day-header">📅 {day_label} &nbsp;'
            f'<span style="font-weight:400;color:#aaa;font-size:.82rem;">'
            f'({len(day_sessions)} sessão/sessões · {day_user}U {day_asst}A)</span></div>',
            unsafe_allow_html=True,
        )

        for s in day_sessions:
            title = s["title"]
            u, a  = s["user_turns"], s["assistant_turns"]
            src   = s["source"]
            ts    = ts_to_label(s["last_ts"])
            tid   = s["thread_id"]

            # Destaca o termo buscado no título (com escape XSS)
            safe_title = _html.escape(title)
            if text_filter and text_filter.lower() in title.lower():
                idx = title.lower().find(text_filter.lower())
                hl  = _html.escape(title[idx:idx + len(text_filter)])
                safe_title = safe_title.replace(
                    hl,
                    f'<mark style="background:#5a4a00;color:#ffd">{hl}</mark>',
                    1,
                )

            entry_col, btn_col = st.columns([11, 1])
            entry_col.markdown(
                f'<div class="diary-session">'
                f'<span class="diary-session-title">• {safe_title}</span>'
                f' {_source_badge(src)}'
                f'<br><span class="diary-meta">'
                f'{_html.escape(ts)} · {u} perguntas · {a} respostas'
                f' · <span style="font-family:monospace;font-size:.72rem;color:#666">{_html.escape(tid[:16])}…</span>'
                f'</span></div>',
                unsafe_allow_html=True,
            )
            if btn_col.button("↗", key=f"goto_{tid}", help="Abrir no Conversa"):
                st.session_state["_pending_tid"]   = tid
                st.session_state["_goto_conversa"] = True
                st.rerun()


# ---------------------------------------------------------------------------
# Tab 3: Workspaces
# ---------------------------------------------------------------------------
def tab_workspaces(workspaces: list[dict]) -> None:
    st.subheader("Workspaces")
    if not workspaces:
        st.markdown(
            '<div class="empty-state">'
            '<div class="empty-state-icon">🗂️</div>'
            '<div class="empty-state-text">Nenhum workspace encontrado.<br>'
            'Execute o pipeline para atualizar os dados.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    st.caption(f"{len(workspaces)} workspace(s) com sessões de chat registradas.")
    search = st.text_input("🔍 Filtrar por pasta", "", key="ws_search")
    filtered = [
        w for w in workspaces
        if not search or search.lower() in w["folder"].lower() or search.lower() in w["hash"].lower()
    ]

    if not filtered:
        st.warning("Nenhum workspace encontrado para o filtro aplicado.")
        return

    for w in filtered:
        folder   = w["folder"]
        h        = w["hash"]
        n_sess   = len(w["sessions"])
        last_dt  = w["last_ts"][:10] if w["last_ts"] else "—"
        first_dt = w["first_ts"][:10] if w["first_ts"] else "—"
        u, a     = w["total_user"], w["total_assistant"]

        st.markdown(
            f'<div class="ws-card">'
            f'<div class="ws-folder">📁 {_html.escape(folder)}</div>'
            f'<div class="ws-hash">{_html.escape(h)}</div>'
            f'<div class="ws-meta">'
            f'Primeira sessão: {first_dt} &nbsp;·&nbsp; Última: {last_dt} &nbsp;·&nbsp; '
            f'{n_sess} sessão(ões) &nbsp;·&nbsp; {u} perguntas &nbsp;·&nbsp; {a} respostas'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        with st.expander(f"Ver {n_sess} sessão(ões) de '{folder.split(chr(92))[-1] or folder}'", expanded=False):
            for sess in w["sessions"]:
                dt  = sess["last_ts"][:10] if sess["last_ts"] else "—"
                u_s = sess["user_turns"]
                a_s = sess["assistant_turns"]
                tid = sess["thread_id"][:12]
                st.markdown(
                    f'<div class="ws-sess-item">'
                    f'<b>{_html.escape(sess["title"])}</b>'
                    f' {_source_badge(sess["source"])}'
                    f'<br><span class="ws-sess-meta">'
                    f'{dt} · {u_s}U {a_s}A · {_html.escape(tid)}…'
                    f'</span></div>',
                    unsafe_allow_html=True,
                )


# ---------------------------------------------------------------------------
# App principal
# ---------------------------------------------------------------------------
def main() -> None:
    # Lê o tema ANTES de injetar o CSS (session_state persiste entre reruns)
    theme = st.session_state.get("theme", "dark")
    _inject_css(theme)

    # Resolve seleção pendente do Diário ANTES de qualquer widget ser criado.
    if "_pending_tid" in st.session_state:
        st.session_state["selected_tid"] = st.session_state.pop("_pending_tid")

    # JS para trocar para a aba Conversa quando solicitado do Diário
    if st.session_state.pop("_goto_conversa", False):
        import streamlit.components.v1 as components
        components.html(
            """<script>
            setTimeout(function(){
                var tabs=window.parent.document.querySelectorAll('[data-testid="stTab"]');
                if(tabs.length>0) tabs[0].click();
            },120);
            </script>""",
            height=0,
        )

    if not _SESSIONS_FILE.exists():
        st.error(
            f"Arquivo `sessions.jsonl` não encontrado em:\n`{_SESSIONS_FILE}`\n\n"
            "Execute o pipeline primeiro:\n```\npython pipeline/02_normalize/normalize.py\n```"
        )
        st.stop()

    messages, summaries = load_data()
    sessions   = build_session_index(messages, summaries)
    ws_paths   = load_workspace_paths()
    workspaces = build_workspace_index(summaries, ws_paths)

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------
    with st.sidebar:
        st.title("💬 Chat Viewer")
        st.caption(f"**{len(sessions)}** sessões carregadas")

        # Toggle de tema
        theme_label = "☀️ Tema claro" if theme == "dark" else "🌙 Tema escuro"
        if st.button(theme_label, use_container_width=True):
            st.session_state["theme"] = "light" if theme == "dark" else "dark"
            st.rerun()

        st.divider()

        search     = st.text_input("🔍 Buscar por título ou palavra-chave", "")
        sources    = sorted({s["source"] for s in sessions.values()})
        source_sel = st.multiselect("Fonte", sources, default=sources)
        hide_empty = st.checkbox("Ocultar sessões vazias", value=True)

        st.divider()

        # Filtro usando _search_text pré-computado (performance O(n_sessions))
        filtered = [
            s for s in sorted(sessions.values(), key=lambda s: s["last_ts"], reverse=True)
            if s["source"] in source_sel
            and (not hide_empty or s["user_turns"] > 0 or s["assistant_turns"] > 0)
            and (not search or search.lower() in s["_search_text"])
        ]

        st.caption(f"{len(filtered)} sessão(ões) encontrada(s)")

        if not filtered:
            st.markdown(
                '<div style="text-align:center;padding:20px;color:#666;font-size:.85rem;">'
                '🔍 Nenhuma sessão encontrada.<br>Tente outros termos de busca.</div>',
                unsafe_allow_html=True,
            )
            selected_tid = None
        else:
            options = [s["thread_id"] for s in filtered]
            labels  = {
                s["thread_id"]: f"{s['date_label']} — {s['title'][:38]}"
                for s in filtered
            }

            if (
                "selected_tid" not in st.session_state
                or st.session_state.selected_tid not in options
            ):
                first_with_content = next(
                    (s["thread_id"] for s in filtered if s["user_turns"] > 0 or s["assistant_turns"] > 0),
                    options[0],
                )
                st.session_state.selected_tid = first_with_content

            selected_tid = st.selectbox(
                "Sessão:",
                options,
                format_func=lambda t: labels.get(t) or str(t),
                key="selected_tid",
            )

        st.divider()

        # Botão de pipeline
        run_pipeline = st.button("🔄 Executar pipeline", use_container_width=True)
        pipeline_log = st.empty()

        if run_pipeline:
            _py     = Path(sys.executable)
            _script = _ROOT / "pipeline" / "run_pipeline.py"
            env     = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            lines: list[str] = []
            pipeline_log.info("Iniciando pipeline...")
            success = False
            try:
                with subprocess.Popen(
                    [str(_py), str(_script)],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, encoding="utf-8", errors="replace",
                    cwd=str(_ROOT), env=env,
                ) as proc:
                    for raw in proc.stdout:  # type: ignore[union-attr]
                        lines.append(raw.rstrip())
                        pipeline_log.code("\n".join(lines[-30:]), language="")
                    proc.wait()
                    success = proc.returncode == 0
            except Exception as exc:
                pipeline_log.error(f"Erro ao iniciar pipeline: {exc}")

            if success:
                pipeline_log.success("Pipeline concluído! Recarregando dados...")
                st.cache_data.clear()
                st.rerun()
            else:
                pipeline_log.error("Pipeline encerrou com erro. Veja o log acima.")

    # ------------------------------------------------------------------
    # Área principal — abas
    # ------------------------------------------------------------------
    if not sessions:
        st.markdown(
            '<div class="empty-state">'
            '<div class="empty-state-icon">📭</div>'
            '<div class="empty-state-text">Nenhuma sessão disponível.<br>'
            'Execute o pipeline para carregar os dados.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    tab1, tab2, tab3 = st.tabs(["💬 Conversa", "📅 Diário de Atividades", "🗂️ Workspaces"])

    with tab2:
        tab_diario(sessions)

    with tab3:
        tab_workspaces(workspaces)

    if selected_tid and selected_tid in sessions:
        session = sessions[selected_tid]
        with tab1:
            tab_conversa(session, ws_paths)
    else:
        with tab1:
            st.info("Selecione uma sessão na barra lateral.")


if __name__ == "__main__":
    main()
