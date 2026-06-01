"""检查 AID Daemon 依赖"""
import sys
deps = {
    "tkinter": None,
    "PIL": None,
    "pystray": None,
    "sounddevice": None,
    "whisper": None,
    "speech_recognition": None,
    "requests": None,
}
for mod_name in deps:
    try:
        __import__(mod_name)
        deps[mod_name] = "OK"
    except ImportError as e:
        deps[mod_name] = f"NO ({str(e)})"

for name, status in deps.items():
    print(f"  {name:20s}  {status}")
