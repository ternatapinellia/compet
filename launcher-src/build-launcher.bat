@echo off
rem Build CompetLauncher.exe from launcher-src\main.go
setlocal
set "HERE=%~dp0"
set "GOCACHE=%TEMP%\compet-gocache"
set "GOTMPDIR=%TEMP%\compet-gotmp"
pushd "%HERE%"
go build -ldflags="-H windowsgui" -o "%~dp0..\CompetLauncher.exe" .
popd
if exist "%~dp0..\CompetLauncher.exe" ( echo Done: CompetLauncher.exe ) else ( echo Build failed. & exit /b 1 )
endlocal