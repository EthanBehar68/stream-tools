@echo off
rem Runs stitch.py, checking for Python first. Usage: stitch.bat <folder> [options]
where py >nul 2>nul && (py -3 "%~dp0stitch.py" %* & exit /b)
python -c "import sys" >nul 2>nul && (python "%~dp0stitch.py" %* & exit /b)
echo Python is not installed.
echo   Install: winget install Python.Python.3.12
echo   Then close and reopen the terminal.
exit /b 1
