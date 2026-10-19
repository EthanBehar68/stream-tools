@echo off
rem Runs clip.py, checking for Python first. Usage: clip.bat <recording> [options]
where py >nul 2>nul && (py -3 "%~dp0clip.py" %* & exit /b)
python -c "import sys" >nul 2>nul && (python "%~dp0clip.py" %* & exit /b)
echo Python is not installed.
echo   Install: winget install Python.Python.3.12
echo   Then close and reopen the terminal.
exit /b 1
