@echo off
rem mai.cmd -- Windows shim for the mai CLI.
rem Delegates entirely to maicelium_cli.py -- NO verb-dispatch logic here.
rem Single-source invariant: all routing logic lives in maicelium_cli.py only.
python "%~dp0maicelium_cli.py" %*
