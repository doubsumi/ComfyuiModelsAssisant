@echo off
setlocal

echo ==============================
echo  Creating project structure...
echo ==============================

REM 根目录文件
type nul > comfyui-server.py

REM backend
if not exist backend mkdir backend
type nul > backend\__init__.py
type nul > backend\config.py

REM backend\routes
if not exist backend\routes mkdir backend\routes
type nul > backend\routes\__init__.py
type nul > backend\routes\base.py
type nul > backend\routes\model_routes.py
type nul > backend\routes\registry_routes.py

REM backend\services
if not exist backend\services mkdir backend\services
type nul > backend\services\__init__.py
type nul > backend\services\model_scanner.py

REM backend\storage
if not exist backend\storage mkdir backend\storage
type nul > backend\storage\__init__.py
type nul > backend\storage\json_store.py
type nul > backend\storage\cache_store.py
type nul > backend\storage\registry_store.py

REM frontend
if not exist frontend mkdir frontend
type nul > frontend\index.html

REM data（也可以留到程序启动时自动创建，这里一并建好）
if not exist data mkdir data

echo.
echo ==============================
echo  Done. Project structure:
echo ==============================
tree /f

endlocal
pause