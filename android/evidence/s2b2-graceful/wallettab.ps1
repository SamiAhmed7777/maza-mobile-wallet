$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'
& $adb -s emulator-5554 shell input tap 1440 858
Start-Sleep -Seconds 4
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-post-wallet-tab.xml
& $adb -s emulator-5554 pull /sdcard/ui-post-wallet-tab.xml C:\Users\hello\s2b2-pre\ui-post-wallet-tab.xml
& $adb -s emulator-5554 shell screencap -p /sdcard/post-wallet-tab.png
& $adb -s emulator-5554 pull /sdcard/post-wallet-tab.png C:\Users\hello\s2b2-pre\post-wallet-tab.png
Write-Host 'WALLET-TAB-DONE'
