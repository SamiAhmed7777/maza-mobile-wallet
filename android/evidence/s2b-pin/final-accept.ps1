$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'

& $adb -s emulator-5554 shell input tap 800 375
Start-Sleep -Milliseconds 900
& $adb -s emulator-5554 shell input text 2468
Start-Sleep -Milliseconds 900
& $adb -s emulator-5554 shell input keyevent 66
Start-Sleep -Milliseconds 1200
& $adb -s emulator-5554 shell input tap 800 496
Start-Sleep -Milliseconds 5000
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-final-accept.xml
& $adb -s emulator-5554 shell screencap -p /sdcard/s9-unlocked.png
& $adb -s emulator-5554 pull /sdcard/ui-final-accept.xml C:\Users\hello\ui-final-accept.xml
& $adb -s emulator-5554 pull /sdcard/s9-unlocked.png C:\Users\hello\s9-unlocked.png
Write-Host 'FINAL-ACCEPT-ATTEMPT-DONE'
