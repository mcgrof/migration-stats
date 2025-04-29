#!/usr/bin/env python3

import argparse
import os
import re
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.colors as mcolors
from matplotlib.ticker import FuncFormatter

def human_format(num):
    if num >= 1_000_000:
        return f"{num//1_000_000:,}M"
    elif num >= 1_000:
        return f"{num//1_000:,}K"
    return f"{num:,}"

def parse_stats_file(filename):
    stats = {}
    with open(filename) as f:
        for line in f:
            line = line.strip()

            # [Skip section headers]
            if not line or line.startswith("["):
                continue

            # Parse success ratio line
            m = re.match(r'buffer_migrate_folio_norefs:\s+(\d+)% success\s+\((\d+)/(\d+)\)', line)
            if m:
                success = int(m.group(2))
                total = int(m.group(3))
                stats.setdefault("norefs_success_summary", []).append(success)
                stats.setdefault("norefs_total_summary", []).append(total)
                continue

            # Skip other summary lines
            if line.startswith("Success ratios:"):
                continue

            # Parse standard stat line
            parts = re.split(r'\s+', line)
            if len(parts) != 2:
                continue
            key, value = parts
            stats.setdefault(key.strip(), []).append(int(value))
    return stats

def truncate_all(stats_dicts):
    """Truncate all series to the shortest length."""
    min_len = min(len(v) for stats in stats_dicts.values() for v in stats.values())
    return {
        name: {k: v[:min_len] for k, v in stats.items()}
        for name, stats in stats_dicts.items()
    }, min_len

def plot_general(stats_map, min_len, output_file):
    fig, axes = plt.subplots(len(stats_map), 1, figsize=(12, 4 * len(stats_map)))
    if len(stats_map) == 1:
        axes = [axes]

    time = [(i * 60) / 3600.0 for i in range(min_len)]  # hours

    ymax = 0
    for ax, (dut_name, stats) in zip(axes, stats_map.items()):
        success = stats.get("success", [0] * min_len)
        fails = stats.get("fails", [0] * min_len)
        invalid = stats.get("invalid", [0] * min_len)
        ymax = max(ymax, max(
            max(fails) if fails else 0,
            max(success) if success else 0,
            max(invalid) if invalid else 0,
        ))

    for ax, (dut_name, stats) in zip(axes, stats_map.items()):
        success = stats.get("success", [0] * min_len)
        fails = stats.get("fails", [0] * min_len)
        invalid = stats.get("invalid", [0] * min_len)

        # Stack success + fails
        ax.stackplot(time, fails, success, labels=["fails", "success"], colors=["red", "green"], alpha=0.6)

        # Overlay invalid as a flat line
        ax.plot(time, invalid, label="invalid", color="hotpink", linewidth=2.0, zorder=10)

        ax.set_title(f"[GENERAL] {dut_name}")
        ax.set_xlabel("Time (hours)")
        ax.set_ylabel("Events")
        ax.set_ylim(0, ymax * 1.1 if ymax > 0 else 1)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: human_format(int(x))))
        ax.grid(True)
        ax.legend(loc="upper left")

    plt.tight_layout()
    fig.savefig(output_file)
    print(f"Saved general stacked plot to: {output_file}")


def plot_valid_ratio(pct_by_dut, time, output_prefix):
    """
    Plot the ultra-zoomed success ratio plot focusing on top differences.
    """
    fig1 = plt.figure(figsize=(12, 6))
    fig1.set_constrained_layout(True)
    ax1 = fig1.add_subplot(111)

    # Rank based on final ratio value
    final_ratios = {dut: series[-1] if series else 0 for dut, series in pct_by_dut.items()}
    sorted_duts = sorted(final_ratios.items(), key=lambda x: x[1])

    if not sorted_duts:  # No data
        return

    worst_dut, best_dut = sorted_duts[0][0], sorted_duts[-1][0]

    # Use a color gradient for middle DUTs
    middle_duts = [dut for dut, _ in sorted_duts[1:-1]] if len(sorted_duts) > 2 else []
    cmap = plt.colormaps["viridis"]
    norm = mcolors.Normalize(vmin=0, vmax=max(1, len(middle_duts)))

    # Calculate the range of final values to determine zoom level
    non_zero_finals = [v for v in final_ratios.values() if v > 0]
    if non_zero_finals:
        min_final = min(non_zero_finals)
        max_final = max(non_zero_finals)
        value_range = max_final - min_final

        # Ultra-zoom if the range is very small
        if value_range < 0.5:  # Less than 0.5% difference
            min_y = max(99.0, min_final - (value_range * 0.5))
            max_y = min(100.0, max_final + (value_range * 0.5))
        else:
            min_y = max(95.0, min_final - 1.0)
            max_y = 100.5
    else:
        min_y = 95.0
        max_y = 100.5

    # Plot data
    for dut_name, ratio in pct_by_dut.items():
        if dut_name == best_dut:
            color = "green"
            zorder = len(pct_by_dut) + 1
            linewidth = 2.5
            marker = 'o'
            markersize = 4
        elif dut_name == worst_dut:
            color = "red"
            zorder = len(pct_by_dut)
            linewidth = 2.5
            marker = 's'  # square marker
            markersize = 4
        else:
            idx = middle_duts.index(dut_name) if middle_duts and dut_name in middle_duts else 0
            color = cmap(norm(idx))
            zorder = idx
            linewidth = 1.5
            marker = None
            markersize = 0

        # Plot with markers for best and worst
        ax1.plot(time, ratio,
                label=f"{dut_name} ({final_ratios[dut_name]:.3f}%)",
                color=color, linewidth=linewidth, zorder=zorder,
                marker=marker, markersize=markersize, markevery=max(1, len(time)//20))

    # Set ultra-zoomed y-axis
    ax1.set_ylim(min_y, max_y)

    # Add broken axis indicator
    d = .015  # size of diagonal lines
    kwargs = dict(transform=ax1.transAxes, color='k', clip_on=False, linewidth=1.5)
    ax1.plot((-d, +d), (-d, +d), **kwargs)        # bottom-left diagonal
    ax1.plot((1 - d, 1 + d), (-d, +d), **kwargs)  # bottom-right diagonal

    # Main axis formatting
    ax1.set_title(f"Valid Success Ratio (%) - Ultra-Zoomed View ({min_y:.3f}% to {max_y:.3f}%)")
    ax1.set_xlabel("Time (hours)")
    ax1.set_ylabel(f"Success % ({min_y:.3f}% - {max_y:.3f}%)")

    # Format y-axis ticks to show higher precision
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.3f}%'))

    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="lower right", fontsize='small')

    fig1.savefig(f"{output_prefix}-ratio.png", bbox_inches='tight')
    print(f"Saved ultra-zoomed valid success ratio plot to: {output_prefix}-ratio.png")

