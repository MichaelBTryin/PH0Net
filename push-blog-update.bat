@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

rem Deterministic blog sync + push for GitHub Pages mirror.
rem Usage:
rem   push-blog-update.bat "commit message" [remote]
rem   push-blog-update.bat "commit message" [remote] "C:\path\to\posts.json"

if "%~1"=="" (
  echo ERROR: Commit message is required.
  echo Usage: push-blog-update.bat "commit message" [remote] [local_posts_json]
  exit /b 1
)

set "COMMIT_MSG=%~1"
set "REMOTE=%~2"
if "%REMOTE%"=="" set "REMOTE=origin"
set "LOCAL_POSTS_JSON=%~3"

if not "%LOCAL_POSTS_JSON%"=="" (
  if not exist "%LOCAL_POSTS_JSON%" (
    echo ERROR: LOCAL_POSTS_JSON path does not exist: %LOCAL_POSTS_JSON%
    exit /b 1
  )
  set "NEXUS_BLOG_LOCAL_POSTS=%LOCAL_POSTS_JSON%"
)

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

echo [blog-push] Repo: %CD%
echo [blog-push] Branch: %BRANCH%
echo [blog-push] Remote: %REMOTE%
if not "%NEXUS_BLOG_LOCAL_POSTS%"=="" echo [blog-push] Source override: %NEXUS_BLOG_LOCAL_POSTS%
echo.

echo [1/5] Building blog mirror...
python --version >nul 2>&1
if errorlevel 1 (
  py -3 --version >nul 2>&1
  if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    exit /b 1
  )
  py -3 scripts\build_blog.py
) else (
  python scripts\build_blog.py
)
if errorlevel 1 (
  echo ERROR: build_blog.py failed.
  exit /b 1
)

echo [2/5] Validating generated cache...
if not exist "blog\data\posts-cache.json" (
  echo ERROR: Missing blog\data\posts-cache.json after build.
  exit /b 1
)

for /f %%C in ('powershell -NoProfile -Command "$p='"'"'blog/data/posts-cache.json'"'"'; $j=Get-Content -LiteralPath $p -Raw | ConvertFrom-Json; @($j.posts).Count"') do set "POST_COUNT=%%C"
if "%POST_COUNT%"=="" (
  echo ERROR: Could not read post count from cache.
  exit /b 1
)
if %POST_COUNT% LSS 1 (
  echo ERROR: Build produced zero posts. Aborting push.
  exit /b 1
)

echo [blog-push] Post count: %POST_COUNT%
powershell -NoProfile -Command "$p='blog/data/posts-cache.json'; $j=Get-Content -LiteralPath $p -Raw | ConvertFrom-Json; $j.posts | Select-Object -First 5 | ForEach-Object { Write-Host (' - ' + $_.id + ' | ' + $_.title) }"

echo [3/5] Staging changes...
git add -A
if errorlevel 1 (
  echo ERROR: git add failed.
  exit /b 1
)

git diff --cached --quiet
if not errorlevel 1 (
  echo ERROR: No changes to commit after blog build.
  exit /b 1
)

echo [4/5] Committing...
git commit -m "%COMMIT_MSG%"
if errorlevel 1 (
  echo ERROR: git commit failed.
  exit /b 1
)

echo [5/5] Pushing...
git push "%REMOTE%" "%BRANCH%"
if errorlevel 1 (
  echo ERROR: git push failed.
  exit /b 1
)

echo.
echo [blog-push] Success: pushed %POST_COUNT% mirrored post(s) to %REMOTE%/%BRANCH%
exit /b 0
