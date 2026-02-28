# VS Code Chat History

> Extract, normalize, and visualize your complete AI conversation history from VS Code — locally, without sending anything to the internet.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Windows](https://img.shields.io/badge/Platform-Windows-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-MVP-orange)

🌐 **Language / Idioma:** [Português (BR)](README.md) | English

---

## ⚠️ Status: MVP — Local Use Only

**This is a personal tool in early stage (MVP).**  
It works well for its intended purpose, but is not yet production-ready.

- 🖥️ **Windows only** — uses AppData paths and PowerShell scripts; macOS/Linux not tested
- 🔒 **100% local data** — no information ever leaves your machine (see [SECURITY.md](SECURITY.md))
- 🧪 **MVP** — may have unexpected behavior with unmapped session formats

---

## What is it

VS Code stores the Copilot Chat history (and other AI assistants) in SQLite and JSONL files inside `%APPDATA%\Code\User\`. This tool:

1. **Copies** those files into an isolated local snapshot
2. **Normalizes** the data (reconstructing incremental patches from active sessions)
3. **Exposes** an interactive Streamlit viewer to browse, search and export conversations

```
VS Code AppData
       │
       ▼
 01_ingest   → read-only snapshot + automatic cleanup (keeps 2)
       │
       ▼
 02_normalize → sessions.jsonl + summaries.jsonl
       │
       ▼
 03_report   → JSONL and text reports
       │
       ▼
 viewer/app.py → http://localhost:8502
```

---

## Features

- ✅ Reads 5 distinct VS Code sources: `chat_session_json`, `chat_session_jsonl`, `agent_sessions`, `chat_session_index`, `openai_chatgpt`
- ✅ Reconstructs active sessions (open workspaces) from incremental JSONL patches
- ✅ Streamlit viewer with 3 tabs: **Conversation**, **Activity Log**, **Workspaces**
- ✅ Light/dark theme toggle
- ✅ Color-coded source badges · stat bar · pre-computed search index
- ✅ Structured JSON export (schema v1.0) per session
- ✅ "📋 Copy text" button and expandable tool calls per message
- ✅ 🔄 button to run the pipeline directly from the viewer
- ✅ Streamlit telemetry disabled (`gatherUsageStats = false`)

---

## Prerequisites

- Windows 10 or 11
- Python 3.10 or higher ([python.org](https://www.python.org/downloads/))
- VS Code with GitHub Copilot Chat installed and with history generated
- Git ([git-scm.com](https://git-scm.com/downloads))

---

## Installation

```powershell
# 1. Clone the repository
git clone https://github.com/jesustdmen/vscode-chat-history.git
cd vscode-chat-history

# 2. Create the virtual environment
python -m venv .venv
.venv\Scripts\pip install --upgrade pip

# 3. Install dependencies
.venv\Scripts\pip install -r requirements.txt

# 4. Register the package locally (required once)
.venv\Scripts\pip install -e .
```

---

## Usage

### Full pipeline (recommended)

```powershell
$env:PYTHONUTF8="1"; .venv\Scripts\python.exe pipeline/run_pipeline.py
```

### Individual options

```powershell
# Re-normalize only (no new snapshot)
$env:PYTHONUTF8="1"; .venv\Scripts\python.exe pipeline/run_pipeline.py --skip-ingest

# Reports only
$env:PYTHONUTF8="1"; .venv\Scripts\python.exe pipeline/run_pipeline.py --only-report
```

### Viewer

```powershell
$env:PYTHONUTF8="1"; .venv\Scripts\streamlit.exe run pipeline/viewer/app.py
```

Open **http://localhost:8502** in your browser.

> **Why `$env:PYTHONUTF8="1"`?**  
> Required on Windows to correctly process emojis and special characters (UTF-8) in the terminal.

---

## Project Structure

```
vscode-chat-history/
├── .streamlit/
│   └── config.toml          # Telemetry disabled · port 8502 · localhost
├── pipeline/
│   ├── run_pipeline.py      # Orchestrator: ingest → normalize → report
│   ├── 01_ingest/
│   │   └── ingest.py        # Read-only copy + automatic snapshot cleanup
│   ├── 02_normalize/
│   │   ├── normalize.py     # Orchestration (discovers sources, emits sessions/summaries)
│   │   ├── parsers.py       # Parsers by source (openai, agent, index, json, jsonl)
│   │   ├── aggregator.py    # build_summaries(): ChatMessage → SessionSummary
│   │   └── patch.py         # JSONL patch reconstruction (kind 0/1/2)
│   ├── 03_report/
│   │   └── report.py        # JSONL and text reports
│   ├── lib/
│   │   ├── config.py        # Paths and constants (with APPDATA validation)
│   │   ├── models.py        # Dataclasses: ChatMessage + SessionSummary
│   │   ├── db_reader.py     # Read-only SQLite access
│   │   └── patch.py         # Patch reconstruction helpers
│   ├── viewer/
│   │   └── app.py           # Streamlit interface
│   └── output/              # ⚠️ Generated — never version (see .gitignore)
│       ├── raw/             # Raw snapshots (only 2 kept)
│       ├── normalized/      # sessions.jsonl · summaries.jsonl
│       └── reports/         # conversations · topics · tool_calls · timeline
├── _dev/                    # Local personal files — never versioned
├── pyproject.toml
├── requirements.txt
├── CHANGELOG.md
├── SECURITY.md
└── README.md
```

---

## Known Limitations

| Limitation | Detail |
|---|---|
| Windows only | `%APPDATA%` paths and `.ps1` scripts; no tested support for macOS/Linux |
| GitHub Copilot Chat only | Other assistants (Continue, Codeium, etc.) are not parsed |
| No authentication | The viewer runs locally without a password — do not expose on a public network |
| Very old sessions | Some pre-2025 sessions may have an unmapped format |

---

## Roadmap

- [ ] **PostgreSQL via Docker** — migrate to a relational database with upsert
- [ ] **`chatEditingSessions`** — file edit history per session
- [ ] **Support for other assistants** — parsers for Blackbox AI, Continue and others

---

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide.

**Quick summary:**
1. Fork the repo
2. Create a branch: `git checkout -b feat/my-feature`
3. Commit: `git commit -m "feat: description of change"`
4. Push: `git push origin feat/my-feature`
5. Open a Pull Request to the `main` branch

---

## Security & Privacy

This tool reads personal files from your VS Code. See [SECURITY.md](SECURITY.md) to understand what is accessed, what never goes to Git, and how to audit the code.

---

## License

Distributed under the [MIT License](LICENSE).

---

## Author

**Jesus Teles** — Just an enthusiast who is blown away by vibecoding.

Built with [GitHub Copilot](https://github.com/features/copilot) (Claude Sonnet 4.6).

Feedback, issues and ⭐ are very welcome!
