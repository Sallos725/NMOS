"""NMOS for Windows (Phase 23): a notification-area icon that runs the bundle's services. NMOS.exe starts it with
pythonw.exe, so there is no console; everything is logged to nmos.log in the data folder (Phase 37: outside the
bundle, %LOCALAPPDATA%\\NMOS unless the user chose another).

Win32 through ctypes only, so the bundle needs no extra package.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import subprocess
import sys
import threading
import traceback
import winreg
from ctypes import wintypes
from pathlib import Path

import nmos_launcher as launcher

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ole32 = ctypes.WinDLL("ole32")

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

WM_DESTROY, WM_CLOSE, WM_QUERYENDSESSION, WM_ENDSESSION, WM_NULL = 0x0002, 0x0010, 0x0011, 0x0016, 0x0000
WM_LBUTTONUP, WM_RBUTTONUP, WM_APP = 0x0202, 0x0205, 0x8000
# WM_COMMAND_POST: a menu command posted to the window (wParam = the command); the CI smoke drives the tray with it.
WM_TRAY, WM_STATUS, WM_COMMAND_POST = WM_APP + 1, WM_APP + 2, WM_APP + 3
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x1, 0x2, 0x4, 0x10
NIIF_INFO, NIIF_ERROR = 0x1, 0x3
MF_STRING, MF_GRAYED, MF_CHECKED, MF_SEPARATOR = 0x0, 0x1, 0x8, 0x800
TPM_RIGHTBUTTON, TPM_NONOTIFY, TPM_RETURNCMD = 0x2, 0x80, 0x100
IMAGE_ICON, LR_LOADFROMFILE, SM_CXSMICON, SM_CYSMICON = 1, 0x10, 49, 50
MB_ICONERROR, MB_ICONINFORMATION, MB_YESNOCANCEL, IDYES, IDNO = 0x10, 0x40, 0x3, 6, 7
BIF_RETURNONLYFSDIRS, BIF_NEWDIALOGSTYLE, MAX_PATH = 0x1, 0x40, 260
ERROR_ALREADY_EXISTS = 183
CLASS_NAME = "NMOSTrayWindow"

CMD_COPY_URL, CMD_OPEN_PLUGIN, CMD_OPEN_LOGS, CMD_AUTOSTART, CMD_DASHBOARD, CMD_QUIT = 1, 2, 3, 4, 5, 9


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]


class BROWSEINFOW(ctypes.Structure):
    _fields_ = [("hwndOwner", wintypes.HWND), ("pidlRoot", ctypes.c_void_p), ("pszDisplayName", wintypes.LPWSTR),
                ("lpszTitle", wintypes.LPCWSTR), ("ulFlags", wintypes.UINT), ("lpfn", ctypes.c_void_p),
                ("lParam", wintypes.LPARAM), ("iImage", ctypes.c_int)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64),
                ("dwInfoFlags", wintypes.DWORD), ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", wintypes.HICON)]


user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.LoadImageW.restype = wintypes.HANDLE
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                              wintypes.UINT]
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  wintypes.HWND, wintypes.LPVOID]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
shell32.SHBrowseForFolderW.restype = ctypes.c_void_p
shell32.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BROWSEINFOW)]
shell32.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR]
ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
ole32.OleInitialize.argtypes = [wintypes.LPVOID]
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]


def message_box(text: str, error: bool = True) -> None:
    user32.MessageBoxW(None, text, "NMOS", MB_ICONERROR if error else MB_ICONINFORMATION)


# --- Q6 of Phase 37: a data folder PostgreSQL can use -----------------------------------------------------------------

def browse_folder() -> Path | None:
    """The system's folder picker (it can make a new folder); None when cancelled."""
    ole32.OleInitialize(None)  # the picker's new-folder button needs OLE on this thread
    name = ctypes.create_unicode_buffer(MAX_PATH)
    info = BROWSEINFOW(hwndOwner=None, pszDisplayName=ctypes.cast(name, wintypes.LPWSTR),
                       lpszTitle="NMOS 데이터를 둘 폴더를 골라 주세요 (영문과 숫자로만 된 경로)",
                       ulFlags=BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE)
    pidl = shell32.SHBrowseForFolderW(ctypes.byref(info))
    if not pidl:
        return None
    try:
        path = ctypes.create_unicode_buffer(32768)
        return Path(path.value) if shell32.SHGetPathFromIDListW(pidl, path) else None
    finally:
        ole32.CoTaskMemFree(pidl)


