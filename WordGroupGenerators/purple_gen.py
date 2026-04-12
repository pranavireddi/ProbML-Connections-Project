#!/usr/bin/env python3
"""
Purple Connections Generator — 10K Batch Mode

Generates 10,000 purple (hardest tier) categories for NYT Connections puzzles.
Word pool comes from WordNet + wordfreq — no words.txt needed.

Setup:
  pip install pronouncing nltk wordfreq
  python -c "import nltk; nltk.download('wordnet'); nltk.download('omw-1.4')"

Usage:
  python purple_gen.py                          # 10,000 categories
  python purple_gen.py --count 500 --seed 42    # smaller test run
  python purple_gen.py --min-zipf 2.5           # bigger word pool
"""

import json
import os
import re
import random
import subprocess
import argparse
from collections import defaultdict, Counter
from itertools import combinations

import pronouncing
import nltk

nltk.download("wordnet", quiet=True)
nltk.download("omw-1.4", quiet=True)

from nltk.corpus import wordnet as wn
from wordfreq import zipf_frequency

REPO_URL = "https://github.com/Eyefyre/NYT-Connections-Answers.git"
REPO_DIR = "NYT-Connections-Answers"
DATA_FILE = os.path.join(REPO_DIR, "connections.json")

VOWELS = set("aeiou")
LEFT_HAND = set("qwertasdfgzxcvb")
RIGHT_HAND = set("yuiophjklnm")
NUMBERS = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


# ============================================================
# SETUP
# ============================================================

def sync_repo():
    if os.path.isdir(REPO_DIR):
        subprocess.run(["git", "-C", REPO_DIR, "pull", "--ff-only"], capture_output=True)
    else:
        if subprocess.run(["git", "clone", REPO_URL, "--depth", "1"], capture_output=True).returncode != 0:
            return False
    return True


def load_past():
    past = set()
    if not os.path.isfile(DATA_FILE):
        return past
    for puzzle in json.load(open(DATA_FILE)):
        for answer in puzzle["answers"]:
            if answer.get("level", -1) >= 0:
                past.add(tuple(sorted(m.upper() for m in answer["members"])))
    return past


def is_dupe(words, past):
    return tuple(sorted(w.upper() for w in words)) in past


def collect_common_wordnet_words(min_zipf=2.8):
    """Pull all common English words from WordNet, filtered by frequency."""
    out = set()
    for syn in wn.all_synsets():
        for lemma in syn.lemmas():
            w = lemma.name().lower()
            if "_" in w or "-" in w or " " in w:
                continue
            if not re.fullmatch(r"[a-z]+", w):
                continue
            if len(w) < 3 or len(w) > 12:
                continue
            if zipf_frequency(w, "en") < min_zipf:
                continue
            out.add(w)
    return out


def build_pron():
    pronouncing.init_cmu()
    w2p = defaultdict(list)
    p2w = defaultdict(list)
    for word, pron in pronouncing.pronunciations:
        w = word.lower().strip("()")
        if w.isalpha():
            w2p[w].append(pron)
            p2w[pron].append(w)
    return w2p, p2w


# ============================================================
# HELPERS
# ============================================================

def get_vowels(word):
    return [c for c in word if c in VOWELS]


def has_all_same_vowel(word):
    v = get_vowels(word)
    return len(v) >= 2 and len(set(v)) == 1


def is_alternating(word):
    return len(word) >= 5 and all(
        (word[i] in VOWELS) != (word[i + 1] in VOWELS)
        for i in range(len(word) - 1)
    )


def count_double_pairs(word):
    return sum(word[i] == word[i + 1] for i in range(len(word) - 1))


def typed_with(word, keys):
    return len(word) >= 4 and all(c in keys for c in word)


def contains_sub(word, sub):
    return sub in word and word != sub and len(word) >= len(sub) + 1


def rhyme_key(pron):
    phones = pron.split()
    for i in range(len(phones) - 1, -1, -1):
        if any(c.isdigit() for c in phones[i]):
            return " ".join(phones[i:])
    return pron


def get_rhyme(word, w2p):
    prons = w2p.get(word, [])
    return rhyme_key(prons[0]) if prons else None


def pick_from_groups(groups, past, count):
    """Pick count groups of 4 words from a dict of {key: [words]}."""
    good = {k: v for k, v in groups.items() if len(v) >= 4}
    keys = list(good.keys())
    random.shuffle(keys)
    results = []
    for key in keys:
        if len(results) >= count:
            break
        picked = random.sample(good[key], 4)
        if not is_dupe(picked, past):
            results.append((key, picked))
    return results


