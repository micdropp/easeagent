@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title EaseAgent 一键启动
color 0A

echo ============================================
echo    EaseAgent 智能办公 Agent 一键启动
echo ============================================
echo.

REM --- 检查虚拟环境 ---
if exist "%~dp0venv\Scripts\python.exe" (
    set "PYTHON=%~dp0venv\Scripts\python.exe"
    echo [OK] 虚拟环境: venv
) else if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON=%~dp0.venv\Scripts\python.exe"
    echo [OK] 虚拟环境: .venv
) else (
    set "PYTHON=python"
    echo [!!] 未找到虚拟环境，使用系统 Python
)

REM ============================================
REM  Docker 依赖服务
REM ============================================
where docker >nul 2>&1
if !errorlevel! neq 0 goto :no_docker

REM Docker 已安装，检测守护进程
docker info >nul 2>&1
if !errorlevel!==0 goto :docker_ready

echo [..] Docker Desktop 未运行，正在启动...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
echo [..] 等待 Docker 启动（最多 30 秒）...
set "_wait=0"

:wait_docker
if !_wait! geq 30 goto :docker_timeout
timeout /t 2 /nobreak >nul
set /a _wait+=2
docker info >nul 2>&1
if !errorlevel! neq 0 goto :wait_docker
echo [OK] Docker Desktop 已启动
goto :docker_ready

:docker_timeout
echo [!!] Docker 启动超时，请手动打开 Docker Desktop
goto :no_docker

:docker_ready
echo [..] 检查 Docker 依赖服务...
cd /d "%~dp0"
docker-compose up -d mosquitto redis chromadb >nul 2>&1
if !errorlevel! neq 0 (
    echo [!!] Docker 容器启动失败
) else (
    echo [OK] Redis ^(Docker^)
    echo [OK] Mosquitto MQTT ^(Docker^)
    echo [OK] ChromaDB ^(Docker^)
)
goto :after_deps

:no_docker
echo [!!] Docker 未安装，尝试本地启动依赖服务...

where redis-server >nul 2>&1
if !errorlevel!==0 (
    start /min "Redis" redis-server
    echo [OK] Redis
) else (
    echo [!!] Redis 未安装，决策缓存不可用
)

where mosquitto >nul 2>&1
if !errorlevel!==0 (
    start /min "Mosquitto" mosquitto -v
    echo [OK] Mosquitto
) else (
    echo [!!] Mosquitto 未安装，IoT 设备通信不可用
)

where chroma >nul 2>&1
if !errorlevel!==0 (
    start /min "ChromaDB" chroma run --host localhost --port 8100
    echo [OK] ChromaDB
) else (
    echo [!!] ChromaDB 未安装，向量记忆不可用
)

:after_deps

REM ============================================
REM  Ollama
REM ============================================
where ollama >nul 2>&1
if !errorlevel!==0 (
    echo [..] 启动 Ollama...
    start /min "Ollama" ollama serve
    timeout /t 2 /nobreak >nul
    echo [OK] Ollama 已启动
) else (
    echo [!!] Ollama 未安装，AI Agent 将使用云端 API
)

REM ============================================
REM  释放端口 8000（防止旧进程占用）
REM ============================================
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000.*LISTENING" 2^>nul') do (
    echo [..] 端口 8000 被 PID %%p 占用，正在释放...
    taskkill /PID %%p /F >nul 2>&1
)

REM ============================================
REM  释放端口 3000 + 启动 Vue 前端
REM ============================================
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":3000.*LISTENING" 2^>nul') do (
    echo [..] 端口 3000 被 PID %%p 占用，正在释放...
    taskkill /PID %%p /F >nul 2>&1
)

if exist "%~dp0web\node_modules" (
    echo [..] 启动前端开发服务器...
    cd /d "%~dp0web"
    start /min "EaseAgent-Frontend" cmd /c "npx vite --port 3000"
    timeout /t 3 /nobreak >nul
    echo [OK] 前端已启动
    start http://localhost:3000
) else (
    echo [!!] 前端依赖未安装，请先执行: cd web ^&^& npm install
)

timeout /t 1 /nobreak >nul

echo.
echo ============================================
echo    启动 EaseAgent 主服务...
echo ============================================
echo.
echo    访问地址:
echo      管理面板:  http://localhost:3000
echo      API:       http://localhost:8000
echo      Swagger:   http://localhost:8000/docs
echo      视频流:    http://localhost:8000/api/video/stream/cam_entrance
echo      健康检查:  http://localhost:8000/health?detail=true
echo.
echo    按 Ctrl+C 停止服务
echo ============================================
echo.

cd /d "%~dp0"
!PYTHON! run.py

pause
