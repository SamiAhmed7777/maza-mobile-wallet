$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'
& $adb -s emulator-5554 shell am force-stop com.mazawallet
Start-Sleep -Seconds 2
& $adb -s emulator-5554 shell am start -n com.mazawallet/.MainActivity
Start-Sleep -Seconds 4
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-pre-connect.xml
& $adb -s emulator-5554 pull /sdcard/ui-pre-connect.xml C:\Users\hello\s2b2-pre\ui-pre-connect.xml
Write-Host 'PRE-DUMP-DONE'
