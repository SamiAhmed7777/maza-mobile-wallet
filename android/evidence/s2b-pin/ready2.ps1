$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'

# post-drain: clear field, retype, verify bullets via dump, THEN tap UNLOCK
& $adb -s emulator-5554 shell input tap 800 375
Start-Sleep -Milliseconds 900
& $adb -s emulator-5554 shell input keyevent 123
Start-Sleep -Milliseconds 300
1..16 | ForEach-Object { & $adb -s emulator-5554 shell input keyevent 67; Start-Sleep -Milliseconds 120 }
Start-Sleep -Milliseconds 400
& $adb -s emulator-5554 shell input text 2468
Start-Sleep -Milliseconds 800
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-ready2.xml
& $adb -s emulator-5554 pull /sdcard/ui-ready2.xml C:\Users\hello\ui-ready2.xml
Write-Host 'READY2-DONE'
