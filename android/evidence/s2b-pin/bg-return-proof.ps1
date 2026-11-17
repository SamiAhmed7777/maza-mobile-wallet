$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'

# P4b continuous driver: unlocked dump -> launcher transition -> background
# span -> resume -> locked dump. One script, no intervening input.
& $adb -s emulator-5554 shell input tap 800 375
Start-Sleep -Milliseconds 700
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-p4b-pre.xml
& $adb -s emulator-5554 pull /sdcard/ui-p4b-pre.xml C:\Users\hello\ui-p4b-pre.xml
& $adb -s emulator-5554 shell input tap 800 496
Start-Sleep -Milliseconds 6000
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-p4b-unlocked.xml
& $adb -s emulator-5554 pull /sdcard/ui-p4b-unlocked.xml C:\Users\hello\ui-p4b-unlocked.xml
& $adb -s emulator-5554 shell screencap -p /sdcard/s13-unlocked-pre-bg.png
& $adb -s emulator-5554 pull /sdcard/s13-unlocked-pre-bg.png C:\Users\hello\s13-unlocked-pre-bg.png
& $adb -s emulator-5554 shell monkey -p com.uncube.launcher3 -c android.intent.category.LAUNCHER 1
Start-Sleep -Seconds 4
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-p4b-launcher.xml
& $adb -s emulator-5554 pull /sdcard/ui-p4b-launcher.xml C:\Users\hello\ui-p4b-launcher.xml
Start-Sleep -Seconds 330
& $adb -s emulator-5554 shell am start -n com.mazawallet/.MainActivity
Start-Sleep -Milliseconds 7000
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-p4b-resumed.xml
& $adb -s emulator-5554 shell screencap -p /sdcard/s14-bg-return-locked.png
& $adb -s emulator-5554 pull /sdcard/ui-p4b-resumed.xml C:\Users\hello\ui-p4b-resumed.xml
& $adb -s emulator-5554 pull /sdcard/s14-bg-return-locked.png C:\Users\hello\s14-bg-return-locked.png
Write-Host 'P4B-DRIVER-DONE'
