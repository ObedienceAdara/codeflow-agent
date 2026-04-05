@echo off
echo [clean] Removing all __pycache__ folders...
for /d /r %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
echo [clean] Done.
pause
