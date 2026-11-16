@echo off
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell input tap 800 576
ping -n 7 127.0.0.1 >nul
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell uiautomator dump /sdcard/ui3.xml
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 pull /sdcard/ui3.xml C:\Users\hello\m22b-ui3.xml
echo CONNECTED-DONE
