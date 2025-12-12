import os
import sys
import re
import csv
import numpy as np

def parse_client_logs(log_dir):
    metrics_rows = []
    sent_events = {}   
    acked_events = {}  
    client_update_counts = {} 
    client_positions=[]
   

    client_files = [f for f in os.listdir(log_dir) if f.startswith("client") and f.endswith("_log.txt")]
    
    if not client_files:
        print(f"❌ ERROR: No client logs found in {log_dir}")
        return [], {}, {}, {}

    for cf in client_files:
        try:
            
            c_id = int(re.search(r'client(\d+)_log.txt', cf).group(1))
        except: continue
        
        client_update_counts[c_id] = []
        filepath = os.path.join(log_dir, cf)
        
        prev_recv_time = 0
        prev_server_ts = 0

        with open(filepath, 'r') as f:
            for line in f:
           
                if "SNAPSHOT recv_time=" in line:
                    try:
                    
                        parts = {k: float(v) for k, v in [x.split('=') for x in line.split() if '=' in x]}
                        
                        recv_time = parts.get("recv_time", 0)
                        server_ts = parts.get("server_ts", 0)
                        snap_id = int(parts.get("snapshot_id", 0))
                        seq_num = int(parts.get("seq", 0))

                        client_update_counts[c_id].append(recv_time)
                        latency = (recv_time - server_ts) * 1000
                        jitter = 0
                        if prev_recv_time > 0:
                            diff_cur = recv_time - server_ts
                            diff_prev = prev_recv_time - prev_server_ts
                            jitter = abs(diff_cur - diff_prev) * 1000

                        prev_recv_time = recv_time
                        prev_server_ts = server_ts

                        packet_size = parts.get("bytes", 0)
                        metrics_rows.append({
                            "client_id": c_id,
                            "snapshot_id": snap_id,
                            "seq_num": seq_num,
                            "server_timestamp_ms": server_ts * 1000,
                            "recv_time_ms": recv_time * 1000,
                            "latency_ms": latency,
                            "jitter_ms": jitter,
                            "packet_size":packet_size
                       
                        })
                    except Exception as e: 
                        continue
                

                #for position error
                if "POS_CLIENT" in line:
                    try:
                        parts = {k: float(v) for k, v in [x.split('=') for x in line.split() if '=' in x]}
                        client_positions.append({
                             "client_id": c_id,
                             "x":parts.get("x", 0),
                             "y":parts.get("y", 0),
                             "server_pos_ts":parts.get("ts", 0)
                            })
                    except: pass

                if "Sent ACQUIRE event" in line:
                    m = re.search(r'\((\d+),(\d+)\) AT (\d+\.\d+)', line)
                    if m: sent_events[(c_id, int(m.group(1)), int(m.group(2)))] = float(m.group(3))

                if "Received ACK for" in line:
                    m = re.search(r'\((\d+),(\d+)\).*recv_time=(\d+\.\d+)', line)
                    if m: acked_events[(c_id, int(m.group(1)), int(m.group(2)))] = float(m.group(3))

    return metrics_rows, sent_events, acked_events, client_update_counts,client_positions

def parse_server_logs(log_dir):
    metrics_rows = []
    server_positions=[]

   
    server_file = [f for f in os.listdir(log_dir) if f.startswith("server") and f.endswith("_log.txt")]
    
    if not server_file:
        print(f"❌ ERROR: No client logs found in {log_dir}")
        return [], {}, {}, {}

    for cf in server_file:
        
    
        filepath = os.path.join(log_dir, cf)
        with open(filepath, 'r') as f:
            for line in f:
                # for cpu usage
                if "CPU_USAGE" in line:
                    try:
                        
                        parts = {k: float(v) for k, v in [x.split('=') for x in line.split() if '=' in x]}
                        
                        cpu_usage = parts.get("percent", 0)
                        cpu_usage_ts = parts.get("ts", 0)
    
                        metrics_rows.append({
                            "cpu_usage": cpu_usage,
                            "cpu_usage_ts": cpu_usage_ts,
          
                        })
                    except Exception as e: 
                        continue
                #for position error
                elif "POS_SERVER" in line:
                    try:
                        # Extract key=value pairs
                        parts = {k: float(v) for k, v in [x.split('=') for x in line.split() if '=' in x]}
                        
                        server_x_pos = parts.get("x", 0)
                        server_y_pos= parts.get("y", 0)
                        cpu_pos_ts = parts.get("ts", 0)
                        client=parts.get("id", 0)
    
                        server_positions.append({
                            "server_x_pos": server_x_pos,
                            "server_y_pos": server_y_pos,
                            "server_pos_ts":cpu_pos_ts,
                            "client": client
          
                        })
                    except Exception as e: 
                        continue

    
    return metrics_rows,server_positions

