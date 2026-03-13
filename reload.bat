@echo off
set "target=pythonw.exe"
set "copysource=C:\Users\azt12\OneDrive\Documents\Computing\Shelved Projects\Jean Projects\Anki SBX\ajs_addon"
set "copydest=C:\Users\azt12\AppData\Roaming\Anki2\addons21\ajs_addon"

::REPLACE OLD FILES WITH FRESH EDITS
xcopy /e /i /y "%copysource%" "%copydest%"

::KILL ANKI
qprocess %target% 
if ERRORLEVEL 1 (goto :skipkill)

set /a retries=1
:kill
if %retries% lss 4 (
taskkill /IM %target% /F /T
  if not ERRORLEVEL 1 (echo Kill Complete & goto :endkill) else (
    echo Kill Attempt %retries% & echo Failed
    set /a retries+=1 & goto :kill)
	)
:endkill
if ERRORLEVEL 1 (echo Kill Failed & EXIT /B)
:skipkill

::START ANKI
set /a retries=1
:start
if %retries% lss 4 (
start "" "C:\Users\azt12\AppData\Local\Programs\Anki\anki.exe"
timeout /t 2
qprocess %target% 
  if not ERRORLEVEL 1 (echo Restart Complete & goto :endstart) else (
  set /a retries+=1 & goto :start))
:endstart
if ERRORLEVEL 1 (echo Restart Failed Anki & EXIT /B)
