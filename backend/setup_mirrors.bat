@echo off
chcp 65001 >nul

echo ========================================
echo   配置国内镜像源加速下载
echo ========================================
echo.

:: 配置 pip 清华镜像源
echo [1/3] 配置 pip 清华镜像源... (已完成)
echo.
echo 已在 backend 目录下创建 pip.ini，自动使用清华源。
echo.

:: 设置 HuggingFace 镜像环境变量
echo [2/3] 配置 HuggingFace 下载镜像...
setx HF_ENDPOINT "https://hf-mirror.com" >nul
echo ✅ HuggingFace 镜像已配置为 hf-mirror.com
echo.
echo 提示：如不想设置系统变量，也可以在终端直接运行：
echo   set HF_ENDPOINT=https://hf-mirror.com
echo.

:: 安装依赖
echo [3/3] 开始安装 Python 依赖...
echo.
pip install -r requirements.txt

echo.
echo ========================================
echo   安装完成，请重启后端服务
echo ========================================
echo.
pause