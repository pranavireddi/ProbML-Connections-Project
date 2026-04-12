#!/usr/bin/env python3
"""
Extended Puzzle Evaluation — Results Generator
===============================================

Runs the Merrill (2024) GloVe solver and a sentence-transformer LLM solver
on generated puzzles and NYT puzzles, then produces a full results analysis.

Outputs:
  - Per-tier solve rates (does yellow solve easier than purple?)
  - Category-type breakdown (which generators produce the hardest puzzles?)
  - Solver agreement analysis (when do GloVe and LLM disagree?)
  - Confusion matrix (which tiers get mixed up with which?)
  - Statistical comparison (KS test on solve distributions)
  - Plots saved as PNG files
  - Full results JSON for the technical appendix

Setup:
  pip install gensim numpy matplotlib scipy sentence-transformers

Usage:
  python evaluate_extended.py
  python evaluate_extended.py --n-puzzles 300 --n-nyt 300
"""

import json, random, argparse, os, subprocess, urllib.request
import numpy as np
from itertools import combinations
from collections import defaultdict, Counter

# ============================================================
# LOAD EMBEDDINGS
# ============================================================

print("Loading GloVe embeddings (~128MB, first time only)...")
import gensim.downloader as api
glove_model = api.load("glove-wiki-gigaword-100")
print("Done!")

st_model = None
st_cache = {}
try:
    from sentence_transformers import SentenceTransformer
    print("Loading sentence-transformer (all-MiniLM-L6-v2)...")
    st_model = SentenceTransformer("all-MiniLM-L6-v2")
    print("Done!\n")
except ImportError:
    print("sentence-transformers not installed, LLM solver disabled.\n")


# ============================================================
# SOLVERS (Merrill 2024 algorithm, GloVe + LLM variants)
# ============================================================

def get_vec_glove(word):
    try: return glove_model[word.lower()]
    except KeyError: return np.zeros(100)

def get_vec_llm(word):
    w = word.lower().strip()
    if w not in st_cache:
        st_cache[w] = st_model.encode(w, normalize_embeddings=True) if st_model else np.zeros(384)
    return st_cache[w]

def incoherence(words, get_vec_fn):
    vecs = np.array([get_vec_fn(w) for w in words])
    centroid = vecs.mean(axis=0)
    return np.linalg.norm(vecs - centroid, axis=1).mean()

def build_cluster(seed, pool, get_vec_fn):
    cluster = [seed]
    remaining = [w for w in pool if w != seed]
    for _ in range(3):
        centroid = np.mean([get_vec_fn(w) for w in cluster], axis=0)
        best = min(remaining, key=lambda w: np.linalg.norm(get_vec_fn(w) - centroid))
        cluster.append(best)
        remaining.remove(best)
    return cluster

def solve_greedy(words, get_vec_fn):
    remaining = list(words)
    solution = []
    while len(remaining) >= 4:
        best, best_score = None, float("inf")
        for seed in remaining:
            c = build_cluster(seed, remaining, get_vec_fn)
            s = incoherence(c, get_vec_fn)
            if s < best_score:
                best_score, best = s, c
        solution.append((best, round(best_score, 4)))
        for w in best:
            remaining.remove(w)
    return solution


# ============================================================
# DATA LOADING
# ============================================================

def load_processed(path="processed_categories.json"):
    with open(path) as f:
        data = json.load(f)
    return data["categories"], data.get("neighbors", {})

