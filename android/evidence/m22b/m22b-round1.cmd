@echo off
echo === T0 BALANCE screencap ===
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell screencap -p /sdcard/m22b-a.png
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 pull /sdcard/m22b-a.png C:\Users\hello\m22b-a.png
echo === TAP SEND ===
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell input tap 800 858
ping -n 4 127.0.0.1 >nul
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell screencap -p /sdcard/m22b-b.png
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 pull /sdcard/m22b-b.png C:\Users\hello\m22b-b.png
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell uiautomator dump /sdcard/ui4.xml
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 pull /sdcard/ui4.xml C:\Users\hello\m22b-ui4.xml
echo === TAP BALANCE ===
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell input tap 160 858
ping -n 4 127.0.0.1 >nul
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell screencap -p /sdcard/m22b-c.png
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 pull /sdcard/m22b-c.png C:\Users\hello\m22b-c.png
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell uiautomator dump /sdcard/ui5.xml
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 pull /sdcard/ui5.xml C:\Users\hello\m22b-ui5.xml
echo ROUND1-DONE
