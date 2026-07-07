Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
target = scriptDir & "\production version\start_hidden.vbs"
If fso.FileExists(target) Then
  shell.Run "wscript.exe """ & target & """", 0, False
Else
  MsgBox "Production version was not found: " & target, 16, "Automat"
End If
