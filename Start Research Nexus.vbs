Option Explicit
Dim shell, fso, root, exe
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
exe = root & "\node_modules\electron\dist\electron.exe"
If Not fso.FileExists(exe) Then
  MsgBox "Electron runtime not found. See README.md for setup instructions.", 48, "Research Nexus"
  WScript.Quit 1
End If
shell.CurrentDirectory = root
shell.Run Chr(34) & exe & Chr(34) & " " & Chr(34) & root & Chr(34), 1, False
