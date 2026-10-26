import ctypes
import hashlib
import os
from ctypes import wintypes


class Mutex:

    def __init__(self, name):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.handle = self.kernel.CreateMutexW(None, False, "Local\\BiliOshi-" + name)
        self.acquired = bool(self.handle) and ctypes.get_last_error() != 183
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def instance_name(root):
    return hashlib.sha256(str(root.resolve()).lower().encode()).hexdigest()[:20]


class Job:
    """Kill all owned workers if the tray process exits or crashes."""

    def __init__(self):

        class Basic(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_int64),
                ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD),
                ("min_ws", ctypes.c_size_t),
                ("max_ws", ctypes.c_size_t),
                ("active", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD),
            ]

        class IO(ctypes.Structure):
            _fields_ = [(f"v{i}", ctypes.c_uint64) for i in range(6)]

        class Extended(ctypes.Structure):
            _fields_ = [
                ("basic", Basic),
                ("io", IO),
                ("process_mem", ctypes.c_size_t),
                ("job_mem", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t),
                ("peak_job", ctypes.c_size_t),
            ]

        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        self.kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        self.kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.handle = self.kernel.CreateJobObjectW(None, None)
        info = Extended()
        info.basic.flags = 8192
        if not self.handle or not self.kernel.SetInformationJobObject(
            self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def add(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            process.kill()
            process.wait()
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def _process_kernel():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
    )
    kernel.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
    kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    return kernel


def _identity_from_handle(kernel, handle, pid):
    exit_code = wintypes.DWORD()
    if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)) or exit_code.value != 259:
        return None
    size = wintypes.DWORD(32768)
    image = ctypes.create_unicode_buffer(size.value)
    created, exited, system, user = (wintypes.FILETIME() for _ in range(4))
    if not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
        return None
    if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in (created, exited, system, user))):
        return None
    return {
        "pid": pid, "executable": os.path.normcase(os.path.realpath(image.value)),
        "created": (created.dwHighDateTime << 32) | created.dwLowDateTime,
    }


def process_identity(pid):
    """Snapshot a live process generation (PID, full image path, creation FILETIME)."""
    if type(pid) is not int or pid <= 0:
        return None
    kernel = _process_kernel()
    handle = kernel.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:  # No such PID; access errors are not evidence of absence.
            return None
        raise ctypes.WinError(error)
    try:
        return _identity_from_handle(kernel, handle, pid)
    finally:
        kernel.CloseHandle(handle)


def terminate_verified(identity):
    """Never terminate by PID alone, or reopen after verifying the generation."""
    pid = identity.get("pid")
    if type(pid) is not int or pid <= 0:
        return False
    kernel = _process_kernel()
    handle = kernel.OpenProcess(0x1001, False, pid)  # QUERY_LIMITED_INFORMATION | TERMINATE
    if not handle:
        return False
    try:
        return (_identity_from_handle(kernel, handle, pid) == identity
                and bool(kernel.TerminateProcess(handle, 1)))
    finally:
        kernel.CloseHandle(handle)


def is_autostart_enabled(app_name: str = "BiliOshi") -> bool:
    """Read the login task and recognize the legacy Run entry during migration."""
    if os.name != "nt":
        return False
    import subprocess
    import winreg
    from xml.etree import ElementTree

    try:
        result = subprocess.run(
            ["schtasks.exe", "/Query", "/TN", app_name + "-Desktop", "/XML"],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=15,
        )
        if result.returncode == 0:
            # schtasks declares UTF-16 but emits UTF-8 text; parse what it actually sent.
            xml = result.stdout.decode("utf-8-sig", errors="replace")
            task = ElementTree.fromstring(xml)
            settings = task.find("{*}Settings")
            enabled = settings.find("{*}Enabled") if settings is not None else None
            if enabled is None or enabled.text != "false":
                return True
    except (OSError, ValueError, ElementTree.ParseError, subprocess.TimeoutExpired):
        pass
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            0, winreg.KEY_READ,
        ) as key:
            winreg.QueryValueEx(key, app_name)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool, app_name: str = "BiliOshi") -> bool:
    """Use the same guardian login task as the installer; remove legacy Run entry."""
    if os.name != "nt":
        return False
    import base64
    import subprocess
    import sys
    import winreg
    from pathlib import Path

    def literal(value):
        return "'" + str(value).replace("'", "''") + "'"

    name = literal(app_name + "-Desktop")
    script = "$ErrorActionPreference='Stop'; "
    if enabled:
        arguments = "--supervisor --start"
        if not getattr(sys, "frozen", False):
            entry = Path(__file__).resolve().parents[1] / "tray_app.py"
            arguments = subprocess.list2cmdline([str(entry), "--supervisor", "--start"])
        script += (
            "$account=[System.Security.Principal.WindowsIdentity]::GetCurrent().Name; "
            f"$action=New-ScheduledTaskAction -Execute {literal(sys.executable)} "
            f"-Argument {literal(arguments)} -WorkingDirectory {literal(Path(sys.executable).parent)}; "
            "$trigger=New-ScheduledTaskTrigger -AtLogOn -User $account; $trigger.Delay='PT20S'; "
            "$principal=New-ScheduledTaskPrincipal -UserId $account -LogonType Interactive -RunLevel Limited; "
            "$settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew "
            "-ExecutionTimeLimit (New-TimeSpan -Seconds 0) -RestartCount 3 "
            "-RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries; "
            f"Register-ScheduledTask -TaskName {name} -Action $action -Trigger $trigger "
            "-Principal $principal -Settings $settings -Description 'BiliOshi guardian; starts after Windows login.' -Force | Out-Null; "
            f"Get-ScheduledTask -TaskName 'LiveSupport-Desktop' -ErrorAction SilentlyContinue | "
            "Unregister-ScheduledTask -Confirm:$false -ErrorAction SilentlyContinue"
        )
    else:
        script += (f"$task=Get-ScheduledTask -TaskName {name} -ErrorAction SilentlyContinue; "
                   "if ($task) { $task | Disable-ScheduledTask | Out-Null }")
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
             base64.b64encode(script.encode("utf-16le")).decode("ascii")],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30,
        )
        if result.returncode:
            return False
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            0, winreg.KEY_SET_VALUE,
        ) as key:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False
