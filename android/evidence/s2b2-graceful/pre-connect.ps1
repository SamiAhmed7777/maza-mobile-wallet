$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'
$tok = (Get-Content 'C:\Users\hello\.maza-token' -Raw).Trim()

& $adb -s emulator-5554 shell input tap 800 455
Start-Sleep -Milliseconds 900
& $adb -s emulator-5554 shell input text $tok
Start-Sleep -Milliseconds 700
& $adb -s emulator-5554 shell input tap 800 294
Start-Sleep -Milliseconds 1200
& $adb -s emulator-5554 shell input tap 800 576
Start-Sleep -Seconds 12
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-pre-lock.xml
& $adb -s emulator-5554 shell screencap -p /sdcard/pre-lock.png
& $adb -s emulator-5554 pull /sdcard/ui-pre-lock.xml C:\Users\hello\s2b2-pre\ui-pre-lock.xml
& $adb -s emulator-5554 pull /sdcard/pre-lock.png C:\Users\hello\s2b2-pre\pre-lock.png
Remove-Item 'C:\Users\hello\.maza-token' -Force
Write-Host ('TOKENFILE-DELETED=' + (-not (Test-Path 'C:\Users\hello\.maza-token')))
Write-Host 'PRE-CONNECT-DONE'
