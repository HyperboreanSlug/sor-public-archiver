' Double-click this file to start the GUI without a lingering console.
' Uses run_gui.bat so the correct Python + dependencies are used.
Option Explicit
Dim sh, fso, dir, bat, rc
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
bat = dir & "\run_gui.bat"
If Not fso.FileExists(bat) Then
  MsgBox "run_gui.bat not found in:" & vbCrLf & dir, vbCritical, "SOR Public Archiver"
  WScript.Quit 1
End If
' 1 = show window so install errors are visible; change to 0 for silent
rc = sh.Run("cmd /c """ & bat & """", 1, True)
If rc <> 0 Then
  MsgBox "GUI exited with code " & rc & vbCrLf & "See gui_error.log in:" & vbCrLf & dir, vbExclamation, "SOR Public Archiver"
End If
