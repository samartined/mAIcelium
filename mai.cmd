@echo off
setlocal

:: Get the directory of this script
set "DIR=%~dp0"

:: Pass all arguments to the mai python script
python "%DIR%mai" %*
