@echo off
REM Cross-platform Python launcher shim (Windows).
REM Tries python3, then python, then the `py` launcher with -3.
where python3 >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  python3 %*
  exit /b %ERRORLEVEL%
)
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  python %*
  exit /b %ERRORLEVEL%
)
where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  py -3 %*
  exit /b %ERRORLEVEL%
)
echo py.cmd: no python interpreter found in PATH 1>&2
exit /b 127
