@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*RealtimeVoiceAnswerAgent*' } | Stop-Process -Force"
