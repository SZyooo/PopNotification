Set ws = CreateObject("WScript.Shell")
currentDir = CreateObject("Scripting.FileSystemObject").GetFile(WScript.ScriptFullName).ParentFolder.Path
ws.CurrentDirectory = currentDir

ws.Run "pythonw main.py --background", 0, False
