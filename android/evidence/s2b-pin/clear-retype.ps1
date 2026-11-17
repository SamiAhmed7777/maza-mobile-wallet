$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'

& $adb -s emulator-5554 shell input tap 800 375
Start-Sleep -Milliseconds 900
& $adb -s emulator-5554 shell input keyevent 123
Start-Sleep -Milliseconds 300
1..12 | ForEach-Object { & $adb -s emulator-5554 shell input keyevent 67; Start-Sleep -Milliseconds 120 }
Start-Sleep -Milliseconds 500
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-cleared.xml
& $adb -s emulator-5554 pull /sdcard/ui-cleared.xml C:\Users\hello\ui-cleared.xml
& $adb -s emulator-5554 shell input text 2468
Start-Sleep -Milliseconds 800
& $adb -s emulator-5554 shell input keyevent 66
Start-Sleep -Milliseconds 1300
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-ready.xml
& $adb -s emulator-5554 pull /sdcard/ui-ready.xml C:\Users\hello\ui-ready.xml
Write-Host 'CLEARED-AND-RETYPED'
