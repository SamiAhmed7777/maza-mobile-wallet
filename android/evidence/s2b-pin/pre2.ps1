$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'

& $adb -s emulator-5554 shell input tap 800 375
Start-Sleep -Milliseconds 1000
& $adb -s emulator-5554 shell input text 2468
Start-Sleep -Milliseconds 1000
& $adb -s emulator-5554 shell input keyevent 66
Start-Sleep -Milliseconds 1500
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-pre2.xml
& $adb -s emulator-5554 pull /sdcard/ui-pre2.xml C:\Users\hello\ui-pre2.xml
Write-Host 'PRE2-DONE'