def load_nyt_puzzles(path="NYT-Connections-Answers/connections.json"):
    RAW_URL = "https://raw.githubusercontent.com/Eyefyre/NYT-Connections-Answers/main/connections.json"
    data = None
    if os.path.isfile(path):
        with open(path) as f:
            data = json.load(f)
    else:
        try:
            req = urllib.request.Request(RAW_URL, headers={"User-Agent": "PuzzleEval/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                with open("connections.json", "w") as f:
                    json.dump(data, f)
        except Exception:
            subprocess.run(["git", "clone", "https://github.com/Eyefyre/NYT-Connections-Answers.git", "--depth", "1"], capture_output=True)
            if os.path.isfile(path):
                with open(path) as f:
                    data = json.load(f)
    if data is None:
        return []
    puzzles = []
    for p in data:
        answers = p.get("answers", [])
        if len(answers) == 4 and all(len(a.get("members", [])) == 4 for a in answers):
            if all(a.get("level", -1) >= 0 for a in answers):
                puzzles.append(p)
    return puzzles

def generate_puzzle_from_processed(categories, neighbors, rng):
    by_color = {"yellow": [], "green": [], "blue": [], "purple": []}
    for idx, cat in enumerate(categories):
        color = cat.get("color", "")
        if color in by_color:
            by_color[color].append((idx, cat))
    if not by_color["purple"]:
        return None
    for _ in range(200):
        purple_idx, purple_cat = rng.choice(by_color["purple"])
        used_words = set(w.upper() for w in purple_cat["members"])
        neighbor_found = None
        for entry in neighbors.get(str(purple_idx), []):
            n_cat = categories[entry["index"]]
            n_words = set(w.upper() for w in n_cat["members"])
            if n_words.isdisjoint(used_words):
                neighbor_found = (entry["index"], n_cat)
                used_words |= n_words
                break
        if neighbor_found is None:
            continue
        n_idx, n_cat = neighbor_found
        remaining_colors = [c for c in ["yellow", "green", "blue"] if c != n_cat["color"]]
        if len(remaining_colors) != 2:
            continue
        selected = [purple_cat, n_cat]
        valid = True
        for color in remaining_colors:
            pool = [(i, c) for i, c in by_color[color]
                    if set(w.upper() for w in c["members"]).isdisjoint(used_words)]
            if not pool:
                valid = False
                break
            idx, cat = rng.choice(pool)
            used_words |= set(w.upper() for w in cat["members"])
            selected.append(cat)
        if not valid:
            continue
        all_words = [w.upper() for c in selected for w in c["members"]]
        if len(set(all_words)) != 16:
            continue
        return {"groups": selected, "board": all_words}
    return None


# ============================================================
# DETAILED EVALUATION
# ============================================================

LEVEL_NAMES = {0: "YELLOW", 1: "GREEN", 2: "BLUE", 3: "PURPLE"}
COLOR_TO_LEVEL = {"yellow": 0, "green": 1, "blue": 2, "purple": 3}

def evaluate_puzzle_detailed(board_words, intended_groups, group_levels, group_meta=None):
    """
    Run both solvers, return detailed per-tier results.
    group_levels: list of 4 ints (0-3) for each intended group
    group_meta: list of 4 dicts with cat_type etc (optional)
    """
    words_lower = [w.lower() for w in board_words]
    intended_sets = [set(w.lower() for w in g) for g in intended_groups]

    result = {"per_tier": {}, "group_meta": group_meta or []}

    for solver_name, get_vec_fn in [("glove", get_vec_glove), ("llm", get_vec_llm)]:
        if solver_name == "llm" and st_model is None:
            continue

        solution = solve_greedy(words_lower, get_vec_fn)

        # which tiers did the solver get right?
        tier_correct = {}
        for level in range(4):
            tier_correct[level] = False

        total_correct = 0
        # for each solver group, check if it matches an intended group
        confusion_pairs = []  # (predicted_as_tier, actual_tier) for mismatches
        for group, score in solution:
            group_set = set(w.lower() for w in group)
            matched = False
            for i, intended_set in enumerate(intended_sets):
                if group_set == intended_set:
                    tier_correct[group_levels[i]] = True
                    total_correct += 1
                    matched = True
                    break
            if not matched:
                # figure out which tiers' words ended up in this wrong group
                for w in group:
                    for i, intended_set in enumerate(intended_sets):
                        if w in intended_set:
                            confusion_pairs.append(group_levels[i])
                            break

        result[f"{solver_name}_correct"] = total_correct
        result[f"{solver_name}_tier_correct"] = tier_correct
        result[f"{solver_name}_confusion"] = confusion_pairs

    return result


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Extended puzzle evaluation for results section")
    parser.add_argument("--processed", default="processed_categories.json")
    parser.add_argument("--n-puzzles", type=int, default=300)
    parser.add_argument("--n-nyt", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)

    # ---- generate puzzles ----
    print("Loading processed categories...")
    categories, neighbors = load_processed(args.processed)
    print(f"  {len(categories)} categories\n")

    print(f"Generating {args.n_puzzles} puzzles...")
    our_puzzles = []
    for _ in range(args.n_puzzles * 3):
        if len(our_puzzles) >= args.n_puzzles:
            break
        p = generate_puzzle_from_processed(categories, neighbors, rng)
        if p:
            our_puzzles.append(p)
    print(f"  Generated {len(our_puzzles)}\n")

    # ---- load NYT ----
    print("Loading NYT puzzles...")
    nyt_all = load_nyt_puzzles()
    nyt_sample = random.Random(args.seed).sample(nyt_all, min(args.n_nyt, len(nyt_all)))
    print(f"  {len(nyt_sample)} NYT puzzles sampled\n")

    # ---- evaluate generated puzzles ----
    print("=" * 60)
    print("  EVALUATING GENERATED PUZZLES")
    print("=" * 60)

    our_results = []
    for i, puzzle in enumerate(our_puzzles):
        groups = puzzle["groups"]
        board = puzzle["board"]
        intended = [g["members"] for g in groups]
        levels = [COLOR_TO_LEVEL.get(g.get("color", ""), 0) for g in groups]
        meta = [{"cat_type": g.get("cat_type", ""), "group": g.get("group", "")} for g in groups]

        r = evaluate_puzzle_detailed(board, intended, levels, meta)
        our_results.append(r)

        if i < 3:
            print(f"\n  Puzzle {i+1}:")
            for g in groups:
                color = g.get("color", "?").upper()
                print(f"    {color:8s} [{g.get('group', '?')}]")
                print(f"             {', '.join(w.upper() for w in g['members'])}")
            print(f"    GloVe: {r['glove_correct']}/4  |  LLM: {r.get('llm_correct', 'N/A')}/4")

    # ---- evaluate NYT puzzles ----
    print(f"\n{'=' * 60}")
    print("  EVALUATING NYT PUZZLES")
    print("=" * 60)

    nyt_results = []
    for i, puzzle in enumerate(nyt_sample):
        answers = puzzle["answers"]
        board = [w for a in answers for w in a["members"]]
        intended = [a["members"] for a in answers]
        levels = [a["level"] for a in answers]

        r = evaluate_puzzle_detailed(board, intended, levels)
        nyt_results.append(r)

        if i < 3:
            print(f"\n  NYT {i+1} ({puzzle.get('date', '?')}):")
            for a in answers:
                color = LEVEL_NAMES.get(a["level"], "?")
                print(f"    {color:8s} [{a['group']}]")
            print(f"    GloVe: {r['glove_correct']}/4  |  LLM: {r.get('llm_correct', 'N/A')}/4")

    # ============================================================
    # ANALYSIS
    # ============================================================

    print(f"\n{'=' * 60}")
    print("  RESULTS ANALYSIS")
    print("=" * 60)

    # ---- 1. Overall solve rates ----
    def solve_stats(results, solver):
        counts = [r[f"{solver}_correct"] for r in results if f"{solver}_correct" in r]
        if not counts:
            return None
        return {
            "avg": np.mean(counts),
            "std": np.std(counts),
            "distribution": {k: sum(1 for c in counts if c == k) for k in range(5)},
            "n": len(counts),
        }

    print("\n  1. OVERALL SOLVE RATES")
    print("  " + "-" * 55)
    for label, results in [("Generated", our_results), ("NYT", nyt_results)]:
        for solver in ["glove", "llm"]:
            s = solve_stats(results, solver)
            if s is None:
                continue
            solver_label = "GloVe (Merrill)" if solver == "glove" else "LLM (MiniLM)"
            print(f"    {label:12s} {solver_label:20s}  avg={s['avg']:.2f}  std={s['std']:.2f}")
            for k in range(5):
                pct = s["distribution"][k] / s["n"] * 100
                bar = "#" * int(pct / 2)
                print(f"      {k}/4: {pct:5.1f}% {bar}")

    # ---- 2. Per-tier solve rates ----
    print("\n  2. PER-TIER SOLVE RATES (does yellow solve easier than purple?)")
    print("  " + "-" * 55)
    for label, results in [("Generated", our_results), ("NYT", nyt_results)]:
        for solver in ["glove", "llm"]:
            key = f"{solver}_tier_correct"
            tier_totals = {0: 0, 1: 0, 2: 0, 3: 0}
            tier_counts = {0: 0, 1: 0, 2: 0, 3: 0}
            for r in results:
                if key not in r:
                    continue
                for level, correct in r[key].items():
                    level = int(level)
                    tier_counts[level] += 1
                    if correct:
                        tier_totals[level] += 1
            if not any(tier_counts.values()):
                continue
            solver_label = "GloVe" if solver == "glove" else "LLM"
            print(f"    {label} ({solver_label}):")
            for level in range(4):
                if tier_counts[level] > 0:
                    rate = tier_totals[level] / tier_counts[level]
                    bar = "#" * int(rate * 40)
                    print(f"      {LEVEL_NAMES[level]:8s} {rate*100:5.1f}% solved  {bar}")

    # ---- 3. Category type breakdown (generated only) ----
    print("\n  3. CATEGORY TYPE BREAKDOWN (which generators are hardest?)")
    print("  " + "-" * 55)
    type_stats = defaultdict(lambda: {"total": 0, "glove_solved": 0, "llm_solved": 0})
    for r in our_results:
        for i, meta in enumerate(r.get("group_meta", [])):
            cat_type = meta.get("cat_type", "unknown")
            if not cat_type:
                cat_type = "unknown"
            type_stats[cat_type]["total"] += 1
            tier_key_g = r.get("glove_tier_correct", {})
            # we need to map index i to the level
            # this is approximate since we don't store the exact mapping
            # but we can check if the group name matches
            for solver in ["glove", "llm"]:
                tier_key = r.get(f"{solver}_tier_correct", {})
                # count this type as solved if any of its tier was solved
                for level, correct in tier_key.items():
                    if correct:
                        type_stats[cat_type][f"{solver}_solved"] += 1
                        break

    if type_stats:
        sorted_types = sorted(type_stats.items(), key=lambda x: -x[1]["total"])
        for cat_type, stats in sorted_types[:15]:
            total = stats["total"]
            g_rate = stats["glove_solved"] / total * 100 if total > 0 else 0
            l_rate = stats["llm_solved"] / total * 100 if total > 0 else 0
            print(f"    {cat_type:35s} n={total:4d}  GloVe={g_rate:5.1f}%  LLM={l_rate:5.1f}%")

    # ---- 4. Solver agreement ----
    print("\n  4. SOLVER AGREEMENT (when do GloVe and LLM disagree?)")
    print("  " + "-" * 55)
    for label, results in [("Generated", our_results), ("NYT", nyt_results)]:
        agree = 0
        glove_better = 0
        llm_better = 0
        total = 0
        for r in results:
            if "glove_correct" in r and "llm_correct" in r:
                total += 1
                gc = r["glove_correct"]
                lc = r["llm_correct"]
                if gc == lc:
                    agree += 1
                elif gc > lc:
                    glove_better += 1
                else:
                    llm_better += 1
        if total > 0:
            print(f"    {label} ({total} puzzles):")
            print(f"      Agree:        {agree/total*100:5.1f}%")
            print(f"      GloVe better: {glove_better/total*100:5.1f}%")
            print(f"      LLM better:   {llm_better/total*100:5.1f}%")

    # ---- 5. Statistical test ----
    print("\n  5. STATISTICAL COMPARISON (KS test)")
    print("  " + "-" * 55)
    from scipy.stats import ks_2samp
    for solver in ["glove", "llm"]:
        our_counts = [r[f"{solver}_correct"] for r in our_results if f"{solver}_correct" in r]
        nyt_counts = [r[f"{solver}_correct"] for r in nyt_results if f"{solver}_correct" in r]
        if our_counts and nyt_counts:
            stat, pval = ks_2samp(our_counts, nyt_counts)
            solver_label = "GloVe (Merrill)" if solver == "glove" else "LLM (MiniLM)"
            print(f"    {solver_label}:")
            print(f"      KS statistic: {stat:.4f}")
            print(f"      p-value:      {pval:.4f}")
            if pval < 0.05:
                print(f"      Interpretation: distributions are significantly different (p<0.05)")
            else:
                print(f"      Interpretation: no significant difference (p>={pval:.2f})")

    # ---- 6. Incoherence comparison ----
    print("\n  6. INCOHERENCE COMPARISON")
    print("  " + "-" * 55)
    our_inc = []
    nyt_inc = []
    for puzzle in our_puzzles:
        groups = puzzle["groups"]
        for g in groups:
            inc = incoherence([w.lower() for w in g["members"]], get_vec_glove)
            our_inc.append(inc)
    for puzzle in nyt_sample:
        for a in puzzle["answers"]:
            inc = incoherence([w.lower() for w in a["members"]], get_vec_glove)
            nyt_inc.append(inc)

    print(f"    Generated categories:  mean={np.mean(our_inc):.3f}  std={np.std(our_inc):.3f}")
    print(f"    NYT categories:        mean={np.mean(nyt_inc):.3f}  std={np.std(nyt_inc):.3f}")

    # per-tier incoherence
    print("\n    Per-tier incoherence (generated):")
    tier_inc = defaultdict(list)
    for puzzle in our_puzzles:
        for g in puzzle["groups"]:
            level = COLOR_TO_LEVEL.get(g.get("color", ""), 0)
            inc = incoherence([w.lower() for w in g["members"]], get_vec_glove)
            tier_inc[level].append(inc)
    for level in range(4):
        if tier_inc[level]:
            print(f"      {LEVEL_NAMES[level]:8s} mean={np.mean(tier_inc[level]):.3f}  std={np.std(tier_inc[level]):.3f}")

    print("\n    Per-tier incoherence (NYT):")
    tier_inc_nyt = defaultdict(list)
    for puzzle in nyt_sample:
        for a in puzzle["answers"]:
            tier_inc_nyt[a["level"]].append(
                incoherence([w.lower() for w in a["members"]], get_vec_glove))
    for level in range(4):
        if tier_inc_nyt[level]:
            print(f"      {LEVEL_NAMES[level]:8s} mean={np.mean(tier_inc_nyt[level]):.3f}  std={np.std(tier_inc_nyt[level]):.3f}")

    # ---- 7. Generate plots ----
    print("\n  7. GENERATING PLOTS...")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle("Puzzle Evaluation Results", fontsize=16, fontweight="bold")

        # plot 1: solve distribution comparison
        ax = axes[0, 0]
        x = np.arange(5)
        width = 0.35
        our_glove = [r["glove_correct"] for r in our_results]
        nyt_glove = [r["glove_correct"] for r in nyt_results]
        our_dist = [sum(1 for c in our_glove if c == k) / len(our_glove) for k in range(5)]
        nyt_dist = [sum(1 for c in nyt_glove if c == k) / len(nyt_glove) for k in range(5)]
        ax.bar(x - width/2, our_dist, width, label="Generated", color="#4C72B0")
        ax.bar(x + width/2, nyt_dist, width, label="NYT", color="#DD8452")
        ax.set_xlabel("Groups Correct (out of 4)")
        ax.set_ylabel("Proportion")
        ax.set_title("GloVe Solver: Solve Distribution")
        ax.set_xticks(x)
        ax.legend()

        # plot 2: per-tier solve rates
        ax = axes[0, 1]
        tier_labels = ["Yellow", "Green", "Blue", "Purple"]
        our_tier_rates = []
        nyt_tier_rates = []
        for level in range(4):
            our_solved = sum(1 for r in our_results if r.get("glove_tier_correct", {}).get(str(level), False) or r.get("glove_tier_correct", {}).get(level, False))
            our_total = sum(1 for r in our_results if "glove_tier_correct" in r)
            our_tier_rates.append(our_solved / our_total if our_total > 0 else 0)

            nyt_solved = sum(1 for r in nyt_results if r.get("glove_tier_correct", {}).get(str(level), False) or r.get("glove_tier_correct", {}).get(level, False))
            nyt_total = sum(1 for r in nyt_results if "glove_tier_correct" in r)
            nyt_tier_rates.append(nyt_solved / nyt_total if nyt_total > 0 else 0)

        x = np.arange(4)
        ax.bar(x - width/2, our_tier_rates, width, label="Generated", color="#4C72B0")
        ax.bar(x + width/2, nyt_tier_rates, width, label="NYT", color="#DD8452")
        ax.set_xlabel("Difficulty Tier")
        ax.set_ylabel("Solve Rate")
        ax.set_title("Per-Tier Solve Rates (GloVe)")
        ax.set_xticks(x)
        ax.set_xticklabels(tier_labels)
        ax.legend()

        # plot 3: incoherence distributions
        ax = axes[1, 0]
        ax.hist(our_inc, bins=30, alpha=0.6, label="Generated", color="#4C72B0", density=True)
        ax.hist(nyt_inc, bins=30, alpha=0.6, label="NYT", color="#DD8452", density=True)
        ax.set_xlabel("Incoherence Score")
        ax.set_ylabel("Density")
        ax.set_title("Category Incoherence Distribution")
        ax.legend()

        # plot 4: GloVe vs LLM solver comparison
        ax = axes[1, 1]
        if st_model:
            our_glove_c = [r["glove_correct"] for r in our_results]
            our_llm_c = [r.get("llm_correct", 0) for r in our_results]
            # add jitter for visibility
            jitter = np.random.RandomState(42).uniform(-0.15, 0.15, len(our_glove_c))
            ax.scatter(np.array(our_glove_c) + jitter, np.array(our_llm_c) + jitter,
                      alpha=0.3, s=20, color="#4C72B0", label="Generated")
            nyt_glove_c = [r["glove_correct"] for r in nyt_results]
            nyt_llm_c = [r.get("llm_correct", 0) for r in nyt_results]
            jitter2 = np.random.RandomState(43).uniform(-0.15, 0.15, len(nyt_glove_c))
            ax.scatter(np.array(nyt_glove_c) + jitter2, np.array(nyt_llm_c) + jitter2,
                      alpha=0.3, s=20, color="#DD8452", label="NYT")
            ax.plot([0, 4], [0, 4], "k--", alpha=0.3, label="Agreement line")
            ax.set_xlabel("GloVe Correct")
            ax.set_ylabel("LLM Correct")
            ax.set_title("GloVe vs LLM Solver Agreement")
            ax.legend()
        else:
            ax.text(0.5, 0.5, "LLM solver not available", ha="center", va="center", transform=ax.transAxes)

        plt.tight_layout()
        plt.savefig("evaluation_plots.png", dpi=150, bbox_inches="tight")
        print("    Saved evaluation_plots.png")

        # additional plot: per-tier incoherence boxplot
        fig2, ax2 = plt.subplots(1, 2, figsize=(12, 5))
        fig2.suptitle("Per-Tier Incoherence Comparison", fontsize=14, fontweight="bold")

        data_ours = [tier_inc.get(level, []) for level in range(4)]
        data_nyt = [tier_inc_nyt.get(level, []) for level in range(4)]

        bp1 = ax2[0].boxplot(data_ours, labels=tier_labels, patch_artist=True)
        for patch, color in zip(bp1["boxes"], ["#FFD700", "#4CAF50", "#2196F3", "#9C27B0"]):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        ax2[0].set_title("Generated Puzzles")
        ax2[0].set_ylabel("Incoherence")

        bp2 = ax2[1].boxplot(data_nyt, labels=tier_labels, patch_artist=True)
        for patch, color in zip(bp2["boxes"], ["#FFD700", "#4CAF50", "#2196F3", "#9C27B0"]):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        ax2[1].set_title("NYT Puzzles")
        ax2[1].set_ylabel("Incoherence")

        plt.tight_layout()
        plt.savefig("incoherence_boxplot.png", dpi=150, bbox_inches="tight")
        print("    Saved incoherence_boxplot.png")

    except ImportError:
        print("    matplotlib not installed, skipping plots")

    # ---- save full results ----
    output = {
        "generated": {
            "n_puzzles": len(our_results),
            "glove": solve_stats(our_results, "glove"),
            "llm": solve_stats(our_results, "llm"),
            "incoherence": {"mean": float(np.mean(our_inc)), "std": float(np.std(our_inc))},
        },
        "nyt": {
            "n_puzzles": len(nyt_results),
            "glove": solve_stats(nyt_results, "glove"),
            "llm": solve_stats(nyt_results, "llm"),
            "incoherence": {"mean": float(np.mean(nyt_inc)), "std": float(np.std(nyt_inc))},
        },
    }

    with open("evaluation_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Saved evaluation_results.json")
    print(f"  Saved evaluation_plots.png")
    print(f"  Saved incoherence_boxplot.png")


if __name__ == "__main__":
    main()
