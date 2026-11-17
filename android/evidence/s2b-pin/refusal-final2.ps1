$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'

# Deterministic correct-PIN refusal driver v2 (single script):
# clear the field (throttle refusals never clear it), prove it EMPTY,
# type the known test PIN, prove exactly 4 bullets, press UNLOCK once,
# prove the throttled refusal with the field retained.
& $adb -s emulator-5554 shell input tap 800 375
Start-Sleep -Milliseconds 800
& $adb -s emulator-5554 shell input keyevent 123
Start-Sleep -Milliseconds 300
1..20 | ForEach-Object { & $adb -s emulator-5554 shell input keyevent 67; Start-Sleep -Milliseconds 130 }
Start-Sleep -Milliseconds 400
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-ref2-cleared.xml
& $adb -s emulator-5554 pull /sdcard/ui-ref2-cleared.xml C:\Users\hello\ui-ref2-cleared.xml
& $adb -s emulator-5554 shell input text 2468
Start-Sleep -Milliseconds 800
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-ref2-pre.xml
& $adb -s emulator-5554 pull /sdcard/ui-ref2-pre.xml C:\Users\hello\ui-ref2-pre.xml
& $adb -s emulator-5554 shell input tap 800 496
Start-Sleep -Milliseconds 5000
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-ref2-post.xml
& $adb -s emulator-5554 shell screencap -p /sdcard/s12-refusal-final.png
& $adb -s emulator-5554 pull /sdcard/ui-ref2-post.xml C:\Users\hello\ui-ref2-post.xml
& $adb -s emulator-5554 pull /sdcard/s12-refusal-final.png C:\Users\hello\s12-refusal-final.png
Write-Host 'REFUSAL2-DRIVER-DONE'
