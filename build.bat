@echo off
chcp 65001 >nul
setlocal

echo ==========================================
echo  抖音助手 - 单文件 EXE 打包脚本
echo ==========================================
echo.

REM 1. 检查 Python 环境
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 python,请先安装 Python 3.10+
    exit /b 1
)

REM 2. 安装/更新依赖
echo [1/4] 安装依赖...
pip install -r requirements.txt
if errorlevel 1 goto :err
pip install pyinstaller
if errorlevel 1 goto :err

REM 3. 构建前端
echo.
echo [2/4] 构建前端 (vite build)...
pushd src\frontend
call npm install
if errorlevel 1 ( popd & goto :err )
call npm run build
if errorlevel 1 ( popd & goto :err )
popd

REM 4. 清理旧产物
echo.
echo [3/4] 清理旧 build / dist...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM 5. PyInstaller 打包
echo.
echo [4/4] PyInstaller 打包 (单文件 onefile)...
pyinstaller douyin_reach.spec --clean --noconfirm
if errorlevel 1 goto :err

echo.
echo ==========================================
echo  完成! 产物位于 dist\抖音助手.exe
echo ==========================================
echo.
echo  使用说明:
echo  1. 把 dist\抖音助手.exe 拷贝到任意目录
echo  2. 双击运行,首次启动会在同目录创建 data\
echo  3. 必须先在系统装好 Chrome 或 Edge
echo  4. 在 设置 - 浏览器配置 中确认 CDP 已启用
echo.
goto :eof

:err
echo.
echo [ERROR] 打包失败,请查看上方日志
exit /b 1
