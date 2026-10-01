Option Explicit

Dim shell, fso, folder, ps1, exePath, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

folder = fso.GetParentFolderName(WScript.ScriptFullName)
exePath = folder & "\Compet.exe"
ps1 = folder & "\GamepadBridge.ps1"

If Not fso.FileExists(exePath) Then
    MsgBox "Compet.exe not found.", 16, "Compet Xbox"
    WScript.Quit 1
End If

If Not fso.FileExists(ps1) Then
    MsgBox "GamepadBridge.ps1 not found.", 16, "Compet Xbox"
    WScript.Quit 1
End If

shell.CurrentDirectory = folder
shell.Run Chr(34) & exePath & Chr(34), 0, False
WScript.Sleep 1500

cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " & Chr(34) & ps1 & Chr(34)
shell.Run cmd, 0, False

Set fso = Nothing
Set shell = Nothing
