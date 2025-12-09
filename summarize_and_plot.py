import pandas as pd
import matplotlib.pyplot as plt
import sys
import glob
import os

results_dir = sys.argv[1] if len(sys.argv) > 1 else "results"

data = []

# Walk through all run directories
for run_dir in glob.glob(f"{results_dir}/*/run*"):
    csv_path = os.path.join(run_dir, "metrics.csv")
    if not os.path.exists(csv_path):
        continue
    
    parts = run_dir.split(os.sep)
    scenario = parts[-2] # e.g., loss_5_wan
    
    try:
        df = pd.read_csv(csv_path)
        
        # 1. Snapshot Latency Stats
        snaps = df[df['metric_type'] == 'snapshot']
        lat_mean = snaps['latency_ms'].mean() if not snaps.empty else 0
        lat_95 = snaps['latency_ms'].quantile(0.95) if not snaps.empty else 0
        
        # 2. Reliability Stats
        rels = df[df['metric_type'] == 'reliability']
        rel_mean = rels['reliability_pct'].mean() if not rels.empty else 100
        retry_mean = rels['retransmits'].mean() if not rels.empty else 0

        data.append({
            'scenario': scenario,
            'latency_mean': lat_mean,
            'latency_95': lat_95,
            'reliability': rel_mean,
            'retransmits': retry_mean
        })
    except Exception as e:
        print(f"Skipping {csv_path}: {e}")

# Aggregate by scenario
df_all = pd.DataFrame(data)
if df_all.empty:
    print("No data found to plot.")
    sys.exit()

summary = df_all.groupby('scenario').mean().reset_index()

# Sort order
order = ['baseline', 'loss_2_lan', 'loss_5_wan', 'delay_100ms']
summary['scenario'] = pd.Categorical(summary['scenario'], categories=order, ordered=True)
summary = summary.sort_values('scenario')

print("\n=== TEST RESULTS SUMMARY ===")
print(summary)

# --- PLOT 1: LATENCY ---
plt.figure(figsize=(10, 6))
plt.bar(summary['scenario'], summary['latency_mean'], yerr=summary['latency_95']-summary['latency_mean'], capsize=5)
plt.title("Average Latency by Scenario (with 95th percentile error bars)")
plt.ylabel("Latency (ms)")
plt.grid(axis='y', alpha=0.5)
plt.savefig(f"{results_dir}/plot_latency.png")

# --- PLOT 2: RELIABILITY ---
plt.figure(figsize=(10, 6))
plt.plot(summary['scenario'], summary['reliability'], marker='o', color='green', linewidth=2)
plt.title("Action Reliability (Success Rate)")
plt.ylabel("Success %")
plt.ylim(80, 105) # Focus on the top range
plt.grid()
plt.savefig(f"{results_dir}/plot_reliability.png")

# --- PLOT 3: RETRANSMISSIONS ---
plt.figure(figsize=(10, 6))
plt.bar(summary['scenario'], summary['retransmits'], color='orange')
plt.title("Average Retransmissions per Run")
plt.ylabel("Count")
plt.grid(axis='y')
plt.savefig(f"{results_dir}/plot_retransmits.png")

print(f"\nPlots saved to {results_dir}/")