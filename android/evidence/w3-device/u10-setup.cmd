@echo off
set ADB="C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
echo === STEP1 install-existing for user 10 ===
%ADB% -s emulator-5554 shell pm install-existing --user 10 com.mazawallet
echo === STEP2 list user 10 ===
%ADB% -s emulator-5554 shell pm list packages --user 10 com.mazawallet
echo === STEP3 switch-user 10 ===
%ADB% -s emulator-5554 shell am switch-user 10
ping -n 14 127.0.0.1 >nul
echo === STEP4 users ===
%ADB% -s emulator-5554 shell am get-current-user
echo === STEP5 launch ===
%ADB% -s emulator-5554 shell am start --user 10 -n com.mazawallet/.MainActivity
echo U10-SETUP-DONE
