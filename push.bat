@echo off
setlocal

set "msg=%~1"
if "%msg%"=="" set "msg=auto update %date% %time%"

git add .
if errorlevel 1 goto :fail

git commit -m "%msg%"
if errorlevel 1 goto :fail

git push
if errorlevel 1 goto :fail

echo.
echo Pushed successfully.
goto :end

:fail
echo.
echo Push failed.
exit /b 1

:end
endlocal
