@echo off
rem ansible-pull launcher for Windows (native Windows port of ansible-core).
rem Runs the CLI directly from this source tree. Requires Python 3.12+ on PATH,
rem or set ANSIBLE_PYTHON to a specific interpreter (e.g. a venv's python.exe).
setlocal
set "_AROOT=%~dp0.."
set "PYTHONPATH=%_AROOT%\lib;%PYTHONPATH%"
set "_APY=%ANSIBLE_PYTHON%"
if "%_APY%"=="" set "_APY=python"
"%_APY%" "%_AROOT%\lib\ansible\cli\pull.py" %*
exit /b %ERRORLEVEL%
