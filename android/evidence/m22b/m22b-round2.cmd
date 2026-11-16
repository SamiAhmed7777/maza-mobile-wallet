@echo off
echo === S1 ===
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell uiautomator dump /sdcard/ui6.xml
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 pull /sdcard/ui6.xml C:\Users\hello\m22b-ui6.xml
echo === NAV1 BALANCE-SEND-BALANCE ===
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell input tap 800 858
ping -n 3 127.0.0.1 >nul
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell input tap 160 858
ping -n 3 127.0.0.1 >nul
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell uiautomator dump /sdcard/ui7.xml
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 pull /sdcard/ui7.xml C:\Users\hello\m22b-ui7.xml
echo === NAV2 ===
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell input tap 800 858
ping -n 3 127.0.0.1 >nul
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell input tap 160 858
ping -n 3 127.0.0.1 >nul
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell uiautomator dump /sdcard/ui8.xml
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 pull /sdcard/ui8.xml C:\Users\hello\m22b-ui8.xml
echo === WALLET TAB ===
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell input tap 1440 858
ping -n 4 127.0.0.1 >nul
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell screencap -p /sdcard/m22b-d.png
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 pull /sdcard/m22b-d.png C:\Users\hello\m22b-d.png
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell uiautomator dump /sdcard/ui9.xml
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 pull /sdcard/ui9.xml C:\Users\hello\m22b-ui9.xml
echo ROUND2-DONE
