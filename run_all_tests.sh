#!/bin/bash
# ============================================================
# run_all_tests.sh — Project 2: Multiplayer Game State Synchronization
# Usage: ./run_all_tests.sh [scenario_name]
# Scenarios: baseline, loss_2_lan, loss_5_wan, delay_100ms, all
# ============================================================

set -e

# ---------------------- CONFIGURATION ----------------------
INTERFACE=${INTERFACE:-lo}
NUM_RUNS=1
RUN_DURATION=130                 # 60s is usually enough for steady state
SERVER_PORT=8888                # Matched your python code
RESULTS_DIR="results"

# ---------------------- SCENARIOS ----------------------
declare -A SCENARIOS
SCENARIOS["baseline"]="None"
SCENARIOS["loss_2_lan"]="loss 2%"
SCENARIOS["loss_5_wan"]="loss 5%"
SCENARIOS["delay_100ms"]="delay 100ms"

# ---------------------- SELECTION MENU ----------------------
TARGET_SCENARIO="$1"

if [ -z "$TARGET_SCENARIO" ]; then
    echo "Please select a test scenario to run:"
    options=("baseline" "loss_2_lan" "loss_5_wan" "delay_100ms" "all")
    select opt in "${options[@]}"; do
        if [[ " ${options[@]} " =~ " ${opt} " ]]; then
            TARGET_SCENARIO=$opt
            break
        else
            echo "Invalid option."
        fi
    done
fi

# ---------------------- HELPER FUNCTIONS ----------------------
cleanup_netem() {
    sudo tc qdisc del dev ${INTERFACE} root 2>/dev/null || true
}

apply_netem() {
    local config="$1"
    if [ "$config" != "None" ]; then
        echo "[NETEM] Applying: $config"
        sudo tc qdisc add dev ${INTERFACE} root netem ${config}
    fi
}

run_scenario() {
    local name=$1
    local config=$2
    
    echo "=========================================================="
    echo "RUNNING SCENARIO: ${name} (${config})"
    echo "=========================================================="
    
    mkdir -p "${RESULTS_DIR}/${name}"

    for run in $(seq 1 ${NUM_RUNS}); do
        RUN_DIR="${RESULTS_DIR}/${name}/run${run}"
        mkdir -p "${RUN_DIR}"
        
        echo "   -> Run ${run}/${NUM_RUNS}..."

        # 1. Setup Network
        cleanup_netem
        apply_netem "$config"

        # 2. Capture (First 2 runs only)
        if [ ${run} -le 2 ]; then
            sudo tcpdump -i ${INTERFACE} udp port ${SERVER_PORT} -w "${RUN_DIR}/capture.pcap" > /dev/null 2>&1 &
            TCP_PID=$!
        fi

        # 3. Start Server
        python3 server.py > "${RUN_DIR}/server_log.txt" 2>&1 &
        SERVER_PID=$!
        sleep 2

        # 4. Start Clients
        for i in {1..4}; do
            python3 client.py > "${RUN_DIR}/client${i}_log.txt" 2>&1 &
            sleep 0.5
        done

        # 5. Wait
        sleep ${RUN_DURATION}

        # 6. Kill
        kill $SERVER_PID 2>/dev/null || true
        pkill -f "client.py" 2>/dev/null || true
        if [ ! -z "$TCP_PID" ]; then sudo kill $TCP_PID 2>/dev/null || true; fi
        wait 2>/dev/null || true

        # 7. Metrics
        python3 collect_metrics.py "${RUN_DIR}/server_log.txt" "${RUN_DIR}"/client*_log.txt
        # Move the generated csv to the run folder
        mv metrics.csv "${RUN_DIR}/metrics.csv" 2>/dev/null || true
    done
    cleanup_netem
}

# ---------------------- EXECUTION ----------------------
if [ "$TARGET_SCENARIO" == "all" ]; then
    for key in "${!SCENARIOS[@]}"; do
        run_scenario "$key" "${SCENARIOS[$key]}"
    done
else
    if [ -z "${SCENARIOS[$TARGET_SCENARIO]}" ]; then
        echo "Error: Unknown scenario '$TARGET_SCENARIO'"
        exit 1
    fi
    run_scenario "$TARGET_SCENARIO" "${SCENARIOS[$TARGET_SCENARIO]}"
fi

echo ""
echo "[INFO] Processing plots..."
python3 summarize_and_plot.py "${RESULTS_DIR}"
echo "[DONE] Results saved in ${RESULTS_DIR}/"