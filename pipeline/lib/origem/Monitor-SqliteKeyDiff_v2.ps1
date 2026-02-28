<#
.SYNOPSIS
    Monitora mudancas de chaves no SQLite state.vscdb e grava diffs em JSONL.

.DESCRIPTION
    Quando um DB alvo muda, o script re-le as chaves filtradas e registra:
    - key_added
    - key_modified
    - key_removed
    Tambem registra um evento de resumo por varredura.

.EXAMPLE
    .\Monitor-SqliteKeyDiff_v2.ps1 -DurationSeconds 300 -IntervalMs 500

.EXAMPLE
    .\Monitor-SqliteKeyDiff_v2.ps1 `
      -DurationSeconds 600 `
      -IntervalMs 500 `
      -KeyIncludeRegex '(?i)openai\\.chatgpt|agentSessions|chat\\.|codex|memento/webviewView\\.chatgpt|workbench\\.find\\.history' `
      -OutputFile '.\_resumo\_v1\sqlite_keydiff_019c7d28.jsonl'
#>

param(
    [string[]]$DbPaths = @(
        "$env:APPDATA\Code\User\globalStorage\state.vscdb",
        "$env:APPDATA\Code\User\workspaceStorage\0bcf0a9aa1fe149bdfe3a51f4a4236b5\state.vscdb"
    ),
    [string]$KeyIncludeRegex = '(?i)openai\.chatgpt|agentSessions|chat\.|codex|memento/webviewView\.chatgpt|workbench\.find\.history',
    [int]$DurationSeconds = 300,
    [int]$IntervalMs = 500,
    [string]$OutputFile = ".\_resumo\_v1\sqlite_keydiff_v2.jsonl"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Normalize-FullPath {
    param([string]$Path)
    try {
        return [System.IO.Path]::GetFullPath($Path)
    } catch {
        return $Path
    }
}

function Invoke-PythonStdin {
    param(
        [string]$Script,
        [string[]]$PyArgs = @()
    )

    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        return $null
    }

    $argList = @("-") + $PyArgs
    try {
        return ($Script | & $python.Source @argList 2>$null)
    } catch {
        return $null
    }
}

function Get-DbFileState {
    param([string]$DbPath)
    if (-not (Test-Path -LiteralPath $DbPath)) {
        return $null
    }
    $item = Get-Item -LiteralPath $DbPath -Force
    return [PSCustomObject]@{
        Length = [int64]$item.Length
        LastWriteTicks = [int64]$item.LastWriteTimeUtc.Ticks
        LastWriteUtc = $item.LastWriteTimeUtc.ToString("o")
    }
}

