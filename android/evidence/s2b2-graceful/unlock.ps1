$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'

& $adb -s emulator-5554 shell input tap 800 375
Start-Sleep -Milliseconds 900
& $adb -s emulator-5554 shell input text 2468
Start-Sleep -Milliseconds 900
& $adb -s emulator-5554 shell input keyevent 66
Start-Sleep -Milliseconds 1500
& $adb -s emulator-5554 shell input tap 800 496
Start-Sleep -Milliseconds 5000
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-post-unlock1.xml
& $adb -s emulator-5554 pull /sdcard/ui-post-unlock1.xml C:\Users\hello\s2b2-pre\ui-post-unlock1.xml
& $adb -s emulator-5554 shell screencap -p /sdcard/post-unlock1.png
& $adb -s emulator-5554 pull /sdcard/post-unlock1.png C:\Users\hello\s2b2-pre\post-unlock1.png
Write-Host 'UNLOCK-STEP1-DONE'
