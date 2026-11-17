$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'
$tok = (Get-Content 'C:\Users\hello\.maza-token' -Raw).Trim()

& $adb -s emulator-5554 shell am force-stop com.mazawallet
Start-Sleep -Seconds 2
& $adb -s emulator-5554 shell am start -n com.mazawallet/.MainActivity
Start-Sleep -Seconds 4
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-post-connect-card.xml
& $adb -s emulator-5554 pull /sdcard/ui-post-connect-card.xml C:\Users\hello\s2b2-pre\ui-post-connect-card.xml

& $adb -s emulator-5554 shell input tap 800 455
Start-Sleep -Milliseconds 900
& $adb -s emulator-5554 shell input text $tok
Start-Sleep -Milliseconds 700
& $adb -s emulator-5554 shell input tap 800 294
Start-Sleep -Milliseconds 1200
& $adb -s emulator-5554 shell input tap 800 576
Start-Sleep -Seconds 12
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-post-lock1.xml
& $adb -s emulator-5554 shell screencap -p /sdcard/post-lock1.png
& $adb -s emulator-5554 pull /sdcard/ui-post-lock1.xml C:\Users\hello\s2b2-pre\ui-post-lock1.xml
& $adb -s emulator-5554 pull /sdcard/post-lock1.png C:\Users\hello\s2b2-pre\post-lock1.png
Start-Sleep -Seconds 15
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-post-lock2.xml
& $adb -s emulator-5554 shell screencap -p /sdcard/post-lock2.png
& $adb -s emulator-5554 pull /sdcard/ui-post-lock2.xml C:\Users\hello\s2b2-pre\ui-post-lock2.xml
& $adb -s emulator-5554 pull /sdcard/post-lock2.png C:\Users\hello\s2b2-pre\post-lock2.png
Remove-Item 'C:\Users\hello\.maza-token' -Force
Write-Host ('TOKENFILE-DELETED=' + (-not (Test-Path 'C:\Users\hello\.maza-token')))
Write-Host 'POST-CONNECT-DONE'
