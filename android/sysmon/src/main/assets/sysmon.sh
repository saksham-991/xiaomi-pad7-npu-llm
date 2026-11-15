#!/system/bin/sh
# Pad7 SysMon root sampler -> /data/local/tmp/sysmon.json every second
OUT=/data/local/tmp/sysmon.json
TMP=/data/local/tmp/sysmon.$$
PREV_CPU=/data/local/tmp/sysmon.prevcpu
PREV_NET=/data/local/tmp/sysmon.prevnet
INTERVAL_FILE=/data/local/tmp/sysmon.interval

iface_bytes() {
  awk -F'[: ]+' '/^ *(wlan0|eth0|rmnet)/ {print $2, $10}' /proc/net/dev | awk '{rx+=$1; tx+=$2} END{print rx+0, tx+0}'
}

cpu_line() {
  awk '/^cpu / {print $2+$3+$4+$5+$6+$7+$8, $5}' /proc/stat
}

while true; do
  IV=$(cat "$INTERVAL_FILE" 2>/dev/null)
  [ -z "$IV" ] && IV=2

  CUR_CPU=$(cpu_line)
  if [ -f "$PREV_CPU" ]; then
    PREV=$(cat "$PREV_CPU")
    CPU_PCT=$(echo "$PREV $CUR_CPU" | awk '{dt=$3-$1; di=$4-$2; if(dt<=0){print 0}else{printf "%.1f", 100*(dt-di)/dt}}')
  else
    CPU_PCT=0
  fi
  echo "$CUR_CPU" > "$PREV_CPU"

  CORES=$(awk '/^cpu[0-9]+ / {tot=$2+$3+$4+$5+$6+$7+$8; idle=$5; printf "%s%d", (n++?",":""), (tot>0?100*(tot-idle)/tot:0)}' /proc/stat)

  MEM=$(awk '
    /MemTotal:/{t=$2}/MemAvailable:/{a=$2}/Cached:/{c=$2}
    /SwapTotal:/{st=$2}/SwapFree:/{sf=$2}
    /Dirty:/{d=$2}
    END{printf "%d %d %d %d %d %d", t, a, c, st, sf, d}' /proc/meminfo)

  ZRAM=$(awk '{printf "%d %d %d", $1, $2, $3}' /sys/block/zram0/mm_stat 2>/dev/null)
  [ -z "$ZRAM" ] && ZRAM="0 0 0"

  DISK=$(df -k /data 2>/dev/null | awk 'NR==2{printf "%d %d %d", $2, $3, $4}')

  NET=$(iface_bytes)
  if [ -f "$PREV_NET" ]; then
    PN=$(cat "$PREV_NET")
    RATES=$(echo "$PN $NET" | awk -v iv="$IV" '{printf "%.0f %.0f", ($3-$1)/iv, ($4-$2)/iv}')
  else
    RATES="0 0"
  fi
  echo "$NET" > "$PREV_NET"

  GPU=$(cat /sys/class/kgsl/kgsl-3d0/gpubusy 2>/dev/null | awk '{if($2>0) printf "%.0f", 100*$1/$2; else print 0}')
  [ -z "$GPU" ] && GPU=-1
  GPUFREQ=$(cat /sys/class/kgsl/kgsl-3d0/devfreq/cur_freq 2>/dev/null)
  [ -z "$GPUFREQ" ] && GPUFREQ=0

  NPUSTATE=$(for r in /sys/class/remoteproc/remoteproc*; do
      n=$(cat "$r/name" 2>/dev/null); [ -z "$n" ] && continue
      s=$(cat "$r/state" 2>/dev/null)
      echo "$n:$s"
    done | tr '\n' '|')

  TICK=$((${TICK:-0}+1)); TICK=$((TICK%5))
  if [ "$TICK" = "1" ]; then
    NPUFDS=$(ls -l /proc/[0-9]*/fd 2>/dev/null | grep -c adsprpc)
    echo "$NPUFDS" > /data/local/tmp/sysmon.npufds
  fi
  NPUFDS=$(cat /data/local/tmp/sysmon.npufds 2>/dev/null)
  [ -z "$NPUFDS" ] && NPUFDS=0

  LLAMA=$(pgrep -x llama-server >/dev/null 2>&1 && echo 1 || echo 0)
  LLMCPU=$(ps -A -o NAME,%CPU 2>/dev/null | awk '$1=="llama-server"{print $2}' | head -1)
  [ -z "$LLMCPU" ] && LLMCPU=0

  TOP=$(ps -A -o PID,NAME,RSS,%CPU 2>/dev/null | awk 'NR>1 {c=$4+0; if(c>0 || $3+0>1024) printf "%.2f %s:%s:%s:%s\n", c, $1, $2, $3, $4}' | sort -rn | head -10 | awk '{printf "%s\"%s\"", (n++?",":""), $2}')

  cat > "$TMP" <<EOF
{"ts":$(date +%s),"cpu":$CPU_PCT,"cores":[$CORES],"mem":[$(echo $MEM | tr " " ",")],"zram":[$(echo $ZRAM | tr " " ",")],"disk":[$(echo $DISK | tr " " ",")],"net":[$(echo $RATES | tr " " ",")],"gpu":$GPU,"gpufreq":$GPUFREQ,"npu":"$NPUSTATE","llama":$LLAMA,"llmcpu":$LLMCPU,"npufds":$NPUFDS,"procs":[$TOP]}
EOF
  mv "$TMP" "$OUT"
  chmod 644 "$OUT"
  sleep "$IV"
done
