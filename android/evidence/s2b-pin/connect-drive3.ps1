$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'
$tokFile = 'C:\Users\hello\.maza-token'
$tok = (Get-Content $tokFile -Raw).Trim()

# bring app to front
& $adb -s emulator-5554 shell am start -n com.mazawallet/.MainActivity
Start-Sleep -Seconds 3

# focus token field, type token
& $adb -s emulator-5554 shell input tap 800 455
Start-Sleep -Milliseconds 900
echo $tok | & $adb -s emulator-5554 shell input text $tok
Start-Sleep -Milliseconds 700

# dismiss soft keyboard by tapping the non-editable 'Server URL' label row
& $adb -s emulator-5554 shell input tap 800 294
Start-Sleep -Milliseconds 1200

# verify token landed (masked bullets in dump), then tap CONNECT
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui5.xml
& $adb -s emulator-5554 shell input tap 800 576
Start-Sleep -Seconds 8
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui6.xml
Remove-Item $tokFile -Force
Write-Host ('TOKENFILE-DELETED=' + (-not (Test-Path $tokFile)))
