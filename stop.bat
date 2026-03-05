@echo off
chcp 65001 >nul
title EaseAgent 停止服务
color 0C

echo ============================================
echo    停止 EaseAgent 所有服务
echo ============================================
echo.

echo [..] 停止 EaseAgent 主服务...
taskkill /f /fi "WINDOWTITLE eq EaseAgent*" >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)
echo [OK] EaseAgent 已停止

echo [..] 停止前端开发服务器...
taskkill /f /fi "WINDOWTITLE eq EaseAgent-Frontend" >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000.*LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)
echo [OK] 前端已停止

echo [..] 停止 Redis...
taskkill /f /fi "WINDOWTITLE eq Redis" >nul 2>&1
taskkill /f /im redis-server.exe >nul 2>&1
echo [OK] Redis 已停止

echo [..] 停止 Mosquitto...
taskkill /f /fi "WINDOWTITLE eq Mosquitto" >nul 2>&1
taskkill /f /im mosquitto.exe >nul 2>&1
echo [OK] Mosquitto 已停止

echo [..] 停止 ChromaDB...
taskkill /f /fi "WINDOWTITLE eq ChromaDB" >nul 2>&1
echo [OK] ChromaDB 已停止

echo [..] 停止 Ollama...
taskkill /f /fi "WINDOWTITLE eq Ollama" >nul 2>&1
echo [OK] Ollama 已停止

echo.
echo ============================================
echo    所有服务已停止
echo ============================================
echo.
pause
