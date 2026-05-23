#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>

int WINAPI WinMain(HINSTANCE hInst, HINSTANCE hPrev, LPSTR lpCmd, int nShow) {
    wchar_t exe_path[MAX_PATH];
    GetModuleFileNameW(NULL, exe_path, MAX_PATH);

    wchar_t dir[MAX_PATH];
    wcsncpy(dir, exe_path, MAX_PATH);
    wchar_t *p = wcsrchr(dir, L'\\');
    if (p) *p = L'\0';

    SetCurrentDirectoryW(dir);

    wchar_t cmdline[256] = L"pythonw main.py";
    STARTUPINFOW si = { sizeof(si) };
    PROCESS_INFORMATION pi;
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;

    BOOL ok = CreateProcessW(NULL, cmdline, NULL, NULL, FALSE,
                              CREATE_NO_WINDOW, NULL, dir, &si, &pi);
    if (!ok) {
        wcscpy(cmdline, L"python main.py");
        si.wShowWindow = SW_SHOW;
        ok = CreateProcessW(NULL, cmdline, NULL, NULL, FALSE,
                            0, NULL, dir, &si, &pi);
        if (!ok) {
            MessageBoxW(NULL,
                L"BubbleMind: Python not found.\n\n"
                L"Please install Python 3.8+ and ensure 'python' is in PATH.",
                L"BubbleMind", MB_OK | MB_ICONERROR);
            return 1;
        }
    }

    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    return 0;
}
