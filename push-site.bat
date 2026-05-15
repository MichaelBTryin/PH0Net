@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Push all tracked changes to GitHub (for PH0Net site or future private repos).
rem Usage: push-site.bat "commit message" [remote]
rem Example: push-site.bat "Update homepage links"
rem Example: push-site.bat "Merith memory backup" origin

if "%~1"=="" (
  echo ERROR: Commit message is required.
  echo Usage: push-site.bat "commit message" [remote]
  exit /b 1
)

set "COMMIT_MSG=%~1"
set "REMOTE=%~2"
if "%REMOTE%"=="" set "REMOTE=origin"

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo ERROR: Not inside a git repository.
  exit /b 1
)

for /f "delims=" %%B in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "BRANCH=%%B"
if "%BRANCH%"=="" (
  echo ERROR: Could not determine current branch.
  exit /b 1
)

if "%BRANCH%"=="HEAD" (
  echo ERROR: Detached HEAD state. Checkout a branch before pushing.
  exit /b 1
)

echo [push-site] Repository: %CD%
echo [push-site] Branch: %BRANCH%
echo [push-site] Remote: %REMOTE%
echo [push-site] Message: %COMMIT_MSG%
echo.

git add -A
if errorlevel 1 (
  echo ERROR: git add failed.
  exit /b 1
)

git diff --cached --quiet
if not errorlevel 1 (
  echo ERROR: No changes to commit.
  exit /b 1
)

git commit -m "%COMMIT_MSG%"
if errorlevel 1 (
  echo ERROR: git commit failed.
  exit /b 1
)

git push "%REMOTE%" "%BRANCH%"
if errorlevel 1 (
  echo ERROR: git push failed.
  exit /b 1
)

echo.
echo [push-site] Success: pushed to %REMOTE%/%BRANCH%
exit /b 0
