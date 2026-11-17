$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'

& $adb -s emulator-5554 shell input tap 800 375
Start-Sleep -Milliseconds 900
& $adb -s emulator-5554 shell input text 2468
Start-Sleep -Milliseconds 800
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-r1.xml
& $adb -s emulator-5554 pull /sdcard/ui-r1.xml C:\Users\hello\ui-r1.xml
& $adb -s emulator-5554 shell input tap 800 496
Start-Sleep -Milliseconds 6000
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-r2.xml
& $adb -s emulator-5554 pull /sdcard/ui-r2.xml C:\Users\hello\ui-r2.xml
Write-Host 'RELOCK-UNLOCK-ATTEMPTED'