def ask_data_dir(base: Path) -> Path | None:
    """Ask where the data goes, suggesting C:\\NMOS-data; the choice is remembered. None when the user cancels."""
    text = (f"Windows 사용자 이름에 한글이 있어서, NMOS 데이터베이스를 기본 위치({base})에 둘 수 없어요. 데이터를 둘 "
            "폴더를 정해 주세요. 한 번 정하면 기억해 두니, 다음 실행이나 업데이트 때는 다시 묻지 않아요.\n\n"
            f"[예] {launcher.SUGGESTED_DATA_DIR}에 두기\n[아니요] 다른 폴더 고르기\n[취소] 시작하지 않기")
    while True:
        answer = user32.MessageBoxW(None, text, "NMOS", MB_YESNOCANCEL | MB_ICONINFORMATION)
        if answer == IDYES:
            chosen = launcher.SUGGESTED_DATA_DIR
        elif answer == IDNO:
            chosen = browse_folder()
            if chosen is None:
                continue
        else:
            return None
        try:
            return launcher.choose_data_dir(base, chosen)
        except (ValueError, OSError) as e:
            message_box(str(e))


# --- start at login: this NMOS.exe in the user's Run key ------------------------------------------------------------
# Not a Startup-folder shortcut: WScript.Shell writes a shortcut's paths in the ANSI code page, so a Korean folder
# came back as "???" and an empty target (Phase 23 step 3, CI). The registry holds the path as it is.

RUN_KEY, RUN_VALUE = r"Software\Microsoft\Windows\CurrentVersion\Run", "NMOS"
EXE = launcher.ROOT / "NMOS.exe"


def autostart_command() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return winreg.QueryValueEx(key, RUN_VALUE)[0]
    except FileNotFoundError:
        return None


def autostart_enabled() -> bool:
    """On only when the entry starts this copy; one left by a moved or another copy reads as off."""
    command = autostart_command()
    return command is not None and Path(command.strip('"')).resolve() == EXE.resolve()


def set_autostart(on: bool) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if on:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, f'"{EXE}"')
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass


def dashboard_url(services: launcher.Services) -> str:
    """The Inspector's first page (PHASE-23 Q8), with the token when one is set (the page asks for it)."""
    from urllib.parse import quote

    token = services.env.get("NMOS_AUTH_TOKEN")
    return services.url + "/dashboard" + (f"?token={quote(token)}" if token else "")


# --- the tray ---------------------------------------------------------------------------------------------------------

