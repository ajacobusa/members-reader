@echo off
rem ============================================================
rem  Portable launcher for the Etsy/Gelato (QuoteForge) project.
rem  Everything lives on THIS drive: python\ + its packages,
rem  the code, and data\. Nothing depends on C:.
rem
rem  Usage:   run.bat <admin command and args>
rem  Example: run.bat rebuild-site
rem           run.bat deploy-status
rem ============================================================
setlocal
cd /d "%~dp0"
rem Use ONLY this drive's python + packages (ignore any system user-site).
set "PYTHONNOUSERSITE=1"
"%~dp0python\python.exe" -m quoteforge.admin %*
endlocal
