@echo off
chcp 65001 >nul
title 企业材料预审 · 本机试用版
setlocal

REM 双击本文件：启动本机服务并打开浏览器（默认 http://127.0.0.1:8765 ）

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
ping -n 4 127.0.0.1 >nul
start "" "http://127.0.0.1:8765/"
exit /b 0
