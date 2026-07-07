Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
target = scriptDir & "\produkcni verze\start_hidden.vbs"
If fso.FileExists(target) Then
  shell.Run "wscript.exe """ & target & """", 0, False
Else
  MsgBox "Produkcni verze nebyla nalezena: " & target, 16, "Automat"
End If
