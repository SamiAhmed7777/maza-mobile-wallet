$ErrorActionPreference = 'Continue'
# M8b2a lane: back up the installed APK, then IN-PLACE update (pm install -r keeps app data).
# Never uninstalls, never clears data. Expected new md5: 1a287b66e3ee91a61a1fd8f66c7b51c4
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'
$dir = 'C:\Users\hello\maza-bench-lane'
$dev = 'emulator-5554'
Write-Output '=== PRE ==='
$p = ((& $adb -s $dev shell pm path com.mazawallet) -join ' ')
Write-Output ('PMPATH ' + $p.Trim())
& $adb -s $dev shell dumpsys package com.mazawallet | Select-String 'lastUpdateTime|firstInstallTime|versionName|versionCode' | ForEach-Object { 'PRE ' + $_.Line.Trim() }
$apkPath = ($p -replace 'package:', '').Trim()
Write-Output '=== BACKUP OLD APK ==='
if (Test-Path "$dir\old-installed.apk") { Remove-Item "$dir\old-installed.apk" -Force }
& $adb -s $dev pull $apkPath "$dir\old-installed.apk" 2>&1 | ForEach-Object { $_ }
$old = Get-Item "$dir\old-installed.apk" -ErrorAction SilentlyContinue
if ($old) { Write-Output ('OLD-APK bytes=' + $old.Length + ' md5=' + (Get-FileHash -Algorithm MD5 "$dir\old-installed.apk").Hash.ToLower()) } else { Write-Output 'OLD-APK MISSING' }
Write-Output '=== PUSH NEW ==='
& $adb -s $dev shell rm -f /sdcard/m8b2a.apk 2>&1 | Out-Null
& $adb -s $dev push "$dir\m8b2a.apk" /sdcard/m8b2a.apk 2>&1 | ForEach-Object { $_ }
& $adb -s $dev shell ls -l /sdcard/m8b2a.apk 2>&1 | ForEach-Object { $_ }
Write-Output '=== INSTALL ==='
& $adb -s $dev shell pm install -r /sdcard/m8b2a.apk 2>&1 | ForEach-Object { $_ }
Write-Output '=== WAIT 25s + RECONNECT ==='
Start-Sleep -Seconds 25
& $adb connect 127.0.0.1:5555 2>&1 | ForEach-Object { $_ }
Start-Sleep -Seconds 3
Write-Output '=== VERIFY ==='
& $adb -s $dev shell pm list packages com.mazawallet 2>&1 | ForEach-Object { $_ }
$p2 = ((& $adb -s $dev shell pm path com.mazawallet) -join ' ')
Write-Output ('PMPATH2 ' + $p2.Trim())
& $adb -s $dev shell dumpsys package com.mazawallet | Select-String 'lastUpdateTime|firstInstallTime|versionName|versionCode' | ForEach-Object { 'POST ' + $_.Line.Trim() }
$apkPath2 = ($p2 -replace 'package:', '').Trim()
& $adb -s $dev shell md5sum $apkPath2 2>&1 | ForEach-Object { 'MD5-DEVICE ' + $_ }
Write-Output ('NEW-APK md5=' + (Get-FileHash -Algorithm MD5 "$dir\m8b2a.apk").Hash.ToLower())
Write-Output 'INSTALL-SCRIPT-DONE'