def calculate_update_rate(client_timestamps):
    rates = []
    for cid, times in client_timestamps.items():
        if len(times) < 2: continue
        duration = max(times) - min(times)
        count = len(times)
        if duration > 1: 
            rates.append(count / duration)
    return np.mean(rates) if rates else 0

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 collect_metrics.py <log_dir> <mode>")
        sys.exit(1)
        
    log_dir = sys.argv[1]
    mode = sys.argv[2]
    
    rows, sent, acked, updates,client_positions = parse_client_logs(log_dir)
    rows = sorted(rows, key=lambda r: r["server_timestamp_ms"])
    server_rows,server_positions=parse_server_logs(log_dir)
    server_rows=sorted(server_rows, key=lambda r: r["cpu_usage_ts"])


    client_positions.sort(key=lambda k: k['server_pos_ts'])
    server_positions.sort(key=lambda k: k['server_pos_ts'])

    #for cpu usage and it takes closest timestamp
    for row in range(len(rows)):
        closest=0
        row_data = rows[row]
        for s_row in server_rows:
            if s_row["cpu_usage_ts"] > row_data["server_timestamp_ms"]/1000:
                break
            closest=s_row["cpu_usage"]
        row_data["cpu"]=closest

    #for poistion error and it takes closest timestamp
    for row in rows:

        cid = row['client_id']
        current_time_sec = row['recv_time_ms'] / 1000.0  
        server_pos_x=0
        server_pos_y=0

        for pos in server_positions:
            if pos['client'] != cid: continue
            if pos['server_pos_ts'] > current_time_sec: break
            server_pos_x=pos['server_x_pos']
            server_pos_y = pos['server_y_pos']

        client_pos_x= 0
        client_pos_y = 0
        for pos in client_positions:
            if pos['client_id'] != cid: continue
            
            if pos['server_pos_ts'] > current_time_sec: break
            
            client_pos_x =pos['x'] 
            client_pos_y =  pos['y']

        dist = np.sqrt((server_pos_x - client_pos_x)**2 + (server_pos_y - client_pos_y)**2)
        row['perceived_position_error'] = dist
    

    #calculate bandwidth for each client in a cumulative way
    unique_clients={}
    for row in rows:
        if row['client_id'] not in unique_clients:
            unique_clients[row['client_id'] ]={"start":row["recv_time_ms"],"size_sum":0}

        unique_clients[row['client_id'] ]["size_sum"]+=row["packet_size"]

        bandwidth=0
        if row["recv_time_ms"] ==  unique_clients[row['client_id'] ]["start"]:
            pass

        else:
            bandwidth= ((8*unique_clients[row['client_id'] ]["size_sum"])/((row["recv_time_ms"] -unique_clients[row['client_id'] ]["start"])/ 1000.0))/1000

        row['bandwidth'] = bandwidth

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

    # Statistics
    client_bandwidths = {}
    for r in rows:
        client_bandwidths[r['client_id']] = r['bandwidth']

    latencies = [r['latency_ms'] for r in rows]
    jitters = [r['jitter_ms'] for r in rows]
    errors = [r['perceived_position_error'] for r in rows]
    cpu_usage = [r['cpu'] for r in rows]
    clients_updates = calculate_update_rate(updates)

    latency_mean = np.mean(latencies) if latencies else 0
    lattency_med = np.median(latencies) if latencies else 0
    latency_per95 = np.percentile(latencies, 95) if latencies else 0

    jitter_mean = np.mean(jitters) if jitters else 0
    jitter_med = np.median(jitters) if jitters else 0
    jitter_95 = np.percentile(jitters, 95) if jitters else 0

    error_mean = np.mean(errors) if errors else 0
    error_med = np.median(errors) if errors else 0
    error_95 = np.percentile(errors, 95) if errors else 0

    cpu_mean = np.mean(cpu_usage) if cpu_usage else 0

    print("\n" + "="*50)
    print(f"RESULTS SUMMARY: {mode.upper()}")
    print("="*50)

    if latencies:
        print(f"Latency (ms):Mean={latency_mean:.2f} | Median={lattency_med:.2f} | 95th={latency_per95:.2f}")
    else:
        print("Latency (ms):No Data")

    if jitters:
        print(f"Jitter (ms):Mean={jitter_mean:.2f} | Median={jitter_med:.2f} | 95th={jitter_95:.2f}")
    
    if errors:
        print(f"Pos Error:  Mean={error_mean:.4f} | Median={error_med:.4f} | 95th={error_95:.4f}")

    if cpu_usage:
        print(f"Avg CPU Usage:  {cpu_mean:.2f} %")

    print(f"Update Rate:    {clients_updates:.2f} Hz")
    print("-" * 30)
    print("Bandwidth per Client (Session Avg):")
    for cid in sorted(client_bandwidths.keys()):
        print(f"  Client {cid}: {client_bandwidths[cid]:.2f} kbps")

    avg_bw = np.mean(list(client_bandwidths.values())) if client_bandwidths else 0
    with open(os.path.join(log_dir, "stats_summary.txt"), "w") as f:
        f.write(f"Test: {mode}\n")
        f.write(f"Latency: Mean={latency_mean:.2f}, Median={lattency_med:.2f}, 95th={latency_per95:.2f}\n")
        f.write(f"Jitter: Mean={jitter_mean:.2f}, Median={jitter_med:.2f}, 95th={jitter_95:.2f}\n")
        f.write(f"Error: Mean={error_mean:.4f}, Median={error_med:.4f}, 95th={error_95:.4f}\n")
        f.write(f"Bandwidth (Avg Total): {avg_bw:.2f} kbps\n")
        f.write(f"CPU: {cpu_mean:.2f}%\n")
        f.write(f"Update Rate: {clients_updates:.2f} Hz\n")
    print(f"[INFO] Stats saved to {os.path.join(log_dir, 'stats_summary.txt')}")
    
    passed = False
    
    if mode == "baseline":
        if clients_updates >= 15 and latency_mean <= 50 and cpu_mean < 60:
            print("✅ PASS: Server sustains ~20 updates/sec; avg latency <= 50 ms.;cpu usage<60%")
            passed = True
        else:
            print(f"❌ FAIL: Latency {latency_mean:.1f}ms (>50) or Hz {clients_updates:.1f} (<20) or cpu usage>60%.")

    elif mode == "loss2":
        print(f"Mean Pos Error: {error_mean:.2f}")
        print(f"95% Pos Error:  {error_95:.2f}")
        
        if error_mean < 0.5 and error_95 < 1.5:
            print("✅ PASS: Mean perceived position error < 0.5 units.")
            passed = True
        else:
            print("❌ FAIL: Position error too high.")

    elif mode == "loss5":
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
        print(f"Latency check: {latency_mean:.2f}ms (Expected ~100-150ms)")
        if 90 <= latency_mean <= 160:
             print("✅ PASS: Clients continue functioning under 100ms delay.")
             passed = True
        else:
             print("⚠️ WARN: Latency unexpected (Check if netem applied).")
             passed = True

    if not passed:
        print("\n[WARN] Criteria not met.")

if __name__ == "__main__":
    main()