function Get-SqliteKeySnapshot {
    param(
        [string]$DbPath,
        [string]$KeyRegex
    )

    if (-not (Test-Path -LiteralPath $DbPath)) {
        return @()
    }

    $py = @"
import hashlib
import json
import re
import sqlite3
import sys

db_path = sys.argv[1]
key_regex = sys.argv[2]
rx = re.compile(key_regex)

con = sqlite3.connect(db_path)
cur = con.cursor()

def trunc_text(value, limit=220):
    if value is None:
        return ""
    txt = str(value).replace("\r", " ").replace("\n", " ")
    if len(txt) > limit:
        return txt[:limit]
    return txt

def summarize_value(key, txt):
    summary = {}
    try:
        obj = json.loads(txt)
    except Exception:
        return summary

    if key == "openai.chatgpt" and isinstance(obj, dict):
        persisted = obj.get("persisted-atom-state")
        if not isinstance(persisted, dict):
            persisted = {}
        prompt_history = persisted.get("prompt-history")
        if not isinstance(prompt_history, list):
            prompt_history = []
        summary["prompt_history_len"] = len(prompt_history)
        if prompt_history:
            summary["prompt_last"] = trunc_text(prompt_history[-1], 200)

        thread_titles = obj.get("thread-titles")
        if not isinstance(thread_titles, dict):
            thread_titles = {}
        titles = thread_titles.get("titles")
        if not isinstance(titles, dict):
            titles = {}
        order = thread_titles.get("order")
        if not isinstance(order, list):
            order = []
        summary["thread_titles_len"] = len(titles)
        summary["thread_order_len"] = len(order)

        queued = obj.get("queued-follow-ups")
        summary["queued_followups_len"] = len(queued) if isinstance(queued, list) else 0
        summary["persisted_keys_len"] = len(persisted.keys())

    elif key == "agentSessions.model.cache" and isinstance(obj, list):
        summary["entries_len"] = len(obj)
        provider_counts = {}
        latest_created = None
        latest_label = None
        for item in obj:
            if not isinstance(item, dict):
                continue
            provider = item.get("providerType") or "unknown"
            provider_counts[provider] = provider_counts.get(provider, 0) + 1

            timing = item.get("timing")
            created = None
            if isinstance(timing, dict):
                raw_created = timing.get("created")
                if isinstance(raw_created, (int, float)):
                    created = int(raw_created)

            if created is not None and (latest_created is None or created > latest_created):
                latest_created = created
                latest_label = item.get("label")

        summary["provider_counts"] = provider_counts
        if latest_created is not None:
            summary["latest_created_ms"] = latest_created
            summary["latest_label"] = trunc_text(latest_label, 180)

    elif key == "agentSessions.state.cache" and isinstance(obj, list):
        summary["entries_len"] = len(obj)
        openai_codex_resources = 0
        archived_true = 0
        for item in obj:
            if not isinstance(item, dict):
                continue
            resource = item.get("resource")
            if isinstance(resource, str) and resource.startswith("openai-codex://"):
                openai_codex_resources += 1
            if item.get("archived") is True:
                archived_true += 1
        summary["openai_codex_resources"] = openai_codex_resources
        summary["archived_true"] = archived_true

    elif key == "chat.ChatSessionStore.index" and isinstance(obj, dict):
        entries = obj.get("entries")
        if isinstance(entries, dict):
            summary["entries_len"] = len(entries)
            max_last_message = None
            max_title = None
            for _sid, item in entries.items():
                if not isinstance(item, dict):
                    continue
                last_msg = item.get("lastMessageDate")
                if isinstance(last_msg, (int, float)):
                    last_msg = int(last_msg)
                    if max_last_message is None or last_msg > max_last_message:
                        max_last_message = last_msg
                        max_title = item.get("title")
            if max_last_message is not None:
                summary["max_lastMessageDate"] = max_last_message
                summary["max_title"] = trunc_text(max_title, 180)

    return summary

rows = []
for key, value in cur.execute("SELECT key, value FROM ItemTable"):
    if not rx.search(key):
        continue
    if value is None:
        txt = ""
    elif isinstance(value, bytes):
        txt = value.decode("utf-8", "replace")
    else:
        txt = str(value)

    data = txt.encode("utf-8", "replace")
    sha1 = hashlib.sha1(data).hexdigest()
    preview = txt.replace("\r", " ").replace("\n", " ")
    if len(preview) > 220:
        preview = preview[:220]
    summary = summarize_value(key, txt)

    rows.append({
        "key": key,
        "len": len(txt),
        "sha1": sha1,
        "preview": preview,
        "summary": summary
    })

con.close()
print(json.dumps(rows, ensure_ascii=False))
"@

    $raw = Invoke-PythonStdin -Script $py -PyArgs @($DbPath, $KeyRegex)
    if (-not $raw) {
        return @()
    }
    $json = $raw -join "`n"
    try {
        return @($json | ConvertFrom-Json -ErrorAction Stop)
    } catch {
        return @()
    }
}

function To-KeyMap {
    param($Rows)
    $map = @{}
    foreach ($r in @($Rows)) {
        if (-not $r.key) { continue }
        $map[[string]$r.key] = $r
    }
    return $map
}

