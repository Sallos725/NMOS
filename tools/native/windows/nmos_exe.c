/* NMOS.exe (Phase 23): start the tray (python\pythonw.exe nmos_tray.py) from this folder, with no console, and exit.
 * The icon comes from nmos.rc. Build: rc nmos.rc && cl /utf-8 nmos_exe.c nmos.res /link /SUBSYSTEM:WINDOWS */
#define WIN32_LEAN_AND_MEAN
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <wchar.h>

#pragma comment(lib, "user32.lib")

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE prev, PWSTR args, int show) {
    static wchar_t dir[32768], cmd[65600];
    DWORD n = GetModuleFileNameW(NULL, dir, 32768);
    if (n == 0 || n >= 32768) return 1;
    wchar_t *slash = wcsrchr(dir, L'\\');
    if (slash) *slash = L'\0';
    swprintf(cmd, sizeof cmd / sizeof cmd[0], L"\"%ls\\python\\pythonw.exe\" \"%ls\\nmos_tray.py\"", dir, dir);

    STARTUPINFOW si = {sizeof si};
    PROCESS_INFORMATION pi;
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE, 0, NULL, dir, &si, &pi)) {
        MessageBoxW(NULL,
                    L"NMOS를 시작할 수 없어요: python\\pythonw.exe를 찾지 못했습니다.\n"
                    L"압축을 모두 푼 폴더에서 NMOS.exe를 실행해 주세요.",
                    L"NMOS", MB_ICONERROR);
        return 1;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}
