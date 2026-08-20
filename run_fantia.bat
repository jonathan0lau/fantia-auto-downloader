@echo off
setlocal
python fantia_downloader.py %*
if errorlevel 1 pause
