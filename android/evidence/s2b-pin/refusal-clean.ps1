$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'

# clean refusal demo: correct PIN while a throttle window is live
& $adb -s emulator-5554 shell input tap 800 375
Start-Sleep -Milliseconds 900
& $adb -s emulator-5554 shell input text 2468
Start-Sleep -Milliseconds 600
& $adb -s emulator-5554 shell input tap 800 262
Start-Sleep -Milliseconds 1300
& $adb -s emulator-5554 shell input tap 800 496
Start-Sleep -Milliseconds 4000
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-refusal-clean.xml
& $adb -s emulator-5554 shell screencap -p /sdcard/s6-refusal-clean.png
& $adb -s emulator-5554 pull /sdcard/ui-refusal-clean.xml C:\Users\hello\ui-refusal-clean.xml
& $adb -s emulator-5554 pull /sdcard/s6-refusal-clean.png C:\Users\hello\s6-refusal-clean.png
Write-Host 'CLEAN-REFUSAL-DONE'