function Get-SummaryDiff {
    param(
        $BeforeSummary,
        $AfterSummary
    )

    $beforeMap = @{}
    if ($BeforeSummary) {
        foreach ($p in $BeforeSummary.PSObject.Properties) {
            $beforeMap[$p.Name] = $p.Value
        }
    }

    $afterMap = @{}
    if ($AfterSummary) {
        foreach ($p in $AfterSummary.PSObject.Properties) {
            $afterMap[$p.Name] = $p.Value
        }
    }

    $allKeys = @($beforeMap.Keys + $afterMap.Keys | Select-Object -Unique)
    $diff = [ordered]@{}

    foreach ($k in $allKeys) {
        $hasBefore = $beforeMap.ContainsKey($k)
        $hasAfter = $afterMap.ContainsKey($k)

        if (-not $hasBefore -and $hasAfter) {
            $diff[$k] = [ordered]@{ before = $null; after = $afterMap[$k] }
            continue
        }
        if ($hasBefore -and -not $hasAfter) {
            $diff[$k] = [ordered]@{ before = $beforeMap[$k]; after = $null }
            continue
        }

        $beforeJson = $beforeMap[$k] | ConvertTo-Json -Compress -Depth 10
        $afterJson = $afterMap[$k] | ConvertTo-Json -Compress -Depth 10
        if ($beforeJson -ne $afterJson) {
            $diff[$k] = [ordered]@{ before = $beforeMap[$k]; after = $afterMap[$k] }
        }
    }

    if ($diff.Count -eq 0) {
        return $null
    }
    return $diff
}

function Append-Jsonl {
    param(
        [string]$Path,
        $Object
    )
    $line = $Object | ConvertTo-Json -Compress -Depth 12
    Add-Content -LiteralPath $Path -Value $line -Encoding UTF8
}

$resolvedDbPaths = @()
foreach ($db in $DbPaths) {
    if (-not $db) { continue }
    $resolvedDbPaths += (Normalize-FullPath -Path $db)
}
$resolvedDbPaths = @($resolvedDbPaths | Select-Object -Unique)

$outFull = Normalize-FullPath -Path $OutputFile
$outDir = Split-Path -Parent $outFull
if ($outDir -and -not (Test-Path -LiteralPath $outDir)) {
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
}
if (Test-Path -LiteralPath $outFull) {
    Remove-Item -LiteralPath $outFull -Force
}
New-Item -ItemType File -Path $outFull -Force | Out-Null

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python nao encontrado no PATH."
}

$meta = [ordered]@{
    startedAtUtc = (Get-Date).ToUniversalTime().ToString("o")
    durationSeconds = $DurationSeconds
    intervalMs = $IntervalMs
    dbPaths = $resolvedDbPaths
    keyIncludeRegex = $KeyIncludeRegex
    outputFile = $outFull
}
Append-Jsonl -Path $outFull -Object $meta

Write-Host ""
Write-Host "============================================================" -ForegroundColor Blue
Write-Host "   SQLite Key Diff Monitor (v2)" -ForegroundColor Blue
Write-Host "============================================================" -ForegroundColor Blue
Write-Host "Duracao  : $DurationSeconds s" -ForegroundColor Cyan
Write-Host "Intervalo: $IntervalMs ms" -ForegroundColor Cyan
Write-Host "Regex    : $KeyIncludeRegex" -ForegroundColor Cyan
Write-Host "Saida    : $outFull" -ForegroundColor Cyan
Write-Host ""
Write-Host "DBs monitorados:" -ForegroundColor Yellow
foreach ($db in $resolvedDbPaths) {
    Write-Host " - $db" -ForegroundColor DarkYellow
}
Write-Host ""

# Baseline inicial
$dbState = @{}
foreach ($db in $resolvedDbPaths) {
    $fileState = Get-DbFileState -DbPath $db
    $rows = Get-SqliteKeySnapshot -DbPath $db -KeyRegex $KeyIncludeRegex
    $dbState[$db] = [PSCustomObject]@{
        FileState = $fileState
        Map = To-KeyMap -Rows $rows
    }
}

$start = Get-Date
$deadline = $start.AddSeconds($DurationSeconds)
$eventCount = 0

