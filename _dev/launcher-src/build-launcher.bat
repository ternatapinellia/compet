@echo off
rem Build CompetLauncher.exe from _dev\launcher-src\main.go
setlocal
set "HERE=%~dp0"
set "OUT=%~dp0..\..\CompetLauncher.exe"
set "GOCACHE=%TEMP%\compet-gocache"
set "GOTMPDIR=%TEMP%\compet-gotmp"
pushd "%HERE%"
go build -ldflags="-H windowsgui" -o "%OUT%" .
popd
if exist "%OUT%" ( echo Done: CompetLauncher.exe ) else ( echo Build failed. & exit /b 1 )
endlocal