class Tray:
    def __init__(self, services: launcher.Services) -> None:
        self.services = services
        self.state = "starting"  # starting | running | stopped | failed | stopping
        self.error = ""
        self.autostart = False
        self.hwnd = None
        self.nid = NOTIFYICONDATAW()
        self._wndproc = WNDPROC(self.wndproc)  # referenced for the window's lifetime
        self.taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")

    def create(self) -> None:
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW(cbSize=ctypes.sizeof(WNDCLASSEXW), lpfnWndProc=self._wndproc, hInstance=hinst,
                         lpszClassName=CLASS_NAME)
        user32.RegisterClassExW(ctypes.byref(wc))
        self.hwnd = user32.CreateWindowExW(0, CLASS_NAME, "NMOS", 0, 0, 0, 0, 0, None, None, hinst, None)
        icon = user32.LoadImageW(None, str(launcher.ROOT / "nmos.ico"), IMAGE_ICON,
                                 user32.GetSystemMetrics(SM_CXSMICON), user32.GetSystemMetrics(SM_CYSMICON),
                                 LR_LOADFROMFILE)
        self.nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        self.nid.hWnd, self.nid.uID, self.nid.hIcon = self.hwnd, 1, icon
        self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        self.nid.uCallbackMessage = WM_TRAY
        self.nid.szTip = "NMOS — 시작하는 중…"
        ok = shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self.nid))
        launcher.log(f"tray icon added: {bool(ok)}")

    def set_tip(self, tip: str, balloon: str | None = None, error: bool = False) -> None:
        self.nid.szTip = tip[:127]
        self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        if balloon:
            self.nid.uFlags |= NIF_INFO
            self.nid.szInfoTitle, self.nid.szInfo = "NMOS", balloon[:255]
            self.nid.dwInfoFlags = NIIF_ERROR if error else NIIF_INFO
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self.nid))

    # --- services (a worker thread; the window thread only reads the state) --------------------------------------
    def run_services(self) -> None:
        try:
            self.autostart = autostart_enabled()
        except OSError as e:
            launcher.log(f"start at login unknown: {e}")
        try:
            self.services.start()
            self.state = "running"
        except BaseException as e:  # noqa: BLE001 — anything here must reach the user, not a closed console
            self.state = "failed"
            self.error = e.code if isinstance(e, SystemExit) and isinstance(e.code, str) else repr(e)
            launcher.log("start failed (what had started is stopped):\n" + "".join(traceback.format_exception(e)))
        user32.PostMessageW(self.hwnd, WM_STATUS, 0, 0)
        while self.state == "running" and self.services.alive():
            threading.Event().wait(2)
        if self.state == "running":
            self.state = "stopped"
            launcher.log("a service exited; stopping the others (see this log)")
            self.services.stop()  # the worker and PostgreSQL do not wait for a quit that may never come
            user32.PostMessageW(self.hwnd, WM_STATUS, 0, 0)

    def on_status(self) -> None:
        if self.state == "running":
            self.set_tip(f"NMOS — 실행 중 ({self.services.url})",
                         f"NMOS가 실행 중이에요. PocketRisu 플러그인의 사이드카 주소: {self.services.url}")
        elif self.state == "failed":
            self.set_tip("NMOS — 시작 실패", "NMOS를 시작하지 못했어요. 메뉴의 '로그 폴더 열기'에서 nmos.log를 확인해 주세요.",
                         error=True)
            message_box(f"NMOS를 시작하지 못했어요.\n\n{self.error}")
        elif self.state == "stopped":
            self.set_tip("NMOS — 멈춤 (로그 확인)", "NMOS의 서비스가 멈췄어요. 로그를 확인해 주세요.", error=True)

    # --- menu ------------------------------------------------------------------------------------------------------
    def show_menu(self) -> None:
        status = {"starting": "시작하는 중…", "running": f"실행 중 — {self.services.url}",
                  "stopped": "멈춤 — 로그를 확인해 주세요", "failed": "시작 실패 — 로그를 확인해 주세요",
                  "stopping": "끄는 중…"}[self.state]
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING | MF_GRAYED, 0, f"NMOS: {status}")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING | (0 if self.state == "running" else MF_GRAYED), CMD_DASHBOARD,
                           "대시보드 열기")
        user32.AppendMenuW(menu, MF_STRING, CMD_COPY_URL, "사이드카 주소 복사")
        user32.AppendMenuW(menu, MF_STRING, CMD_OPEN_PLUGIN, "플러그인 파일 폴더 열기")
        user32.AppendMenuW(menu, MF_STRING, CMD_OPEN_LOGS, "로그 폴더 열기")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING | (MF_CHECKED if self.autostart else 0), CMD_AUTOSTART,
                           "Windows 시작 시 NMOS 실행")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, CMD_QUIT, "NMOS 종료")
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)  # otherwise the menu does not close when clicking elsewhere
        cmd = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_NONOTIFY | TPM_RETURNCMD, pt.x, pt.y, 0,
                                    self.hwnd, None)
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)
        self.on_command(cmd)

    def on_command(self, cmd: int) -> None:
        if cmd == CMD_DASHBOARD:
            os.startfile(dashboard_url(self.services))
        elif cmd == CMD_COPY_URL:
            subprocess.run(["clip"], input=self.services.url.encode("ascii"), **launcher.CHILD_KW_NO_OUTPUT)
            self.set_tip(self.nid.szTip, "사이드카 주소를 복사했어요.")
        elif cmd == CMD_OPEN_PLUGIN:
            os.startfile(launcher.ROOT / "plugin")
        elif cmd == CMD_OPEN_LOGS:
            os.startfile(self.services.data)
        elif cmd == CMD_AUTOSTART:
            want = not self.autostart
            try:
                set_autostart(want)
                self.autostart = want
                launcher.log(f"start at login: {'on' if want else 'off'}")
                self.set_tip(self.nid.szTip, "Windows를 시작하면 NMOS도 같이 실행돼요." if want
                             else "Windows를 시작해도 NMOS는 실행되지 않아요.")
            except OSError as e:
                launcher.log(f"start at login could not be changed: {e}")
                message_box(f"Windows 시작 시 실행 설정을 바꾸지 못했어요.\n\n{e}")
        elif cmd == CMD_QUIT:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    # --- window procedure -------------------------------------------------------------------------------------------
    def wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY and lparam in (WM_RBUTTONUP, WM_LBUTTONUP):
            self.show_menu()
            return 0
        if msg == WM_COMMAND_POST:
            self.on_command(int(wparam))
            return 0
        if msg == WM_STATUS:
            self.on_status()
            return 0
        if msg == self.taskbar_created:  # Explorer restarted: the icon is gone until added again
            shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self.nid))
            return 0
        if msg == WM_QUERYENDSESSION:
            return 1
        if msg == WM_ENDSESSION and wparam:
            self.quit()
            return 0
        if msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            self.quit()
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def quit(self) -> None:
        self.state = "stopping"
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
        self.services.stop()

    def loop(self) -> None:
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


