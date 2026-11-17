$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'
$tok = (Get-Content 'C:\Users\hello\.maza-token' -Raw).Trim()
& $adb -s emulator-5554 shell input tap 800 455
Start-Sleep -Milliseconds 900
& $adb -s emulator-5554 shell input text $tok
Start-Sleep -Milliseconds 900
# dismiss soft keyboard by tapping the non-editable 'Server URL' label row
& $adb -s emulator-5554 shell input tap 800 294
Start-Sleep -Milliseconds 1200
& $adb -s emulator-5554 shell input tap 800 576
Start-Sleep -Seconds 8
Remove-Item 'C:\Users\hello\.maza-token' -Force
Write-Host ('TOKENFILE-DELETED=' + (-not (Test-Path 'C:\Users\hello\.maza-token')))
