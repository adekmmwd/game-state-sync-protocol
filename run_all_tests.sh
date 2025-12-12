#!/bin/bash

set -e


TEST_MODE=$1
if [ -z "$TEST_MODE" ]; then
    echo "Usage: sudo ./run_tests.sh [baseline|loss2|loss5|delay100]"
    exit 1
fi


INTERFACE="lo"         
RUN_DURATION=130      
CLIENTS=4
OUT_DIR="results/${TEST_MODE}/run1"

echo "=== Starting Test: ${TEST_MODE} ==="
echo "[INFO] Cleaning old results in ${OUT_DIR}..."
rm -rf "${OUT_DIR}"
mkdir -p "${OUT_DIR}"

RESULTS_DIR="results/$TEST_MODE/run$i"
mkdir -p "$RESULTS_DIR"
echo "[INFO] Starting Packet Capture..."
tshark -i lo -f "udp port 8888" -w "$RESULTS_DIR/traffic.pcap" > /dev/null 2>&1 &
TSHARK_PID=$!

echo "[INFO] Setting up network conditions on ${INTERFACE}..."
tc qdisc del dev ${INTERFACE} root 2>/dev/null || true

case ${TEST_MODE} in
    "baseline")
        echo "   -> Network: No impairment (Baseline)"
        ;;
    "loss2")
        echo "   -> Network: 2% Loss"
        tc qdisc add dev ${INTERFACE} root netem loss 2%
        ;;
    "loss5")
        echo "   -> Network: 5% Loss"
        tc qdisc add dev ${INTERFACE} root netem loss 5%
        ;;
    "delay100")
        echo "   -> Network: 100ms Delay (+/- 10ms jitter)"
        tc qdisc add dev ${INTERFACE} root netem delay 100ms 10ms
        ;;
    *)
        echo "   -> [Error] Unknown mode: ${TEST_MODE}"
        exit 1
        ;;
esac


if command -v tshark &> /dev/null; then
    echo "[INFO] Starting packet capture..."
    tshark -i ${INTERFACE} -f "udp port 8888" -w "${OUT_DIR}/capture.pcap" > /dev/null 2>&1 &
    CAPTURE_PID=$!
else
    echo "[WARN] tshark not found. Skipping pcap."
fi

echo "[INFO] Launching Server..."

python3 -u server.py > "${OUT_DIR}/server_log.txt" 2>&1 &
SERVER_PID=$!
sleep 2  


for i in $(seq 1 ${CLIENTS}); do
    echo "[INFO] Launching Client ${i}..."
    python3 -u client.py > "${OUT_DIR}/client${i}_log.txt" 2>&1 &
    CLIENT_PIDS+=($!)
    sleep 0.5 
done

echo "[INFO] Running test for ${RUN_DURATION} seconds..."
sleep ${RUN_DURATION}


echo "[INFO] Stopping processes..."
kill ${SERVER_PID} 2>/dev/null || true
kill ${CLIENT_PIDS[@]} 2>/dev/null || true
if [ ! -z "$CAPTURE_PID" ]; then kill $CAPTURE_PID 2>/dev/null || true; fi
sudo chown -R $USER:$USER "$RESULTS_DIR"

echo "[INFO] Resetting network rules..."
tc qdisc del dev ${INTERFACE} root 2>/dev/null || true


echo "==========================================================="
echo "[INFO] Collecting metrics from ${OUT_DIR}..."
python3 collect_metrics.py "${OUT_DIR}" "${TEST_MODE}"

echo "[INFO] Generating plots..."
python3 plot_metrics.py "${OUT_DIR}"

sudo kill $TSHARK_PID

echo "=== Test Complete ==="
echo "Logs and Plots saved to: ${OUT_DIR}"