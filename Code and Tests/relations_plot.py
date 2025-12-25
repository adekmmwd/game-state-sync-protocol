import os
import re
import matplotlib.pyplot as plt
import numpy as np

def parse_stats_file(filepath):

    data = {}
    with open(filepath, 'r') as f:
        content = f.read()
        

        if "BASELINE" in content or "baseline" in content: data['test'] = 'Baseline'
        elif "LOSS2" in content or "loss2" in content: data['test'] = 'Loss 2%'
        elif "LOSS5" in content or "loss5" in content: data['test'] = 'Loss 5%'
        elif "DELAY100" in content or "delay100" in content: data['test'] = 'Delay 100ms'
        else: return None 

        # Latency
        m = re.search(r"Latency.*Mean=([\d\.]+)", content)
        data['latency'] = float(m.group(1)) if m else 0.0
        
        # Jitter
        m = re.search(r"Jitter.*Mean=([\d\.]+)", content)
        data['jitter'] = float(m.group(1)) if m else 0.0
        
        # Position Error
        m = re.search(r"Error.*Mean=([\d\.]+)", content)
        data['error'] = float(m.group(1)) if m else 0.0
        
        # Bandwidth (Total)
        m = re.search(r"Bandwidth.*Total.*[:=]\s*([\d\.]+)", content)
        data['bandwidth'] = float(m.group(1)) if m else 0.0
        
        # Update Rate (ups)
        m = re.search(r"Update Rate:\s+([\d\.]+)", content)
        data['ups'] = float(m.group(1)) if m else 0.0

        # Observed Packet Loss (The new metric)
        m = re.search(r"Loss Rate:\s+([\d\.]+)", content)
        data['loss_rate'] = float(m.group(1)) if m else 0.0
        
    return data

def main():
    results_dir = "results"
    all_data = []
    

    for root, dirs, files in os.walk(results_dir):
        if "stats_summary.txt" in files:
            path = os.path.join(root, "stats_summary.txt")
            stats = parse_stats_file(path)
            if stats:
                all_data.append(stats)

    if not all_data:
        return

    order_map = {'Baseline': 0, 'Loss 2%': 1, 'Loss 5%': 2, 'Delay 100ms': 3}
    all_data.sort(key=lambda x: order_map.get(x['test'], 99))

    loss_only = [d for d in all_data if d['test'] in ['Baseline', 'Loss 2%', 'Loss 5%']]
    loss_x_axis = [d['loss_rate'] for d in loss_only] 


    if len(loss_only) >= 2:
        # Latency vs Loss
        plt.figure(figsize=(8, 5))
        y_lat = [d['latency'] for d in loss_only]
        plt.plot(loss_x_axis, y_lat, marker='o', linestyle='-', color='blue', linewidth=2)
        plt.title("Impact of Packet Loss on Latency")
        plt.xlabel("Observed Packet Loss (%)")
        plt.ylabel("Mean Latency (ms)")
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.savefig("results/summary_latency_vs_loss.png")
        plt.close()

        # Jitter vs Loss
        plt.figure(figsize=(8, 5))
        y_jit = [d['jitter'] for d in loss_only]
        plt.plot(loss_x_axis, y_jit, marker='s', linestyle='-', color='orange', linewidth=2)
        plt.title("Impact of Packet Loss on Jitter")
        plt.xlabel("Observed Packet Loss (%)")
        plt.ylabel("Mean Jitter (ms)")
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.savefig("results/summary_jitter_vs_loss.png")
        plt.close()

        # Position Error vs Loss
        plt.figure(figsize=(8, 5))
        y_err = [d['error'] for d in loss_only]
        plt.plot(loss_x_axis, y_err, marker='^', linestyle='-', color='red', linewidth=2)
        plt.title("Impact of Packet Loss on Position Error")
        plt.xlabel("Observed Packet Loss (%)")
        plt.ylabel("Mean Position Error (Units)")
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.savefig("results/summary_error_vs_loss.png")
        plt.close()

    
        x_ups = [d['ups'] for d in loss_only]
        labels = [d['test'] for d in loss_only]

        # Metric 1: Latency vs UPS
        plt.figure(figsize=(8, 5))
        y_val = [d['latency'] for d in loss_only]
        plt.scatter(x_ups, y_val, color='blue', s=100, zorder=5)
        plt.plot(x_ups, y_val, color='blue', linestyle=':', alpha=0.5) 
        for i, txt in enumerate(labels):
            plt.annotate(txt, (x_ups[i], y_val[i]), xytext=(5, 5), textcoords='offset points')
        
        plt.gca().invert_xaxis() 
        plt.title("Latency vs Update Rate")
        plt.xlabel("Measured Update Rate (ups)")
        plt.ylabel("Mean Latency (ms)")
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.savefig("results/summary_latency_vs_ups.png")
        plt.close()

        # Jitter vs UPS
        plt.figure(figsize=(8, 5))
        y_val = [d['jitter'] for d in loss_only]
        plt.scatter(x_ups, y_val, color='orange', s=100, zorder=5)
        plt.plot(x_ups, y_val, color='orange', linestyle=':', alpha=0.5)
        for i, txt in enumerate(labels):
            plt.annotate(txt, (x_ups[i], y_val[i]), xytext=(5, 5), textcoords='offset points')
            
        plt.gca().invert_xaxis()
        plt.title("Jitter vs Update Rate")
        plt.xlabel("Measured Update Rate (ups)")
        plt.ylabel("Mean Jitter (ms)")
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.savefig("results/summary_jitter_vs_ups.png")
        plt.close()

        # Error vs UPS
        plt.figure(figsize=(8, 5))
        y_val = [d['error'] for d in loss_only]
        plt.scatter(x_ups, y_val, color='purple', s=100, zorder=5)
        plt.plot(x_ups, y_val, color='purple', linestyle=':', alpha=0.5)
        for i, txt in enumerate(labels):
            plt.annotate(txt, (x_ups[i], y_val[i]), xytext=(5, 5), textcoords='offset points')
            
        plt.gca().invert_xaxis()
        plt.title("Error vs Update Rate")
        plt.xlabel("Measured Update Rate (ups) ")
        plt.ylabel("Mean Position Error (Units)")
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.savefig("results/summary_error_vs_ups.png")
        plt.close()




    plt.figure(figsize=(10, 6))
    tests = [d['test'] for d in all_data]
    bws = [d['bandwidth'] for d in all_data]
    
    bars = plt.bar(tests, bws, color='#2ca02c', alpha=0.7, edgecolor='black', width=0.6)
    plt.title("Bandwidth Efficiency Across All Scenarios")
    plt.ylabel("Average Bandwidth (kbps)")
    plt.grid(axis='y', linestyle='--', alpha=0.6)
    
    for bar in bars:
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height,
                 f'{height:.2f}', ha='center', va='bottom')
    plt.savefig("results/summary_bandwidth_comparison.png")
    plt.close()

if __name__ == "__main__":
    main()