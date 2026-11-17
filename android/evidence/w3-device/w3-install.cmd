@echo off
set ADB="C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
set LOG=C:\Users\hello\w3bench\install.log
echo === PUSH === > %LOG%
%ADB% -s emulator-5554 shell rm -f /sdcard/maza-w3.apk >> %LOG% 2>&1
%ADB% -s emulator-5554 push C:\Users\hello\maza-w3.apk /sdcard/maza-w3.apk >> %LOG% 2>&1
%ADB% -s emulator-5554 shell ls -l /sdcard/maza-w3.apk >> %LOG% 2>&1
echo === INSTALL === >> %LOG%
%ADB% -s emulator-5554 shell pm install -r /sdcard/maza-w3.apk >> %LOG% 2>&1
echo === POST-INSTALL WAIT === >> %LOG%
ping -n 30 127.0.0.1 >nul
%ADB% connect 127.0.0.1:5555 >> %LOG% 2>&1
echo === VERIFY === >> %LOG%
%ADB% -s emulator-5554 shell pm list packages com.mazawallet >> %LOG% 2>&1
%ADB% -s emulator-5554 shell pm path com.mazawallet >> %LOG% 2>&1
%ADB% -s emulator-5554 shell dumpsys package com.mazawallet > C:\Users\hello\w3bench\pkgdump.txt 2>&1
echo INSTALL-SCRIPT-DONE >> %LOG%
