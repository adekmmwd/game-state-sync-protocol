import pandas as pd
import matplotlib.pyplot as plt
import sys
import os

def plot(log_dir):
    csv_path = os.path.join(log_dir, "metrics.csv")
    if not os.path.exists(csv_path):
        print(f"[Plotter] {csv_path} not found. Skipping.")
        return

    try:
        df = pd.read_csv(csv_path)
    except pd.errors.EmptyDataError:
        print("[Plotter] CSV is empty.")
        return

    if df.empty:
        print("[Plotter] DataFrame is empty.")
        return

    # Normalize time to start at 0 seconds
    start_time = df['recv_time_ms'].min()
    df['time_sec'] = (df['recv_time_ms'] - start_time) / 1000.0

    # 1. LATENCY PLOT
    plt.figure(figsize=(10, 5))
    for cid in df['client_id'].unique():
        subset = df[df['client_id'] == cid]
        plt.plot(subset['time_sec'], subset['latency_ms'], label=f'Client {cid}', alpha=0.7)
    
    plt.title("Latency vs Time")
    plt.xlabel("Time (s)")
    plt.ylabel("Latency (ms)")
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.savefig(os.path.join(log_dir, "plot_latency.png"))
    plt.close()


    # 2. JITTER PLOT (Histogram)
    plt.figure(figsize=(10, 5))
    plt.hist(df['jitter_ms'], bins=50, color='orange', edgecolor='black', alpha=0.7)
    plt.title("Jitter Distribution")
    plt.xlabel("Jitter (ms)")
    plt.ylabel("Frequency")
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.savefig(os.path.join(log_dir, "plot_jitter.png"))
    plt.close()
    print(f"[Plotter] Saved plot_jitter.png")

    # 3. POSITION ERROR PLOT (Requirement for 2% Loss)
    if 'perceived_position_error' in df.columns and df['perceived_position_error'].sum() > 0:
        plt.figure(figsize=(10, 5))
        for cid in df['client_id'].unique():
            subset = df[df['client_id'] == cid]
            plt.plot(subset['time_sec'], subset['perceived_position_error'], label=f'Client {cid}', marker='.', linestyle='none', alpha=0.5)
        
        # Add a line for the Mean Error
        mean_err = df['perceived_position_error'].mean()
        plt.axhline(y=mean_err, color='r', linestyle='-', label=f'Mean ({mean_err:.2f})')
        
        plt.title("Perceived Position Error vs Time")
        plt.xlabel("Time (s)")
        plt.ylabel("Error (Euclidean Distance)")
        plt.legend()
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.savefig(os.path.join(log_dir, "plot_perceived_position_error.png"))
        plt.close()
        print(f"[Plotter] Saved plot_perceived_position_error.png")
    else:
        print("[Plotter] No Position Error data found (or error is 0). Skipping error plot.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 plot_metrics.py <log_dir>")
        sys.exit(1)
    
    plot(sys.argv[1])