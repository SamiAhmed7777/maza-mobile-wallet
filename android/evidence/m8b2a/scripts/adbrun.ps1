param([string]$B64 = '')
$ErrorActionPreference = 'Continue'
# M8b2a lane: run a list of adb commands (base64 of UTF-8 text in -B64, else STDIN), sequentially, on SAMI-PC.
# Line verbs:  sleep <sec> | echo <text> | shell <device shell command> | pull <remote> <local> | push <local> <remote> | raw <adb args>
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'
$dev = 'emulator-5554'
function Emit { param($o) if ($o -is [System.Management.Automation.ErrorRecord]) { Write-Output ('[e] ' + $o.Exception.Message) } else { Write-Output $o } }
if ($B64 -ne '') {
    $text = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($B64))
    $lines = $text -split "`n"
} else {
    $lines = @([Console]::In.ReadToEnd() -split "`n")
}
foreach ($l in $lines) {
    $line = $l.Trim()
    if ($line.Length -eq 0 -or $line.StartsWith('#')) { continue }
    if ($line.StartsWith('sleep ')) { Start-Sleep -Milliseconds ([int]([double]$line.Substring(6).Trim() * 1000)); continue }
    if ($line.StartsWith('echo ')) { Write-Output ('## ' + $line.Substring(5)); continue }
    # qshell = run WITHOUT echoing the command line (typing a credential)
    if ($line.StartsWith('qshell ')) { Write-Output '> qshell <redacted>'; & $adb -s $dev shell $line.Substring(7) 2>&1 | ForEach-Object { Emit $_ }; continue }
    Write-Output ('> ' + $line)
    if ($line.StartsWith('ps ')) { Invoke-Expression $line.Substring(3) 2>&1 | ForEach-Object { Emit $_ }; continue }
    if ($line.StartsWith('shell ')) { & $adb -s $dev shell $line.Substring(6) 2>&1 | ForEach-Object { Emit $_ }; continue }
    if ($line.StartsWith('pull ')) { $i = $line.IndexOf(' ', 6); & $adb -s $dev pull $line.Substring(6, $i - 6) $line.Substring($i + 1) 2>&1 | ForEach-Object { Emit $_ }; continue }
    if ($line.StartsWith('push ')) { $i = $line.IndexOf(' ', 6); & $adb -s $dev push $line.Substring(6, $i - 6) $line.Substring($i + 1) 2>&1 | ForEach-Object { Emit $_ }; continue }
    if ($line.StartsWith('raw ')) { & $adb -s $dev ($line.Substring(4).Split(' ')) 2>&1 | ForEach-Object { Emit $_ }; continue }
    Write-Output 'ERR unknown verb'
}
Write-Output '## ROUND-DONE'
