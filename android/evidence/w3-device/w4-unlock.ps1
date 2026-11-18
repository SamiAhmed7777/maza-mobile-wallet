# W4-DEV: PIN unlock on the lock cover (bench PIN 2468, disclosed bench credential).
# Bounds from a pre-capture uiautomator dump: PIN field [36,341][1564,409], UNLOCK [36,460][1564,532].
$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'
& $adb -s emulator-5554 shell input tap 800 375
Start-Sleep -Milliseconds 900
& $adb -s emulator-5554 shell input text 2468
Start-Sleep -Milliseconds 900
& $adb -s emulator-5554 shell input tap 800 496
Start-Sleep -Seconds 4
Write-Output 'UNLOCK-TAPPED'
