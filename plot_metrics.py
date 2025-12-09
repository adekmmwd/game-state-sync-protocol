import pandas as pd
import matplotlib.pyplot as plt
import sys
import os

def plot(log_dir):
    csv_path = os.path.join(log_dir, "metrics.csv")
    if not os.path.exists(csv_path):
        print("[WARN] metrics.csv not found, skipping plots.")
        return

    df = pd.read_csv(csv_path)
    if df.empty:
        print("[WARN] metrics.csv is empty, skipping plots.")
        return

    # 1. Latency Over Time
    plt.figure(figsize=(10, 4))
    for cid in df['client_id'].unique():
        sub = df[df['client_id'] == cid]
        if sub.empty: continue
        t = (sub['recv_time_ms'] - sub['recv_time_ms'].min()) / 1000
        plt.plot(t, sub['latency_ms'], label=f'Client {cid}', alpha=0.7)
    
    plt.title("Latency vs Time")
    plt.xlabel("Time (s)")
    plt.ylabel("Latency (ms)")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(log_dir, "plot_latency.png"))
    plt.close()

    # 2. Jitter Distribution
    plt.figure(figsize=(10, 4))
    plt.hist(df['jitter_ms'], bins=30, alpha=0.7, color='orange', edgecolor='black')
    plt.title("Jitter Distribution")
    plt.xlabel("Jitter (ms)")
    plt.ylabel("Frequency")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(log_dir, "plot_jitter.png"))
    plt.close()

    print(f"[INFO] Plots saved to {log_dir}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 plot_metrics.py <log_dir>")
        sys.exit(1)
    plot(sys.argv[1])