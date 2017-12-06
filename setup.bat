@echo off
cd /d %~dp0
if "%PROCESSOR_ARCHITECTURE%"=="x86" (copy "unrar\32\*" "C:\Windows")
if "%PROCESSOR_ARCHITECTURE%"=="AMD64" (copy "unrar\64\*" "C:\Windows")
@pause