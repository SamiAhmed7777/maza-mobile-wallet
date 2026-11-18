# W4-DEV: offline SEND attempt. Fills the BENCH send form with a real external address
# and taps SEND, then leaves the result copy on screen for the capture.
# Bounds (this build): recipient [24,232][1576,300] -> (800,266); amount [24,384][1576,452] -> (800,418);
# SEND button [24,492][1576,564] -> (800,528).
$ErrorActionPreference = 'Stop'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'
& $adb -s emulator-5554 shell input tap 800 266
Start-Sleep -Milliseconds 800
& $adb -s emulator-5554 shell input text MLRe5sWp7LE3skDMQhFbkfd2n5XcZdpKMs
Start-Sleep -Milliseconds 800
& $adb -s emulator-5554 shell input tap 800 418
Start-Sleep -Milliseconds 800
& $adb -s emulator-5554 shell input text 1
Start-Sleep -Milliseconds 800
& $adb -s emulator-5554 shell input tap 800 528
Start-Sleep -Seconds 12
Write-Output 'SEND-TAPPED'
