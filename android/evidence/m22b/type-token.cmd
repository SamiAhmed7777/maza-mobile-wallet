@echo off
set /p TOK=
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell input tap 800 455
ping -n 2 127.0.0.1 >nul
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell input text "%TOK%"
ping -n 2 127.0.0.1 >nul
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 shell uiautomator dump /sdcard/ui2.xml
"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554 pull /sdcard/ui2.xml C:\Users\hello\m22b-ui2.xml
echo TYPED-DONE
