<#
.SYNOPSIS
    Configura e cria o atalho "Chat VS Pipeline" na Area de Trabalho.

.DESCRIPTION
    1. Instala a dependencia `pystray` no venv (se ainda nao presente).
    2. Gera o icone .ico via PIL (launcher.py).
    3. Cria o atalho .lnk na Area de Trabalho apontando para run_tray.vbs.

.EXAMPLE
    .\create_shortcut.ps1
#>

$ErrorActionPreference = "Stop"

$scriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$pythonExe  = Join-Path $scriptDir ".venv\Scripts\python.exe"
$vbsPath    = Join-Path $scriptDir "run_tray.vbs"
$icoPath    = Join-Path $scriptDir "VS-Code.ico"

Write-Host ""
Write-Host "=== Chat VS Pipeline — Criacao do atalho ===" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------------------
# 1. Verificar/instalar pystray
# ---------------------------------------------------------------------------
Write-Host "[1/3] Verificando dependencia pystray..." -NoNewline

$checkResult = & $pythonExe -c "import pystray; print('ok')" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host " instalando..."
    & $pythonExe -m pip install "pystray>=0.19" --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Falha ao instalar pystray. Verifique a conexao e o venv."
        exit 1
    }
    Write-Host "   pystray instalado." -ForegroundColor Green
} else {
    Write-Host " ok." -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# 2. Verificar icone
# ---------------------------------------------------------------------------
Write-Host "[2/3] Verificando icone $icoPath..." -NoNewline

if (-not (Test-Path $icoPath)) {
    Write-Error "Arquivo de icone nao encontrado: $icoPath"
    exit 1
}
Write-Host " ok." -ForegroundColor Green

# ---------------------------------------------------------------------------
# 3. Criar atalho .lnk na Area de Trabalho
# ---------------------------------------------------------------------------
Write-Host "[3/3] Criando atalho na Area de Trabalho..." -NoNewline

$desktopPath  = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "Chat VS Pipeline.lnk"

$wshShell = New-Object -ComObject WScript.Shell
$shortcut = $wshShell.CreateShortcut($shortcutPath)

$shortcut.TargetPath       = "wscript.exe"
$shortcut.Arguments        = "`"$vbsPath`""
$shortcut.WorkingDirectory = $scriptDir
$shortcut.WindowStyle      = 7          # SW_SHOWMINNOACTIVE — minimizado/oculto
$shortcut.Description      = "Chat VS Pipeline — Sincronizacao e Viewer"
$shortcut.IconLocation     = "$icoPath,0"
$shortcut.Save()

Write-Host " ok." -ForegroundColor Green
Write-Host ""
Write-Host "Atalho criado em:" -ForegroundColor White
Write-Host "  $shortcutPath" -ForegroundColor Yellow
Write-Host ""
Write-Host "Pronto! Clique duas vezes no atalho para iniciar." -ForegroundColor Green
Write-Host ""
