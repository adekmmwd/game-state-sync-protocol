#!/usr/bin/env python3
import pandas as pd
import matplotlib.pyplot as plt
import os
import sys
from pathlib import Path

results_dir = Path(sys.argv[1])

data = []
for csv_path in results_dir.rglob("metrics.csv"):
    scenario = csv_path.parts[-3]
    df = pd.read_csv(csv_path)
    # Adjust column names to what your collect_metrics.py actually outputs
    stats = {
        'scenario': scenario,
        'latency_mean': df['latency_ms'].mean(),
        'latency_95': df['latency_ms'].quantile(0.95),
        'jitter_mean': df['jitter_ms'].mean(),
        'position_error_mean': df['perceived_position_error'].mean(),
        'position_error_95': df['perceived_position_error'].quantile(0.95),
        'bandwidth_kbps': df['bandwidth_per_client_kbps'].mean(),
    }
    data.append(stats)

summary = pd.DataFrame(data)

# Sort scenarios in the correct order
order = ['baseline', 'loss_2_lan', 'loss_5_wan', 'delay_100ms']
summary['scenario'] = pd.Categorical(summary['scenario'], categories=order, ordered=True)
summary = summary.sort_values('scenario')

# Plots (exactly what the project asks for)
plt.figure(figsize=(10,6))
plt.plot(summary['scenario'], summary['latency_mean'], marker='o', label='Mean latency')
plt.plot(summary['scenario'], summary['latency_95'], marker='s', label='95th latency')
plt.ylabel('Latency (ms)'); plt.title('Latency vs Network Condition')
plt.legend(); plt.grid(); plt.savefig('results_latency.png')

plt.figure(figsize=(10,6))
plt.plot(summary['scenario'], summary['position_error_mean'], marker='o', label='Mean error')
plt.plot(summary['scenario'], summary['position_error_95'], marker='s', label='95th error')
plt.ylabel('Perceived Position Error (units)'); plt.title('Position Error vs Network Condition')
plt.legend(); plt.grid(); plt.savefig('results_position_error.png')

plt.figure(figsize=(10,6))
plt.bar(summary['scenario'], summary['bandwidth_kbps'])
plt.ylabel('Bandwidth per client (kbps)'); plt.title('Bandwidth vs Network Condition')
plt.savefig('results_bandwidth.png')

print("Summary plots saved: results_latency.png, results_position_error.png, results_bandwidth.png")