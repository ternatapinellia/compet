@echo off
rem Build CompetGifFix.dll from _dev\injector-src\CompetGifFix.c
setlocal
set "HERE=%~dp0"
set "OUT=%~dp0..\..\CompetGifFix.dll"
set "ZIG=%LOCALAPPDATA%\Programs\Python\Python314\Lib\site-packages\ziglang\zig.exe"

if exist "%ZIG%" (
    echo Building with zig...
    "%ZIG%" cc -shared -Os -o "%OUT%" -lkernel32 -luser32 "%HERE%CompetGifFix.c"
) else (
    where cl >nul 2>nul && (
        echo Building with MSVC...
        pushd "%HERE%" && cl /nologo /O2 /LD CompetGifFix.c /Fe:"%OUT%" kernel32.lib user32.lib && popd
    ) || (
        echo No C compiler found. Install zig, MSVC, or MinGW and retry.
        exit /b 1
    )
)

if exist "%OUT%" ( echo Done: %OUT% ) else ( echo Build failed. & exit /b 1 )
endlocal