def main() -> int:
    # One NMOS per bundle folder, said kindly before the launcher's own data-folder lock would refuse it (and before
    # a second one asks where the data goes).
    key = hashlib.sha1(str(launcher.ROOT).lower().encode()).hexdigest()[:16]
    kernel32.CreateMutexW(None, True, f"Local\\NMOS-{key}")
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        message_box("NMOS가 이미 실행 중이에요. 작업 표시줄 오른쪽 아래의 NMOS 아이콘을 확인해 주세요.", error=False)
        return 0

    try:
        services = launcher.Services()  # resolves .env and the data folder, so the log goes where the data is
    except launcher.DataLocationNeeded as need:
        if ask_data_dir(need.base) is None:
            return 0  # cancelled: nothing is started
        services = launcher.Services()
    data = services.data
    log_path = data / "nmos.log"
    if log_path.exists() and log_path.stat().st_size > 5_000_000:
        log_path.replace(data / "nmos.log.1")
    log_file = open(log_path, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log_file  # pythonw has neither
    launcher.LOG = log_file
    no_window = {"creationflags": subprocess.CREATE_NO_WINDOW}
    launcher.CHILD_FLAGS = no_window
    launcher.CHILD_KW = {**no_window, "stdout": log_file, "stderr": subprocess.STDOUT}
    launcher.CHILD_KW_NO_OUTPUT = {**no_window, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}

    tray = Tray(services)
    tray.create()
    threading.Thread(target=tray.run_services, daemon=True).start()
    tray.loop()
    launcher.log("tray exited")
    return 0


if __name__ == "__main__":
    sys.exit(main())
