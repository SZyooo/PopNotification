import os
import sys
import subprocess
import glob

exe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "PopNotification.exe")
if not os.path.exists(exe_path):
    exe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "BubbleMind.exe")

if not os.path.exists(exe_path):
    print("错误: 未找到 PopNotification.exe 或 BubbleMind.exe")
    sys.exit(1)

startup = os.path.join(os.path.expanduser("~"),
    "AppData", "Roaming", "Microsoft", "Windows",
    "Start Menu", "Programs", "Startup")

# Remove old VBS-based shortcuts
for f in glob.glob(os.path.join(startup, "*BubbleMind*")) + glob.glob(os.path.join(startup, "*PopNotification*")):
    try:
        os.remove(f)
        print(f"已移除旧启动项: {os.path.basename(f)}")
    except Exception:
        pass

lnk = os.path.join(startup, "PopNotification.lnk")

ps = (
    '$ws = New-Object -ComObject WScript.Shell;\n'
    '$sc = $ws.CreateShortcut("' + lnk + '");\n'
    '$sc.TargetPath = "' + exe_path + '";\n'
    '$sc.WorkingDirectory = "' + os.path.dirname(exe_path) + '";\n'
    '$sc.Description = "PopNotification 知识提醒";\n'
    '$sc.WindowStyle = 7;\n'
    '$sc.Save();\n'
)

ret = subprocess.call(["powershell", "-ExecutionPolicy", "Bypass", ps],
                       shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if os.path.exists(lnk):
    print("[OK] 已添加到开机启动项")
else:
    print("[错误] 创建快捷方式失败")
    sys.exit(1)
