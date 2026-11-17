$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'

# ARM: 5 wrong presses (garbage contents suffice; streak -> 6 opens a 60s window
# on the first post-expiry evaluated press)
foreach ($i in 1..5) {
  & $adb -s emulator-5554 shell input tap 800 375
  Start-Sleep -Milliseconds 600
  & $adb -s emulator-5554 shell input text 9999
  Start-Sleep -Milliseconds 400
  & $adb -s emulator-5554 shell input tap 800 496
  Start-Sleep -Milliseconds 3000
  Write-Host ("ARM2-" + $i)
}
& $adb -s emulator-5554 shell uiautomator dump /sdcard/ui-armed2.xml
& $adb -s emulator-5554 pull /sdcard/ui-armed2.xml C:\Users\hello\ui-armed2.xml
Write-Host 'ARM2-DONE'
