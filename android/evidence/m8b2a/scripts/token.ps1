$ErrorActionPreference = 'Continue'
# M8b2a lane: type the bench token (arrives on STDIN, first line) into the Connect card, then CONNECT.
# Token is never echoed, never in this script, never in a file; the typed field is password-masked.
# Coordinates from a uiautomator dump of build 1a287b66 (2026-11-27 03:03): token (800,489), CONNECT (800,610).
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'
$dev = 'emulator-5554'
$cap = 'C:\Users\hello\maza-bench-lane\cap'
$tok = [Console]::In.ReadLine()
if ($null -eq $tok) { Write-Output 'NO-TOKEN-ON-STDIN'; exit 2 }
$tok = $tok.Trim()
Write-Output ('TOKEN-LEN ' + $tok.Length)
& $adb -s $dev shell input tap 800 489 2>&1 | Out-Null
Start-Sleep -Milliseconds 900
& $adb -s $dev shell input text $tok 2>&1 | Out-Null
$tok = $null
Start-Sleep -Milliseconds 900
& $adb -s $dev shell uiautomator dump /sdcard/ui_tok.xml 2>&1 | Out-Null
& $adb -s $dev pull /sdcard/ui_tok.xml "$cap\ui_tok.xml" 2>&1 | Out-Null
& $adb -s $dev shell rm -f /sdcard/ui_tok.xml 2>&1 | Out-Null
$typed = -1
if (Test-Path "$cap\ui_tok.xml") {
    $x = Get-Content "$cap\ui_tok.xml" -Raw -Encoding UTF8
    $m = [regex]::Match($x, 'text="([^"]*)"[^>]*password="true"')
    if ($m.Success) { $typed = $m.Groups[1].Value.Length }
    Remove-Item "$cap\ui_tok.xml" -Force
}
Write-Output ('TYPED-LEN ' + $typed)
& $adb -s $dev shell input tap 800 610 2>&1 | Out-Null
Write-Output 'CONNECT-TAPPED'
Start-Sleep -Seconds 9
& $adb -s $dev shell uiautomator dump /sdcard/ui_after.xml 2>&1 | Out-Null
& $adb -s $dev pull /sdcard/ui_after.xml "$cap\b_after_connect.xml" 2>&1 | Out-Null
& $adb -s $dev shell rm -f /sdcard/ui_after.xml 2>&1 | Out-Null
Write-Output 'AFTER-DUMP-PULLED'
