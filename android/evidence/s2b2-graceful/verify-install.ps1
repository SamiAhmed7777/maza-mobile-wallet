$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'
Start-Sleep -Seconds 25
& $adb connect 127.0.0.1:5555
Start-Sleep -Seconds 3
& $adb -s emulator-5554 shell pm list packages com.mazawallet
& $adb -s emulator-5554 shell dumpsys package com.mazawallet | Select-String 'lastUpdateTime|firstInstallTime|versionName'
& $adb -s emulator-5554 shell md5sum $(& $adb -s emulator-5554 shell pm path com.mazawallet | ForEach-Object { ($_ -replace 'package:','').Trim() })
Write-Host 'INSTALL-VERIFY-DONE'
