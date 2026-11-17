$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'

& $adb -s emulator-5554 push C:\Users\hello\s2b2-pre\maza-s2b2.apk /sdcard/maza-s2b2.apk
& $adb -s emulator-5554 shell ls -l /sdcard/maza-s2b2.apk
& $adb -s emulator-5554 shell pm install -r /sdcard/maza-s2b2.apk
Write-Host 'INSTALL-ISSUED'