def plot_valid_success(valid_success_by_dut, time, output_prefix):
    """
    Plot the success counts with color-coded best/worst performers.
    """
    fig = plt.figure(figsize=(12, 6))
    fig.set_constrained_layout(True)
    ax = fig.add_subplot(111)

    # Rank based on final success count
    final_success = {dut: series[-1] if series else 0 for dut, series in valid_success_by_dut.items()}
    sorted_success = sorted(final_success.items(), key=lambda x: x[1])

    if not sorted_success:  # No data
        return

    worst_success_dut, best_success_dut = sorted_success[0][0], sorted_success[-1][0]

    # Use a color gradient for middle DUTs
    middle_success_duts = [dut for dut, _ in sorted_success[1:-1]] if len(sorted_success) > 2 else []
    success_cmap = plt.colormaps["viridis"]
    success_norm = mcolors.Normalize(vmin=0, vmax=max(1, len(middle_success_duts)))

    for dut_name, success_series in valid_success_by_dut.items():
        if dut_name == best_success_dut:
            color = "green"
            zorder = len(valid_success_by_dut) + 1
            linewidth = 2.5
        elif dut_name == worst_success_dut:
            color = "red"
            zorder = len(valid_success_by_dut)
            linewidth = 2.5
        else:
            idx = middle_success_duts.index(dut_name) if middle_success_duts and dut_name in middle_success_duts else 0
            color = success_cmap(success_norm(idx))
            zorder = idx
            linewidth = 1.5

        ax.plot(time, success_series,
                label=f"{dut_name} ({human_format(final_success[dut_name])})",
                color=color, linewidth=linewidth, zorder=zorder)

    ax.set_title("Valid Success Counts")
    ax.set_xlabel("Time (hours)")
    ax.set_ylabel("Events")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", fontsize='small')
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: human_format(int(x))))

    fig.savefig(f"{output_prefix}-success.png", bbox_inches='tight')
    print(f"Saved valid success counts plot to: {output_prefix}-success.png")


def plot_valid_fails(valid_fails_by_dut, time, output_prefix):
    """
    Plot the fail counts with inverse color-coding (best=lowest fails).
    """
    fig = plt.figure(figsize=(12, 6))
    fig.set_constrained_layout(True)
    ax = fig.add_subplot(111)

    # Rank based on final fail count - INVERSE coloring from the others!
    final_fails = {dut: series[-1] if series else 0 for dut, series in valid_fails_by_dut.items()}
    sorted_fails = sorted(final_fails.items(), key=lambda x: x[1])

    if not sorted_fails:  # No data
        return

    # REVERSED: best is lowest fails, worst is highest fails
    best_fails_dut, worst_fails_dut = sorted_fails[0][0], sorted_fails[-1][0]

    # Use a color gradient for middle DUTs
    middle_fails_duts = [dut for dut, _ in sorted_fails[1:-1]] if len(sorted_fails) > 2 else []
    fails_cmap = plt.colormaps["viridis"]
    fails_norm = mcolors.Normalize(vmin=0, vmax=max(1, len(middle_fails_duts)))

    for dut_name, fails_series in valid_fails_by_dut.items():
        if dut_name == best_fails_dut:  # Best = LOWEST fails
            color = "green"
            zorder = len(valid_fails_by_dut) + 1
            linewidth = 2.5
        elif dut_name == worst_fails_dut:  # Worst = HIGHEST fails
            color = "red"
            zorder = len(valid_fails_by_dut)
            linewidth = 2.5
        else:
            idx = middle_fails_duts.index(dut_name) if middle_fails_duts and dut_name in middle_fails_duts else 0
            color = fails_cmap(fails_norm(idx))
            zorder = idx
            linewidth = 1.5

        ax.plot(time, fails_series,
                label=f"{dut_name} ({human_format(final_fails[dut_name])})",
                color=color, linewidth=linewidth, zorder=zorder)

    ax.set_title("Valid Fail Counts")
    ax.set_xlabel("Time (hours)")
    ax.set_ylabel("Events")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", fontsize='small')
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: human_format(int(x))))

    fig.savefig(f"{output_prefix}-fails.png", bbox_inches='tight')
    print(f"Saved valid fail counts plot to: {output_prefix}-fails.png")

