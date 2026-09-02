@echo off
set DIR=%~dp0
set GRADLE_VERSION=9.3.1
set DIST=
for /d %%D in ("%USERPROFILE%\.gradle\wrapper\dists\gradle-%GRADLE_VERSION%-bin\*") do (
  if exist "%%~fD\gradle-%GRADLE_VERSION%\bin\gradle.bat" set "DIST=%%~fD\gradle-%GRADLE_VERSION%\bin\gradle.bat"
)
if not defined DIST (
  echo Please run this project with Gradle 9.3.1 installed.
  exit /b 1
)
call "%DIST%" %*
