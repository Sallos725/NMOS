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
        DWORD err = GetLastError();
        static wchar_t reason[1024], text[2048];
        if (!FormatMessageW(FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS, NULL, err, 0, reason,
                            sizeof reason / sizeof reason[0], NULL))
            swprintf(reason, sizeof reason / sizeof reason[0], L"error %lu", err);
        swprintf(text, sizeof text / sizeof text[0],
                 L"NMOS를 시작할 수 없어요 (python\\pythonw.exe):\n%ls\n"
                 L"%ls압축을 모두 푼 폴더에서 NMOS.exe를 실행했는지 확인해 주세요.",
                 reason, err == ERROR_FILE_NOT_FOUND || err == ERROR_PATH_NOT_FOUND ? L"" : L"백신이 막았거나 파일이 손상됐을 수 있어요. ");
        MessageBoxW(NULL, text, L"NMOS", MB_ICONERROR);
        return 1;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}
