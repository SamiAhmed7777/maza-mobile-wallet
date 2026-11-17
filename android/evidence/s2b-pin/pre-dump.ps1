$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'

# focus + type + dump BEFORE unlocking (verify field content via bullet count)
& $adb -s emulator-5554 shell input tap 800 375
Start-Sleep -Milliseconds 1000
& $adb -s emulator-5554 shell input text 2468
Start-Sleep -Milliseconds 800
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-pre.xml
& $adb -s emulator-5554 pull /sdcard/ui-pre.xml C:\Users\hello\ui-pre.xml
& $adb -s emulator-5554 shell screencap -p /sdcard/s8-pre.png
& $adb -s emulator-5554 pull /sdcard/s8-pre.png C:\Users\hello\s8-pre.png
Write-Host 'PRE-UNLOCK-DUMP-DONE'
