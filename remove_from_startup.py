import os
import glob
import sys

startup = os.path.join(os.path.expanduser("~"),
    "AppData", "Roaming", "Microsoft", "Windows",
    "Start Menu", "Programs", "Startup")

removed = False
for f in glob.glob(os.path.join(startup, "*BubbleMind*")) + glob.glob(os.path.join(startup, "*PopNotification*")):
    try:
        os.remove(f)
        print(f"已移除: {os.path.basename(f)}")
        removed = True
    except Exception as e:
        print(f"移除失败 {os.path.basename(f)}: {e}")

if not removed:
    print("未找到相关开机启动项")
else:
    print("清理完成")
