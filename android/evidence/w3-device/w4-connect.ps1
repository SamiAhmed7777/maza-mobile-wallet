# W4-DEV: Connect to the PUBLIC front door (https://mazatest.sami-host.me) with the token
# typed from the ssh-stdin-staged file, then delete that file.
# Coordinates resolved from a pre-capture uiautomator dump of THIS build:
#   token field (800,455), CONNECT (800,576); tap (800,294) dismisses the soft keyboard.
$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'
$tok = (Get-Content 'C:\Users\hello\.maza-token' -Raw).Trim()
& $adb -s emulator-5554 shell input tap 800 455
Start-Sleep -Milliseconds 900
& $adb -s emulator-5554 shell input text $tok
Start-Sleep -Milliseconds 900
& $adb -s emulator-5554 shell input tap 800 294
Start-Sleep -Milliseconds 1200
& $adb -s emulator-5554 shell input tap 800 576
Start-Sleep -Seconds 9
Remove-Item 'C:\Users\hello\.maza-token' -Force
Write-Output ('TOKENFILE-DELETED=' + (-not (Test-Path 'C:\Users\hello\.maza-token')))
