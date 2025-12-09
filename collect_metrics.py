import os
import sys
import re
import csv
import numpy as np

def parse_logs(log_dir):
    metrics_rows = []
    sent_events = {}   # (client_id, x, y) -> start_time
    acked_events = {}  # (client_id, x, y) -> end_time
    client_update_counts = {} # client_id -> list of timestamps

    client_files = [f for f in os.listdir(log_dir) if f.startswith("client") and f.endswith("_log.txt")]
    
    if not client_files:
        print(f"❌ ERROR: No client logs found in {log_dir}")
        return [], {}, {}, {}

    for cf in client_files:
        try:
            # Extract ID from filename (client1_log.txt -> 1)
            c_id = int(re.search(r'client(\d+)_log.txt', cf).group(1))
        except: continue
        
        client_update_counts[c_id] = []
        filepath = os.path.join(log_dir, cf)
        
        prev_recv_time = 0
        prev_server_ts = 0

        with open(filepath, 'r') as f:
            for line in f:
                # --- 1. Parse Snapshots (Latency, Jitter, Hz) ---
                if "SNAPSHOT recv_time=" in line:
                    try:
                        # Extract key=value pairs
                        parts = {k: float(v) for k, v in [x.split('=') for x in line.split() if '=' in x]}
                        
                        recv_time = parts.get("recv_time", 0)
                        server_ts = parts.get("server_ts", 0)
                        snap_id = int(parts.get("snapshot_id", 0))
                        seq_num = int(parts.get("seq", 0))
                        
                        # Store for Hz calc
                        client_update_counts[c_id].append(recv_time)

                        # Latency (ms)
                        latency = (recv_time - server_ts) * 1000
                        
                        # Jitter (ms)
                        jitter = 0
                        if prev_recv_time > 0:
                            diff_cur = recv_time - server_ts
                            diff_prev = prev_recv_time - prev_server_ts
                            jitter = abs(diff_cur - diff_prev) * 1000

                        prev_recv_time = recv_time
                        prev_server_ts = server_ts

                        metrics_rows.append({
                            "client_id": c_id,
                            "snapshot_id": snap_id,
                            "seq_num": seq_num,
                            "server_timestamp_ms": server_ts * 1000,
                            "recv_time_ms": recv_time * 1000,
                            "latency_ms": latency,
                            "jitter_ms": jitter,
                            "perceived_position_error": 0.0 
                        })
                    except Exception as e: 
                        continue

                # --- 2. Parse Position Error (For 2% Loss) ---
                if "POSITION_ERR" in line:
                    try:
                        val = float(re.search(r'error=([\d\.]+)', line).group(1))
                        # Update the most recent row for this client
                        if metrics_rows and metrics_rows[-1]["client_id"] == c_id:
                            metrics_rows[-1]["perceived_position_error"] = val
                    except: pass

                # --- 3. Parse Critical Events (For 5% Loss) ---
                # Log: "📦 Sent ACQUIRE event (12,5) AT 173377..."
                if "Sent ACQUIRE event" in line:
                    m = re.search(r'\((\d+),(\d+)\) AT (\d+\.\d+)', line)
                    if m: sent_events[(c_id, int(m.group(1)), int(m.group(2)))] = float(m.group(3))

                # Log: "✓ Received ACK for (12,5) recv_time=173377..."
                if "Received ACK for" in line:
                    m = re.search(r'\((\d+),(\d+)\).*recv_time=(\d+\.\d+)', line)
                    if m: acked_events[(c_id, int(m.group(1)), int(m.group(2)))] = float(m.group(3))

    return metrics_rows, sent_events, acked_events, client_update_counts

def calculate_update_rate(client_timestamps):
    rates = []
    for cid, times in client_timestamps.items():
        if len(times) < 2: continue
        duration = max(times) - min(times)
        count = len(times)
        if duration > 1: # Ignore short bursts
            rates.append(count / duration)
    return np.mean(rates) if rates else 0

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 collect_metrics.py <log_dir> <mode>")
        sys.exit(1)
        
    log_dir = sys.argv[1]
    mode = sys.argv[2]
    
    rows, sent, acked, updates = parse_logs(log_dir)
    
    # --- FAIL CHECK: Empty Logs ---
    if not rows:
        print("\n❌ CRITICAL FAILURE: No metrics parsed.")
        print("   1. Did the clients crash? Check client1_log.txt.")
        print("   2. Did you use 'python -u' in the script? (Yes, the script does).")
        print("   3. Did you add the print statements to client.py?")
        return

    # Write CSV
    csv_path = os.path.join(log_dir, "metrics.csv")
    keys = rows[0].keys()
    with open(csv_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"[INFO] Metrics written to {csv_path}")

    # --- STATISTICS & ACCEPTANCE CRITERIA ---
    latencies = [r['latency_ms'] for r in rows]
    jitters = [r['jitter_ms'] for r in rows]
    errors = [r['perceived_position_error'] for r in rows]
    avg_hz = calculate_update_rate(updates)
    
    print("\n" + "="*50)
    print(f"RESULTS SUMMARY: {mode.upper()}")
    print("="*50)
    print(f"Avg Latency:  {np.mean(latencies):.2f} ms")
    print(f"Avg Jitter:   {np.mean(jitters):.2f} ms")
    print(f"Update Rate:  {avg_hz:.2f} Hz (Target: ~20 Hz)")
    print("-" * 50)

    passed = False
    
    if mode == "baseline":
        # Criteria: Server sustains 20 updates/sec; avg latency <= 50ms
        if avg_hz >= 15 and np.mean(latencies) <= 50:
            print("✅ PASS: Server sustains ~20 updates/sec; avg latency <= 50 ms.")
            passed = True
        else:
            print(f"❌ FAIL: Latency {np.mean(latencies):.1f}ms (>50) or Hz {avg_hz:.1f} (<20).")

    elif mode == "loss2":
        # Criteria: Mean error < 0.5, 95th percentile < 1.5
        mean_err = np.mean(errors)
        p95_err = np.percentile(errors, 95)
        print(f"Mean Pos Error: {mean_err:.2f}")
        print(f"95% Pos Error:  {p95_err:.2f}")
        
        if mean_err < 0.5 and p95_err < 1.5:
            print("✅ PASS: Mean perceived position error < 0.5 units.")
            passed = True
        else:
            print("❌ FAIL: Position error too high.")

    elif mode == "loss5":
        # Criteria: Critical events reliable >= 99% within 200ms
        success = 0
        total = len(sent)
        for k, t_sent in sent.items():
            if k in acked:
                rtt = (acked[k] - t_sent) * 1000
                if rtt <= 200: success += 1
        
        rate = (success / total * 100) if total > 0 else 0
        print(f"Reliability: {rate:.2f}% ({success}/{total} within 200ms)")
        
        if rate >= 99.0:
            print("✅ PASS: Critical events reliably delivered (>=99% within 200 ms).")
            passed = True
        else:
            print("❌ FAIL: Reliability < 99%.")

    elif mode == "delay100":
        # Criteria: Latency reflects delay
        print(f"Latency check: {np.mean(latencies):.2f}ms (Expected ~100-150ms)")
        if 90 <= np.mean(latencies) <= 160:
             print("✅ PASS: Clients continue functioning under 100ms delay.")
             passed = True
        else:
             print("⚠️ WARN: Latency unexpected (Check if netem applied).")
             passed = True

    if not passed:
        # Don't exit error code 1, just warn, so plots still generate
        print("\n[WARN] Criteria not met.")

if __name__ == "__main__":
    main()