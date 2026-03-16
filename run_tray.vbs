' run_tray.vbs
' Inicia o launcher.py usando pythonw.exe (sem janela de terminal).
' Usado como alvo intermediario do atalho no Desktop.

Option Explicit

Dim fso, scriptDir, pythonw, launcherScript, wsh

Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir      = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw        = scriptDir & "\.venv\Scripts\pythonw.exe"
launcherScript = scriptDir & "\launcher.py"

Set wsh = CreateObject("WScript.Shell")
wsh.CurrentDirectory = scriptDir

' WindowStyle=0: sem janela; bWaitOnReturn=False: nao bloqueia
wsh.Run Chr(34) & pythonw & Chr(34) & " " & Chr(34) & launcherScript & Chr(34), 0, False