while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds $IntervalMs

    foreach ($db in $resolvedDbPaths) {
        $previous = $dbState[$db]
        $currFileState = Get-DbFileState -DbPath $db

        if (-not $currFileState -and -not $previous.FileState) {
            continue
        }

        $fileChanged = $false
        if (-not $previous.FileState -and $currFileState) {
            $fileChanged = $true
        } elseif ($previous.FileState -and -not $currFileState) {
            $fileChanged = $true
        } elseif ($previous.FileState -and $currFileState) {
            if ($previous.FileState.LastWriteTicks -ne $currFileState.LastWriteTicks -or
                $previous.FileState.Length -ne $currFileState.Length) {
                $fileChanged = $true
            }
        }

        if (-not $fileChanged) {
            continue
        }

        $currentRows = Get-SqliteKeySnapshot -DbPath $db -KeyRegex $KeyIncludeRegex
        $currentMap = To-KeyMap -Rows $currentRows
        $prevMap = $previous.Map

        $added = 0
        $modified = 0
        $removed = 0

        foreach ($k in $currentMap.Keys) {
            if (-not $prevMap.ContainsKey($k)) {
                $added++
                $eventCount++
                Append-Jsonl -Path $outFull -Object ([ordered]@{
                    tsUtc = (Get-Date).ToUniversalTime().ToString("o")
                    event = "key_added"
                    dbPath = $db
                    key = $k
                    before = $null
                    after = $currentMap[$k]
                })
                continue
            }

            $before = $prevMap[$k]
            $after = $currentMap[$k]
            if ($before.sha1 -ne $after.sha1) {
                $modified++
                $eventCount++
                $summaryDiff = Get-SummaryDiff -BeforeSummary $before.summary -AfterSummary $after.summary
                Append-Jsonl -Path $outFull -Object ([ordered]@{
                    tsUtc = (Get-Date).ToUniversalTime().ToString("o")
                    event = "key_modified"
                    dbPath = $db
                    key = $k
                    before = [ordered]@{
                        len = $before.len
                        sha1 = $before.sha1
                        preview = $before.preview
                        summary = $before.summary
                    }
                    after = [ordered]@{
                        len = $after.len
                        sha1 = $after.sha1
                        preview = $after.preview
                        summary = $after.summary
                    }
                    summaryDiff = $summaryDiff
                })
            }
        }

        foreach ($k in $prevMap.Keys) {
            if (-not $currentMap.ContainsKey($k)) {
                $removed++
                $eventCount++
                $before = $prevMap[$k]
                Append-Jsonl -Path $outFull -Object ([ordered]@{
                    tsUtc = (Get-Date).ToUniversalTime().ToString("o")
                    event = "key_removed"
                    dbPath = $db
                    key = $k
                    before = [ordered]@{
                        len = $before.len
                        sha1 = $before.sha1
                        preview = $before.preview
                        summary = $before.summary
                    }
                    after = $null
                })
            }
        }

        if ($added -gt 0 -or $modified -gt 0 -or $removed -gt 0) {
            $eventCount++
            Append-Jsonl -Path $outFull -Object ([ordered]@{
                tsUtc = (Get-Date).ToUniversalTime().ToString("o")
                event = "db_scan_summary"
                dbPath = $db
                fileLength = if ($currFileState) { $currFileState.Length } else { $null }
                fileLastWriteUtc = if ($currFileState) { $currFileState.LastWriteUtc } else { $null }
                keysAdded = $added
                keysModified = $modified
                keysRemoved = $removed
                keyCount = $currentMap.Count
            })
        }

        $dbState[$db] = [PSCustomObject]@{
            FileState = $currFileState
            Map = $currentMap
        }
    }
}

$finish = Get-Date
Write-Host ""
Write-Host "Monitoramento finalizado." -ForegroundColor Green
Write-Host "Inicio : $($start.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Gray
Write-Host "Fim    : $($finish.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Gray
Write-Host "Eventos: $eventCount" -ForegroundColor Green
Write-Host "Arquivo: $outFull" -ForegroundColor Green
Write-Host ""
