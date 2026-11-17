$ErrorActionPreference = 'Stop'
# W3-a addendum: connect to the PUBLIC front door with the token typed from the
# staged file, then delete the file. Coordinates resolved from a pre-capture
# uiautomator dump of THIS build (token field 800,455; CONNECT 800,576).
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'
$tok = (Get-Content 'C:\Users\hello\.maza-token' -Raw).Trim()
& $adb -s emulator-5554 shell input tap 800 455
Start-Sleep -Milliseconds 900
& $adb -s emulator-5554 shell input text $tok
Start-Sleep -Milliseconds 900
# dismiss the soft keyboard on the non-editable "Server URL" label row
& $adb -s emulator-5554 shell input tap 800 294
Start-Sleep -Milliseconds 1200
& $adb -s emulator-5554 shell input tap 800 576
Start-Sleep -Seconds 8
Remove-Item 'C:\Users\hello\.maza-token' -Force
Write-Host ('TOKENFILE-DELETED=' + (-not (Test-Path 'C:\Users\hello\.maza-token')))
