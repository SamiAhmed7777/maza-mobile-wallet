$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'

# let the current short window expire, then 6th wrong attempt -> 60s backoff
Start-Sleep -Seconds 12
& $adb -s emulator-5554 shell input tap 800 375
Start-Sleep -Milliseconds 800
& $adb -s emulator-5554 shell input text 9999
Start-Sleep -Milliseconds 500
& $adb -s emulator-5554 shell input tap 800 262
Start-Sleep -Milliseconds 1200
& $adb -s emulator-5554 shell input tap 800 496
Start-Sleep -Milliseconds 2500
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-backoff60.xml
& $adb -s emulator-5554 shell screencap -p /sdcard/s5-backoff60.png
& $adb -s emulator-5554 pull /sdcard/ui-backoff60.xml C:\Users\hello\ui-backoff60.xml
& $adb -s emulator-5554 pull /sdcard/s5-backoff60.png C:\Users\hello\s5-backoff60.png
Write-Host 'SIXTH-WRONG-DONE'

# immediately: CORRECT pin during throttle -> must be refused
& $adb -s emulator-5554 shell input tap 800 375
Start-Sleep -Milliseconds 800
& $adb -s emulator-5554 shell input text 2468
Start-Sleep -Milliseconds 500
& $adb -s emulator-5554 shell input tap 800 262
Start-Sleep -Milliseconds 1200
& $adb -s emulator-5554 shell input tap 800 496
Start-Sleep -Milliseconds 2500
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-refused-correct.xml
& $adb -s emulator-5554 shell screencap -p /sdcard/s6-refused-correct.png
& $adb -s emulator-5554 pull /sdcard/ui-refused-correct.xml C:\Users\hello\ui-refused-correct.xml
& $adb -s emulator-5554 pull /sdcard/s6-refused-correct.png C:\Users\hello\s6-refused-correct.png
Write-Host 'REFUSAL-DONE'
