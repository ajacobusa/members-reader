@echo off
rem Run the test suite with THIS drive's portable python + packages.
rem Usage: test.bat              (full suite)
rem        test.bat -q quoteforge_tests\test_admin.py   (any pytest args)
setlocal
cd /d "%~dp0"
set "PYTHONNOUSERSITE=1"
if "%~1"=="" (
  "%~dp0python\python.exe" -m pytest -q --no-header -p no:cacheprovider
) else (
  "%~dp0python\python.exe" -m pytest %*
)
endlocal
