$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'
& $adb -s emulator-5554 shell input tap 800 578
Start-Sleep -Milliseconds 1400
& $adb -s emulator-5554 shell input tap 800 468
Start-Sleep -Milliseconds 700
& $adb -s emulator-5554 shell input text 1111
Start-Sleep -Milliseconds 600
& $adb -s emulator-5554 shell input keyevent 66
Start-Sleep -Milliseconds 700
& $adb -s emulator-5554 shell input tap 1150 547
& $adb -s emulator-5554 shell screencap -p /sdcard/t1.png
& $adb -s emulator-5554 shell screencap -p /sdcard/t2.png
& $adb -s emulator-5554 shell screencap -p /sdcard/t3.png
& $adb -s emulator-5554 pull /sdcard/t1.png C:\Users\hello\w3bench\t1.png
& $adb -s emulator-5554 pull /sdcard/t2.png C:\Users\hello\w3bench\t2.png
& $adb -s emulator-5554 pull /sdcard/t3.png C:\Users\hello\w3bench\t3.png
& $adb -s emulator-5554 shell uiautomator dump /sdcard/t3.xml
& $adb -s emulator-5554 pull /sdcard/t3.xml C:\Users\hello\w3bench\t3.xml
Write-Host 'WRONGPIN-DONE'
