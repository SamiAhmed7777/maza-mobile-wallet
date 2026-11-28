#!/bin/bash
# watch.sh <prefix> <first-k> <last-k> <target-regex>
# Runs uniform read-only capture rounds (prefix_NN.txt -> prefix_NN.out) until a
# UI dump in a round contains <target-regex>, or the last round number is done.
# Writes one timing line per round to <prefix>_times.txt. Never changes device state.
D=/root/.hermes/cache/scratch/m8b2a-rn/m32/win2
R=/root/maza-mobile-wallet/android/evidence/m8b2a/rn/scripts/round.py
cd "$D" || exit 9
for k in $(seq -f "%02g" "$2" "$3"); do
  f="$1_$k"
  printf '%s\n' "echo $f watch" 'shell cat /proc/uptime' \
    'shell logcat -d | grep -c -e hcallOnAppNotificationReceivedRpc' \
    'shell logcat -d | grep -e HCALL | tail -2' \
    'shell logcat -d | grep -e "MAZA " | tail -3' \
    'shell dumpsys notification | grep -e com.mazawallet -e incoming_maza | head -8' \
    'shell ps | grep -e mazawallet | head -2' \
    'shell dumpsys activity activities | grep -e mResumedActivity' \
    'shell uiautomator dump /sdcard/ui.xml' 'sleep 1' \
    'shell cat /sdcard/ui.xml' 'shell rm -f /sdcard/ui.xml' > "$f.txt"
  printf '%s start=%s ' "$f" "$(date +%H:%M:%S)" >> "$1_times.txt"
  python3 "$R" "$f.txt" > "$f.sum" 2>&1
  printf 'rc=%s end=%s\n' "$?" "$(date +%H:%M:%S)" >> "$1_times.txt"
  if tr -d '\r' < "$f.out" | grep -q -e "$4"; then
    echo "TARGET-SEEN in $f at $(date +%H:%M:%S)" >> "$1_times.txt"
    break
  fi
done
cat "$1_times.txt"
