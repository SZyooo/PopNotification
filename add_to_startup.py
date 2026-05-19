import os
import sys
import subprocess

vbs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "启动.vbs")
startup = os.path.join(os.path.expanduser("~"),
    "AppData", "Roaming", "Microsoft", "Windows",
    "Start Menu", "Programs", "Startup", "PopNotification.lnk")

if not os.path.exists(vbs_path):
    print("错误: 未找到 启动.vbs")
    sys.exit(1)

ps = (
    '$ws = New-Object -ComObject WScript.Shell;\n'
    '$sc = $ws.CreateShortcut("' + startup + '");\n'
    '$sc.TargetPath = "wscript.exe";\n'
    '$sc.Arguments = "' + vbs_path + '";\n'
    '$sc.WorkingDirectory = "' + os.path.dirname(vbs_path) + '";\n'
    '$sc.Description = "PopNotification 知识提醒";\n'
    '$sc.WindowStyle = 7;\n'
    '$sc.Save();\n'
)

ret = subprocess.call(["powershell", "-ExecutionPolicy", "Bypass", ps],
                       shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if os.path.exists(startup):
    print("[OK] 已添加到开机启动项")
else:
    print("[错误] 创建快捷方式失败")
    sys.exit(1)
