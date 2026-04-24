@echo off
chcp 65001 >nul
echo ========================================
echo    抖音助手 - 启动调试浏览器
echo ========================================
echo.
echo 正在启动 Chrome 调试模式...
echo.

set CHROME_PATH="C:\Program Files\Google\Chrome\Application\chrome.exe"
set USER_DATA_DIR=%USERPROFILE%\AppData\Local\抖音助手\ChromeProfile
set REMOTE_PORT=9222

echo 检查 Chrome 路径...
if not exist %CHROME_PATH% (
    echo 未找到 Chrome，尝试备用路径...
    set CHROME_PATH="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
)

if not exist %CHROME_PATH% (
    echo.
    echo [错误] 未找到 Chrome 浏览器
    echo 请确认已安装 Google Chrome
    echo.
    pause
    exit /b 1
)

echo Chrome 路径: %CHROME_PATH%
echo 用户数据目录: %USER_DATA_DIR%
echo 调试端口: %REMOTE_PORT%
echo.

if not exist "%USER_DATA_DIR%" (
    echo 创建用户数据目录...
    mkdir "%USER_DATA_DIR%"
)

echo 关闭现有 Chrome 进程...
taskkill /F /IM chrome.exe >nul 2>&1

echo 等待进程关闭...
timeout /t 2 /nobreak >nul

echo 启动浏览器...
start "" %CHROME_PATH% ^
  --remote-debugging-port=%REMOTE_PORT% ^
  --user-data-dir="%USER_DATA_DIR%" ^
  --no-first-run ^
  --no-default-browser-check ^
  https://www.douyin.com

echo.
echo 等待浏览器启动...
timeout /t 3 /nobreak >nul

echo.
echo ========================================
echo Chrome 已启动，调试端口: %REMOTE_PORT%
echo ========================================
echo.
echo 后续操作步骤:
echo 1. 在浏览器中登录抖音账号
echo 2. 登录完成后启动采集应用
echo 3. 应用会自动连接到此浏览器
echo.
echo 提示: 请保持此窗口打开
echo ========================================
echo.

echo 检查浏览器是否成功启动...
timeout /t 2 /nobreak >nul

curl -s http://localhost:%REMOTE_PORT%/json/version >nul 2>&1
if %errorlevel% equ 0 (
    echo [成功] 浏览器调试端口已就绪
    echo 访问 http://localhost:%REMOTE_PORT%/json 查看调试信息
) else (
    echo [警告] 无法连接到调试端口
    echo 请检查浏览器是否正常启动
)

echo.
pause
