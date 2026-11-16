@echo off
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell input swipe 800 620 800 180 400
ping -n 3 127.0.0.1 >nul
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell screencap -p /sdcard/m22b-e.png
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 pull /sdcard/m22b-e.png C:\Users\hello\m22b-e.png
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell uiautomator dump /sdcard/ui10.xml
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 pull /sdcard/ui10.xml C:\Users\hello\m22b-ui10.xml
echo SCROLL-DONE
