import os
import sys
import subprocess

exe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "BubbleMind.exe")

if not os.path.exists(exe_path):
    print("错误: 未找到 BubbleMind.exe")
    sys.exit(1)

startup = os.path.join(os.path.expanduser("~"),
    "AppData", "Roaming", "Microsoft", "Windows",
    "Start Menu", "Programs", "Startup", "BubbleMind.lnk")

ps = (
    '$ws = New-Object -ComObject WScript.Shell;\n'
    '$sc = $ws.CreateShortcut("' + startup + '");\n'
    '$sc.TargetPath = "' + exe_path + '";\n'
    '$sc.WorkingDirectory = "' + os.path.dirname(exe_path) + '";\n'
    '$sc.Description = "BubbleMind 知识提醒";\n'
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
