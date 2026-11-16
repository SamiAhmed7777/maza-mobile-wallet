@echo off
rem M22b round-2: every adb call is transport-qualified (-s emulator-5554).
mkdir C:\Users\hello\m22b-repull 2>nul
echo === devices ===
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" devices
echo === repull PNGs with -s ===
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 pull /sdcard/m22b-a.png C:\Users\hello\m22b-repull\m22b-a.png
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 pull /sdcard/m22b-b.png C:\Users\hello\m22b-repull\m22b-b.png
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 pull /sdcard/m22b-c.png C:\Users\hello\m22b-repull\m22b-c.png
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 pull /sdcard/m22b-d.png C:\Users\hello\m22b-repull\m22b-d.png
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 pull /sdcard/m22b-e.png C:\Users\hello\m22b-repull\m22b-e.png
echo === installed apk identity ===
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell pm path com.mazawallet
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell md5sum /data/app/com.mazawallet-J-0lYxyTQ-rVRyOrgMHV6g==/base.apk
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell dumpsys package com.mazawallet | findstr -i lastUpdateTime
echo === sha256 of repulled files ===
powershell -Command "Get-FileHash -Algorithm SHA256 C:\Users\hello\m22b-repull\*.png | Format-List Hash,Path"
echo ROUND4-DONE
