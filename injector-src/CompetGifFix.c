/*
 * CompetGifFix.dll
 * -----------------
 * Injected into a running Compet.exe.  It locates the embedded CPython 3.11
 * runtime (python311.dll, already loaded by the frozen application), reads the
 * script "CompetGifFix.py" that sits next to this DLL, and runs it inside the
 * target process.
 *
 * The script patches ui.pet_widget.PetWidget so that GIF / WebP skin images are
 * animated.  Nothing on disk is modified and a restart fully reverts the change.
 *
 * The Python call is dispatched through Py_AddPendingCall so it executes on the
 * interpreter's own main thread, exactly like the existing CompetInputFix.dll.
 */

#include <windows.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

typedef int (*py_add_pending_call_t)(int (*)(void *), void *);
typedef int (*py_run_simple_string_t)(const char *);

static HMODULE                 g_self = NULL;
static py_add_pending_call_t   p_add_pending_call = NULL;
static py_run_simple_string_t  p_run_simple_string = NULL;

static void log_line(const char *msg)
{
    char dir[MAX_PATH];
    char path[MAX_PATH];
    DWORD n, written;
    HANDLE h;

    n = GetModuleFileNameA(g_self, dir, MAX_PATH);
    if (n == 0 || n >= MAX_PATH)
        return;
    while (n > 0 && dir[n - 1] != '\\' && dir[n - 1] != '/')
        n--;
    dir[n] = '\0';

    _snprintf_s(path, sizeof(path), _TRUNCATE, "%sCompetGifFix.log", dir);
    h = CreateFileA(path, FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
                    NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE)
        return;
    SetFilePointer(h, 0, NULL, FILE_END);
    WriteFile(h, msg, (DWORD)strlen(msg), &written, NULL);
    WriteFile(h, "\r\n", 2, &written, NULL);
    CloseHandle(h);
}

static char *read_text_file(const char *path)
{
    HANDLE h;
    DWORD size, got;
    char *buf;

    h = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ, NULL,
                    OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE)
        return NULL;
    size = GetFileSize(h, NULL);
    if (size == INVALID_FILE_SIZE || size == 0) {
        CloseHandle(h);
        return NULL;
    }
    buf = (char *)malloc(size + 1);
    if (buf == NULL) {
        CloseHandle(h);
        return NULL;
    }
    if (!ReadFile(h, buf, size, &got, NULL)) {
        free(buf);
        CloseHandle(h);
        return NULL;
    }
    buf[got] = '\0';
    CloseHandle(h);
    return buf;
}

/* Runs on the interpreter main thread.  arg is a heap buffer with the script. */
static int run_script(void *arg)
{
    char *code = (char *)arg;
    if (code != NULL && p_run_simple_string != NULL)
        p_run_simple_string(code);
    return 0;
}

static DWORD WINAPI worker(LPVOID param)
{
    HMODULE py;
    int tries;
    char dir[MAX_PATH];
    char script[MAX_PATH];
    DWORD n;
    char *code;

    (void)param;

    /* The frozen application may still be starting up; retry for a while. */
    py = NULL;
    for (tries = 0; tries < 120 && py == NULL; tries++) {
        py = GetModuleHandleA("python311.dll");
        if (py == NULL)
            Sleep(250);
    }
    if (py == NULL) {
        log_line("python311.dll not found - giving up");
        return 0;
    }

    p_add_pending_call  = (py_add_pending_call_t)(void *)GetProcAddress(py, "Py_AddPendingCall");
    p_run_simple_string = (py_run_simple_string_t)(void *)GetProcAddress(py, "PyRun_SimpleString");
    if (p_add_pending_call == NULL || p_run_simple_string == NULL) {
        log_line("required CPython exports not found - giving up");
        return 0;
    }

    n = GetModuleFileNameA(g_self, dir, MAX_PATH);
    if (n == 0 || n >= MAX_PATH) {
        log_line("cannot resolve own directory");
        return 0;
    }
    while (n > 0 && dir[n - 1] != '\\' && dir[n - 1] != '/')
        n--;
    dir[n] = '\0';

    _snprintf_s(script, sizeof(script), _TRUNCATE, "%sCompetGifFix.py", dir);
    code = read_text_file(script);
    if (code == NULL) {
        log_line("CompetGifFix.py not found or unreadable");
        return 0;
    }

    /* The interpreter may not accept pending calls yet during startup; retry. */
    for (tries = 0; tries < 60; tries++) {
        if (p_add_pending_call(run_script, code) == 0) {
            log_line("gif fix scheduled");
            return 0;
        }
        Sleep(500);
    }
    log_line("Py_AddPendingCall rejected event");
    free(code);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID reserved)
{
    HANDLE th;

    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        g_self = inst;
        DisableThreadLibraryCalls(inst);
        th = CreateThread(NULL, 0, worker, NULL, 0, NULL);
        if (th != NULL)
            CloseHandle(th);
    }
    return TRUE;
}