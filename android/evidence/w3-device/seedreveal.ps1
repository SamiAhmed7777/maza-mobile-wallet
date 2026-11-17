$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'
& $adb -s emulator-5554 shell input tap 800 578
Start-Sleep -Milliseconds 1400
& $adb -s emulator-5554 shell input tap 800 468
Start-Sleep -Milliseconds 700
& $adb -s emulator-5554 shell input text 2468
Start-Sleep -Milliseconds 600
& $adb -s emulator-5554 shell input keyevent 66
Start-Sleep -Milliseconds 700
& $adb -s emulator-5554 shell input tap 1150 547
Start-Sleep -Milliseconds 2500
& $adb -s emulator-5554 shell screencap -p /sdcard/seed.png
& $adb -s emulator-5554 shell uiautomator dump /sdcard/seed.xml
& $adb -s emulator-5554 pull /sdcard/seed.png C:\Users\hello\w3bench\seed.png
& $adb -s emulator-5554 pull /sdcard/seed.xml C:\Users\hello\w3bench\seed.xml
Write-Host 'SEEDREVEAL-DONE'
