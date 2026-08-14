#!/bin/bash
# ============================================================
# İşçi Takip Sistemi - Linux / Raspberry Pi Başlatma Betiği
# ============================================================

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export OMP_NUM_THREADS=4
export OPENBLAS_NUM_THREADS=4
export MKL_NUM_THREADS=4
export VECLIB_MAXIMUM_THREADS=4
export NUMEXPR_NUM_THREADS=4

# CPU Performans Modu (Raspberry Pi 5 - Maksimum 2.4 GHz Hız)
if [ -f /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor ]; then
    echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor >/dev/null 2>&1 || true
fi

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "  İşçi Takip Sistemi - Raspberry Pi 5 Maksimum Performans"
echo "  Tarayıcıda açın: http://localhost:5000"
echo "============================================================"

# Sanal ortam kontrolü
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d "../venv" ]; then
    source ../venv/bin/activate
fi

python3 web/app.py

