param(
    [string]$Src, [string]$Dst,
    [int]$X, [int]$Y, [int]$W, [int]$H,
    [string]$Label = 'redacted'
)
# M8b2a lane: black-box a rectangle of a PNG (webcam-passthrough camera feed), write a new file,
# then DELETE the unredacted original. Prints both hashes so the transcript shows they differ.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$img = [System.Drawing.Image]::FromFile($Src)
try {
    $bmp = New-Object System.Drawing.Bitmap $img.Width, $img.Height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.DrawImage($img, 0, 0, $img.Width, $img.Height)
    $g.FillRectangle([System.Drawing.Brushes]::Black, $X, $Y, $W, $H)
    $font = New-Object System.Drawing.Font('Arial', 14)
    $g.DrawString($Label, $font, [System.Drawing.Brushes]::White, [single]($X + 10), [single]($Y + 8))
    $g.Dispose()
    $bmp.Save($Dst, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
} finally {
    $img.Dispose()
}
$rawHash = (Get-FileHash -Algorithm SHA256 $Src).Hash.ToLower()
Remove-Item $Src -Force
$newHash = (Get-FileHash -Algorithm SHA256 $Dst).Hash.ToLower()
Write-Output ('REDACTED dst=' + $Dst + ' rect=' + $X + ',' + $Y + ',' + $W + ',' + $H)
Write-Output ('RAW sha256=' + $rawHash + ' (original DELETED, raw-exists=' + (Test-Path $Src) + ')')
Write-Output ('NEW sha256=' + $newHash)