def chunk_and_pick(items, past, count):
    """Chunk a list into groups of 4, dupe-check each, return up to count."""
    random.shuffle(items)
    results = []
    for i in range(0, len(items) - 3, 4):
        if len(results) >= count:
            break
        picked = items[i:i + 4]
        words = [p[0] if isinstance(p, tuple) else p for p in picked]
        if len(set(words)) == 4 and not is_dupe(words, past):
            results.append(picked)
    return results


# ============================================================
# TIER 1: META WORD PROPERTIES
# ============================================================

def gen_same_vowel(common, past, count):
    groups = defaultdict(list)
    for w in common:
        if has_all_same_vowel(w) and len(w) >= 5:
            groups[get_vowels(w)[0]].append(w)
    return [
        {"group": f'EVERY VOWEL IS "{v.upper()}"',
         "members": [w.upper() for w in words],
         "explanation": f"All vowels in each word are {v.upper()}",
         "type": "meta_same_vowel"}
        for v, words in pick_from_groups(groups, past, count)
    ]


def gen_keyboard(common, past, count):
    results = []
    for hand, keys, label in [("left", LEFT_HAND, "LEFT"), ("right", RIGHT_HAND, "RIGHT")]:
        candidates = sorted([w for w in common if typed_with(w, keys)], key=lambda w: -len(w))
        pool = candidates[:max(4, len(candidates) // 2)]
        for chunk in chunk_and_pick(pool, past, count):
            results.append({
                "group": f"TYPED WITH {label} HAND ONLY",
                "members": [w.upper() for w in chunk],
                "explanation": f"All letters on {hand} side of QWERTY",
                "type": f"meta_keyboard_{hand}"})
    return results[:count]


def gen_contains_number(common, past, count):
    groups = {num: [w for w in common if contains_sub(w, num)] for num in NUMBERS}
    return [
        {"group": f'CONTAINS "{num.upper()}"',
         "members": [w.upper() for w in words],
         "explanation": ", ".join(f"{w.upper()} hides {num.upper()}" for w in words),
         "type": "meta_number"}
        for num, words in pick_from_groups(groups, past, count)
    ]


def gen_doubles(common, past, count):
    candidates = [w for w in common if count_double_pairs(w) >= 2 and len(w) >= 5]
    results = []
    for chunk in chunk_and_pick(candidates, past, count):
        results.append({
            "group": "TWO SETS OF DOUBLE LETTERS",
            "members": [w.upper() for w in chunk],
            "explanation": ", ".join(w.upper() for w in chunk) + " — each has 2+ double-letter pairs",
            "type": "meta_doubles"})
    return results


def gen_alternating(common, past, count):
    candidates = [w for w in common if is_alternating(w)]
    results = []
    for chunk in chunk_and_pick(candidates, past, count):
        results.append({
            "group": "ALTERNATING VOWELS AND CONSONANTS",
            "members": [w.upper() for w in chunk],
            "explanation": "Every letter alternates V/C perfectly",
            "type": "meta_alternating"})
    return results


def gen_secret_split(common, past, count):
    splits = []
    for w in common:
        if len(w) < 6:
            continue
        for i in range(3, len(w) - 2):
            left, right = w[:i], w[i:]
            if left in common and right in common:
                splits.append((w, left, right))
                break
    results = []
    random.shuffle(splits)
    for i in range(0, len(splits) - 3, 4):
        if len(results) >= count:
            break
        picked = splits[i:i + 4]
        words = [s[0] for s in picked]
        if len(set(words)) == 4 and not is_dupe(words, past):
            results.append({
                "group": "SECRETLY TWO WORDS",
                "members": [w.upper() for w in words],
                "explanation": ", ".join(f"{w.upper()} = {l.upper()}+{r.upper()}" for w, l, r in picked),
                "type": "meta_split"})
    return results


def gen_chop_first(common, past, count):
    candidates = [(w, w[1:]) for w in common if len(w) >= 4 and w[1:] in common]
    results = []
    for chunk in chunk_and_pick(candidates, past, count):
        words = [w for w, _ in chunk]
        results.append({
            "group": "REMOVE FIRST LETTER = NEW WORD",
            "members": [w.upper() for w in words],
            "explanation": ", ".join(f"{w.upper()} -> {r.upper()}" for w, r in chunk),
            "type": "meta_chop_first"})
    return results


def gen_s_front(common, past, count):
    candidates = [(w, f"s{w}") for w in common
                  if len(w) >= 3 and f"s{w}" in common and not w.startswith("s")]
    results = []
    for chunk in chunk_and_pick(candidates, past, count):
        words = [w for w, _ in chunk]
        results.append({
            "group": 'ADD "S" TO THE FRONT = NEW WORD',
            "members": [w.upper() for w in words],
            "explanation": ", ".join(f"S+{w.upper()} = {sw.upper()}" for w, sw in chunk),
            "type": "meta_s_front"})
    return results


def gen_swap_ends(common, past, count):
    pairs = []
    seen = set()
    for w in common:
        if len(w) < 4:
            continue
        swapped = f"{w[-1]}{w[1:-1]}{w[0]}"
        if swapped in common and swapped != w:
            key = tuple(sorted([w, swapped]))
            if key not in seen:
                seen.add(key)
                pairs.append((w, swapped))
    results = []
    for chunk in chunk_and_pick(pairs, past, count):
        words = [a for a, _ in chunk]
        results.append({
            "group": "SWAP FIRST AND LAST LETTER = NEW WORD",
            "members": [w.upper() for w in words],
            "explanation": ", ".join(f"{a.upper()} <-> {b.upper()}" for a, b in chunk),
            "type": "meta_swap_ends"})
    return results


# ============================================================
# TIER 2: TWO-LAYER HIDDEN PATTERNS
# ============================================================

def build_hiding(common, mode):
    """Build map of short_word -> [long_words containing it]."""
    groups = defaultdict(list)
    for short in (w for w in common if 3 <= len(w) <= 5):
        for long in common:
            if long == short or len(long) < len(short) + 2:
                continue
            if mode == "start" and long.startswith(short):
                groups[short].append(long)
            elif mode == "end" and long.endswith(short):
                groups[short].append(long)
            elif mode == "inside":
                pos = long.find(short)
                if pos > 0 and pos + len(short) < len(long):
                    groups[short].append(long)
    return {k: v for k, v in groups.items() if v}


def gen_hidden_rhyme(hiding, past, w2p, count, mode):
    """4 words each hiding a DIFFERENT short word — those hidden words all rhyme."""
    by_rhyme = defaultdict(list)
    for short in hiding:
        rk = get_rhyme(short, w2p)
        if rk and len(rk.split()) >= 2:
            by_rhyme[rk].append(short)

    good = {k: v for k, v in by_rhyme.items() if len(v) >= 4}
    keys = list(good.keys())
    random.shuffle(keys)

    labels = {"start": "STARTING", "end": "ENDING", "inside": "HIDDEN IN"}
    results = []
    for rk in keys:
        if len(results) >= count:
            break
        shorts = list(good[rk])
        random.shuffle(shorts)

        picked, used_words = [], set()
        for short in shorts:
            avail = [w for w in hiding[short] if w not in used_words]
            if avail:
                chosen = random.choice(avail)
                picked.append((chosen, short))
                used_words.add(chosen)
            if len(picked) == 4:
                break

        if len(picked) == 4 and len(used_words) == 4:
            words = [p[0] for p in picked]
            if not is_dupe(words, past):
                hidden = [p[1] for p in picked]
                results.append({
                    "group": f"{labels[mode]} WORDS THAT RHYME",
                    "members": [w.upper() for w in words],
                    "explanation": (
                        ", ".join(f"{w.upper()} -> {h.upper()}" for w, h in picked)
                        + f" -- {', '.join(h.upper() for h in hidden)} all rhyme"
                    ),
                    "type": f"twolayer_rhyme_{mode}"})
    return results


def gen_hidden_drop(hiding, past, common, count, mode):
    """4 words each hiding a DIFFERENT short word — those all shrink to the SAME word."""
    drop_groups = defaultdict(list)
    for short in hiding:
        if len(short) < 4:
            continue
        for i in range(len(short)):
            shorter = f"{short[:i]}{short[i + 1:]}"
            if shorter in common:
                drop_groups[shorter].append(short)

    good = {k: list(set(v)) for k, v in drop_groups.items() if len(set(v)) >= 4}
    keys = list(good.keys())
    random.shuffle(keys)

    results = []
    for target in keys:
        if len(results) >= count:
            break
        shorts = good[target]
        random.shuffle(shorts)

        picked, used_words = [], set()
        for short in shorts:
            avail = [w for w in hiding.get(short, []) if w not in used_words]
            if avail:
                picked.append((random.choice(avail), short))
                used_words.add(picked[-1][0])
            if len(picked) == 4:
                break

        if len(picked) == 4 and len(used_words) == 4:
            words = [p[0] for p in picked]
            if not is_dupe(words, past):
                hidden = [p[1] for p in picked]
                results.append({
                    "group": f'HIDDEN WORDS SHRINK TO "{target.upper()}"',
                    "members": [w.upper() for w in words],
                    "explanation": (
                        ", ".join(f"{w.upper()} -> {h.upper()}" for w, h in picked)
                        + f' -- all become "{target.upper()}" minus a letter'
                    ),
                    "type": f"twolayer_drop_{mode}"})
    return results


# ============================================================
# TIER 3: INHERENTLY PURPLE
# ============================================================

def gen_compounds(common, past, count):
    results = []
    connectors = [w for w in common if 3 <= len(w) <= 7]
    random.shuffle(connectors)

    for conn in connectors[:2000]:
        if len(results) >= count:
            break
        for pattern, fmt_group in [
            (lambda w: f"{w}{conn}", f"___ {conn.upper()}"),
            (lambda w: f"{conn}{w}", f"{conn.upper()} ___"),
        ]:
            hits = [(w, pattern(w)) for w in common
                    if w != conn and len(w) >= 3 and pattern(w) in common]
            if len(hits) >= 4:
                picked = random.sample(hits, 4)
                words = [p[0] for p in picked]
                if not is_dupe(words, past):
                    results.append({
                        "group": fmt_group,
                        "members": [w.upper() for w in words],
                        "explanation": ", ".join(p[1].upper() for p in picked),
                        "type": "compound"})
                    break
    return results


def gen_reversals(common, past, count):
    rev_words = {w for w in common if len(w) >= 3 and w[::-1] in common and w[::-1] != w}
    pairs = [(w, w[::-1]) for w in rev_words if w < w[::-1]]
    results = []
    random.shuffle(pairs)
    for i in range(0, len(pairs) - 3, 4):
        if len(results) >= count:
            break
        chunk = pairs[i:i + 4]
        words = [random.choice([a, b]) for a, b in chunk]
        if len(set(words)) == 4 and not is_dupe(words, past):
            results.append({
                "group": "SPELLED BACKWARDS = ANOTHER WORD",
                "members": [w.upper() for w in words],
                "explanation": ", ".join(f"{w.upper()} <- {w[::-1].upper()}" for w in words),
                "type": "reversal"})
    return results


def gen_homophones(common, past, w2p, p2w, count):
    pairs = set()
    for w in common:
        for pron in w2p.get(w, []):
            for h in p2w.get(pron, []):
                if h != w and h in common:
                    pairs.add(tuple(sorted([w, h])))
    pairs = list(pairs)
    results = []
    random.shuffle(pairs)
    for i in range(0, len(pairs) - 3, 4):
        if len(results) >= count:
            break
        chunk = pairs[i:i + 4]
        words = [p[0] for p in chunk]
        if len(set(words)) == 4 and not is_dupe(words, past):
            results.append({
                "group": "EACH SOUNDS LIKE A DIFFERENT WORD",
                "members": [w.upper() for w in words],
                "explanation": ", ".join(f"{a.upper()} = {b.upper()}" for a, b in chunk),
                "type": "homophone"})
    return results


def gen_anagrams(common, past, count):
    by_letters = defaultdict(list)
    for w in common:
        by_letters["".join(sorted(w))].append(w)
    pairs = [pair for group in by_letters.values() if len(group) >= 2
             for pair in combinations(group, 2)]
    results = []
    random.shuffle(pairs)
    for i in range(0, len(pairs) - 3, 4):
        if len(results) >= count:
            break
        chunk = pairs[i:i + 4]
        words = [p[0] for p in chunk]
        if len(set(words)) == 4 and not is_dupe(words, past):
            results.append({
                "group": "EACH IS AN ANAGRAM OF ANOTHER WORD",
                "members": [w.upper() for w in words],
                "explanation": ", ".join(f"{a.upper()} <-> {b.upper()}" for a, b in chunk),
                "type": "anagram"})
    return results


def gen_letter_drop(common, past, count):
    groups = defaultdict(list)
    for w in common:
        if len(w) < 4:
            continue
        for shorter in {f"{w[:i]}{w[i + 1:]}" for i in range(len(w))}:
            if shorter in common:
                groups[shorter].append(w)
    return [
        {"group": f'EACH MINUS A LETTER = "{target.upper()}"',
         "members": [w.upper() for w in words],
         "explanation": ", ".join(f"{w.upper()} -> {target.upper()}" for w in words),
         "type": "letter_drop"}
        for target, words in pick_from_groups(groups, past, count)
    ]


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Generate 10K purple categories")
    parser.add_argument("--count", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--min-zipf", type=float, default=2.8)
    parser.add_argument("--output", default="purple_categories.json")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    print("Syncing puzzle data...")
    sync_repo()
    past = load_past()
    print(f"  {len(past)} past categories loaded")

    print("Collecting words from WordNet...")
    common = collect_common_wordnet_words(min_zipf=args.min_zipf)
    print(f"  Word pool: {len(common)} words")

    w2p, p2w = build_pron()
    print(f"  Pronunciation entries: {len(w2p)}")

    print("Building hiding maps...")
    hiding = {mode: build_hiding(common, mode) for mode in ["start", "end", "inside"]}
    for mode in hiding:
        print(f"  {mode}: {len(hiding[mode])} groups")

    # distribute target across generators
    per = args.count // 15 + 1
    big = args.count // 5 + 1

    print(f"\nGenerating categories (target: {args.count})...\n")
    all_results = []

    generators = [
        ("same vowel",        lambda: gen_same_vowel(common, past, per)),
        ("keyboard hand",     lambda: gen_keyboard(common, past, per)),
        ("hidden number",     lambda: gen_contains_number(common, past, per)),
        ("double letters",    lambda: gen_doubles(common, past, per)),
        ("alternating V/C",   lambda: gen_alternating(common, past, per)),
        ("secret split",      lambda: gen_secret_split(common, past, big)),
        ("chop first letter", lambda: gen_chop_first(common, past, big)),
        ("S + word",          lambda: gen_s_front(common, past, per)),
        ("swap first/last",   lambda: gen_swap_ends(common, past, per)),
        ("hidden+rhyme in",   lambda: gen_hidden_rhyme(hiding["inside"], past, w2p, big, "inside")),
        ("hidden+rhyme st",   lambda: gen_hidden_rhyme(hiding["start"], past, w2p, big, "start")),
        ("hidden+rhyme en",   lambda: gen_hidden_rhyme(hiding["end"], past, w2p, big, "end")),
        ("hidden+drop",       lambda: gen_hidden_drop(hiding["start"], past, common, per, "start")),
        ("compounds",         lambda: gen_compounds(common, past, big)),
        ("letter drop",       lambda: gen_letter_drop(common, past, big)),
        ("reversals",         lambda: gen_reversals(common, past, per)),
        ("homophones",        lambda: gen_homophones(common, past, w2p, p2w, big)),
        ("anagrams",          lambda: gen_anagrams(common, past, big)),
    ]

    for name, gen_fn in generators:
        results = gen_fn()
        all_results += results
        print(f"  {name:25s} {len(results):6d} categories")

    # deduplicate
    seen = set()
    unique = []
    for cat in all_results:
        key = tuple(sorted(m.upper() for m in cat["members"]))
        if key not in seen:
            seen.add(key)
            unique.append(cat)
    all_results = unique

    print(f"\n  Total unique: {len(all_results)}")
    if len(all_results) < args.count:
        print(f"  Warning: only {len(all_results)}/{args.count} — try --min-zipf 2.5")

    random.shuffle(all_results)
    all_results = all_results[:args.count]

    # sample output
    print(f"\nSample (first 10):")
    for i, g in enumerate(all_results[:10], 1):
        print(f"  [{i}] {g['group']}  ({g['type']})")
        print(f"      {', '.join(g['members'])}")

    # save
    with open(args.output, "w") as f:
        json.dump(all_results, f, indent=2)

    # stats
    type_counts = Counter(g["type"] for g in all_results)
    print(f"\nType distribution:")
    for t, n in type_counts.most_common():
        print(f"  {t:30s} {n:6d}")

    print(f"\nSaved {len(all_results)} categories to {args.output}")


if __name__ == "__main__":
    main()