def plot_valid(stats_map, min_len, output_prefix):
    """
    Main function to prepare data and call the individual plotting functions.
    """
    time = [(i * 60) / 3600.0 for i in range(min_len)]

    pct_by_dut = {}
    valid_success_by_dut = {}
    valid_fails_by_dut = {}

    for dut_name, stats in stats_map.items():
        v_success = stats.get("valid-success", [0] * min_len)
        v_fails = stats.get("valid-fails", [0] * min_len)

        # Protect division
        ratio = []
        for s, f in zip(v_success, v_fails):
            total = s + f
            if total == 0:
                ratio.append(0)
            else:
                ratio.append((s / total) * 100)

        pct_by_dut[dut_name] = ratio
        valid_success_by_dut[dut_name] = v_success
        valid_fails_by_dut[dut_name] = v_fails

    # Call the individual plotting functions
    plot_valid_ratio(pct_by_dut, time, output_prefix)
    plot_valid_success(valid_success_by_dut, time, output_prefix)
    plot_valid_fails(valid_fails_by_dut, time, output_prefix)

def plot_success_rate(stats_map, min_len, output_file):
    fig, ax = plt.subplots(figsize=(12, 6))
    time = [(i * 60) / 3600.0 for i in range(min_len)]

    pct_by_dut = {}
    for dut_name, stats in stats_map.items():
        total = stats.get("norefs_total_summary", [0] * min_len)
        success = stats.get("norefs_success_summary", [0] * min_len)
        pct = [(s / t) * 100 if t > 0 else 0 for s, t in zip(success, total)]
        pct_by_dut[dut_name] = pct

    # Rank based on final value
    final_scores = {dut: series[-1] for dut, series in pct_by_dut.items()}
    sorted_duts = sorted(final_scores.items(), key=lambda x: x[1])
    worst_dut, best_dut = sorted_duts[0][0], sorted_duts[-1][0]

    # Use red for worst, green for best, greys for middle
    middle_duts = [dut for dut, _ in sorted_duts[1:-1]]
    cmap = plt.colormaps["Greys"]
    norm = mcolors.Normalize(vmin=0, vmax=len(middle_duts) + 1)

    for idx, (dut, pct) in enumerate(pct_by_dut.items()):
        if dut == best_dut:
            color = "green"
            zorder = 3
        elif dut == worst_dut:
            color = "red"
            zorder = 2
        else:
            color = cmap(norm(middle_duts.index(dut) + 1))
            zorder = 1
        ax.plot(time, pct, label=dut, color=color, linewidth=2, zorder=zorder)

    max_pct = max((max(pct) for pct in pct_by_dut.values() if pct), default=100)
    ax.set_ylim(0, max_pct * 1.1 if max_pct > 0 else 1)

    ax.set_title("buffer_migrate_folio_norefs Success Rate")
    ax.set_xlabel("Time (hours)")
    ax.set_ylabel("Success %")
    ax.grid(True)
    ax.legend(loc="lower right")

    plt.tight_layout()
    fig.savefig(output_file)
    print(f"Saved success % plot to: {output_file}")

def main():
    parser = argparse.ArgumentParser(description="Plot folio migration stats into general and valid-specific graphs.")
    parser.add_argument("stats_files", nargs='+', help="List of *.stats.txt files")
    parser.add_argument("-o", "--output-general", default="stats-general.png", help="Output PNG for general overview")
    parser.add_argument("-v", "--output-valid", default="stats-valid.png", help="Output PNG for valid-only stats")
    parser.add_argument("-p", "--output-pct", default="stats-pct.png", help="Output PNG for success % plot")
    args = parser.parse_args()

    stats_raw = {}
    for file in args.stats_files:
        name = os.path.splitext(os.path.basename(file))[0]
        stats_raw[name] = parse_stats_file(file)

    stats_map, min_len = truncate_all(stats_raw)

    plot_general(stats_map, min_len, args.output_general)
    plot_valid(stats_map, min_len, args.output_valid)
    plot_success_rate(stats_map, min_len, args.output_pct)

if __name__ == "__main__":
    main()

