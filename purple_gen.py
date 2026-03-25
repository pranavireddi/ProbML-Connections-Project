#!/usr/bin/env python3

# Purple Connections Generator
#
# Rules:
#   1. Two-layer categories required: hidden words must DIFFER and share a second pattern
#   2. Compound/anagram/homophone/reversal are inherently purple-level
#   3. Prefer high-misdirection words (ones that look like they belong elsewhere)
#
# pip install pronouncing
# python purple_gen.py
# python purple_gen.py --seed 42 --count 5

import json, os, random, subprocess, argparse
from collections import defaultdict
import pronouncing

REPO_URL = "https://github.com/Eyefyre/NYT-Connections-Answers.git"
REPO_DIR = "NYT-Connections-Answers"
DATA_FILE = os.path.join(REPO_DIR, "connections.json")


# ---- setup ----

def sync_repo():
    if os.path.isdir(REPO_DIR):
        subprocess.run(["git", "-C", REPO_DIR, "pull", "--ff-only"],
                       capture_output=True, text=True)
    else:
        result = subprocess.run(["git", "clone", REPO_URL, "--depth", "1"],
                                capture_output=True, text=True)
        if result.returncode != 0:
            return False
    return True

def load_words(filepath):
    words = set()
    with open(filepath) as f:
        for line in f:
            w = line.strip().lower()
            if w: words.add(w)
    return words

def load_past():
    past = set()
    with open(DATA_FILE) as f:
        for puzzle in json.load(f):
            for answer in puzzle["answers"]:
                past.add(tuple(sorted(m.upper() for m in answer["members"])))
    return past

def is_dupe(words, past):
    return tuple(sorted(w.upper() for w in words)) in past

def make(group, words, explanation, gen_type):
    return {"group": group, "members": [w.upper() for w in words],
            "explanation": explanation, "type": gen_type}

def build_pron():
    pronouncing.init_cmu()
    w2p, p2w = defaultdict(list), defaultdict(list)
    for word, pron in pronouncing.pronunciations:
        c = word.lower().strip("()")
        if c.isalpha():
            w2p[c].append(pron)
            p2w[pron].append(c)
    return w2p, p2w

def rhyme_key(pron):
    phones = pron.split()
    for i in range(len(phones) - 1, -1, -1):
        if any(ch.isdigit() for ch in phones[i]):
            return " ".join(phones[i:])
    return pron

def get_rhyme_key(word, w2p):
    for pron in w2p.get(word, []):
        return rhyme_key(pron)
    return None


# ---- hiding maps + misdirection ----

def build_hiding_maps(common):
    starts, ends, inside = defaultdict(list), defaultdict(list), defaultdict(list)
    shorts = [w for w in common if 3 <= len(w) <= 5]
    for short in shorts:
        for long in common:
            if long == short or len(long) < len(short) + 2:
                continue
            if long.startswith(short):
                starts[short].append(long)
            if long.endswith(short):
                ends[short].append(long)
            pos = long.find(short)
            if pos > 0 and pos + len(short) < len(long):
                inside[short].append(long)
    return (
        {k: v for k, v in starts.items() if v},
        {k: v for k, v in ends.items() if v},
        {k: v for k, v in inside.items() if v},
    )

def build_misdirection(starts, ends, inside):
    """Words in more pools = more deceptive = better purple candidates."""
    scores = defaultdict(int)
    for mapping in [starts, ends, inside]:
        for short, longs in mapping.items():
            for l in longs:
                scores[l] += 1
    return scores

def pick_deceptive(candidates, scores, n=4):
    """Pick n words preferring high misdirection scores."""
    scored = sorted(candidates, key=lambda w: -scores.get(w, 0))
    pool = scored[:max(n, int(len(scored) * 0.6))]
    if len(pool) < n:
        return None
    return random.sample(pool, n)



def gen_hidden_rhyming(hiding_map, past, w2p, scores, count, mode):
    """
    Each word hides a DIFFERENT short word, but those hidden words all RHYME.
    Example (inside): TOOTHPASTE, SANDCASTLE, RINGMASTER, ELASTIC
      → hidden: PAST, CAST, MAST, LAST → all rhyme!
    """
    rhyme_groups = defaultdict(list)
    for short in hiding_map:
        rk = get_rhyme_key(short, w2p)
        if rk and len(rk.split()) >= 2:
            rhyme_groups[rk].append(short)

    good = {k: v for k, v in rhyme_groups.items() if len(v) >= 4}
    results = []
    keys = list(good.keys())
    random.shuffle(keys)

    for rk in keys:
        if len(results) >= count:
            break
        shorts = list(good[rk])
        random.shuffle(shorts)

        picked = []
        used = set()
        used_words = set()  # also track answer words to avoid picking the same long word twice
        for short in shorts:
            if short in used:
                continue
            candidates = [w for w in hiding_map[short] if w not in used_words]
            best = pick_deceptive(candidates, scores, 1) if candidates else None
            if best:
                picked.append((best[0], short))
                used.add(short)
                used_words.add(best[0])
            if len(picked) == 4:
                break

        if len(picked) == 4:
            words = [p[0] for p in picked]
            # final check: all 4 answer words must be different
            if len(set(words)) == 4 and not is_dupe(words, past):
                hidden = [p[1] for p in picked]
                mode_label = {"start": "STARTING", "end": "ENDING", "inside": "HIDDEN IN"}
                why = ", ".join(f"{w.upper()} → {h.upper()}" for w, h in picked)
                why += f" — {', '.join(h.upper() for h in hidden)} all rhyme"
                results.append(make(
                    f"{mode_label[mode]} WORDS THAT RHYME",
                    words, why, f"two_layer_rhyme_{mode}"))
    return results


def gen_hidden_drop_same(hiding_map, past, common, scores, count, mode):
    """
    Each word hides a DIFFERENT short word, and those all become the SAME word
    when you drop one letter.
    Example (start): LINEAR, LIVESTOCK, LIMESTONE, LIFESPAN
      → hidden: LINE, LIVE, LIME, LIFE → all become LIE!
    """
    drop_groups = defaultdict(list)
    for short in hiding_map:
        if len(short) < 4:
            continue
        for i in range(len(short)):
            shorter = short[:i] + short[i+1:]
            if shorter in common:
                drop_groups[shorter].append(short)

    good = {k: list(set(v)) for k, v in drop_groups.items() if len(set(v)) >= 4}
    results = []
    keys = list(good.keys())
    random.shuffle(keys)

    for target in keys:
        if len(results) >= count:
            break
        shorts = good[target]
        random.shuffle(shorts)

        picked = []
        used = set()
        used_words = set()
        for short in shorts:
            if short in used:
                continue
            longs = [w for w in hiding_map.get(short, []) if w not in used_words]
            if not longs:
                continue
            best = pick_deceptive(longs, scores, 1)
            if best:
                picked.append((best[0], short))
                used.add(short)
                used_words.add(best[0])
            if len(picked) == 4:
                break

        if len(picked) == 4:
            words = [p[0] for p in picked]
            if len(set(words)) == 4 and not is_dupe(words, past):
                hidden = [p[1] for p in picked]
                why = ", ".join(f"{w.upper()} → {h.upper()}" for w, h in picked)
                why += f" — all become \"{target.upper()}\" minus a letter"
                results.append(make(
                    f"HIDDEN WORDS MINUS A LETTER = \"{target.upper()}\"",
                    words, why, f"two_layer_drop_{mode}"))
    return results


def gen_hidden_same_length(hiding_map, past, scores, count, mode):
    """
    Each word hides a DIFFERENT short word, all the SAME length.
    Weaker than rhyme/drop but still two-layer since solver has to extract
    the hidden words and notice they're the same length.
    Only included if hidden words are varied enough to not be obvious.
    """
    len_groups = defaultdict(list)
    for short in hiding_map:
        len_groups[len(short)].append(short)

    results = []
    for length in [4, 5]:  # 3-letter is too easy/common
        shorts = len_groups.get(length, [])
        if len(shorts) < 4:
            continue
        random.shuffle(shorts)

        picked = []
        used = set()
        used_words = set()
        for short in shorts:
            if short in used:
                continue
            candidates = [w for w in hiding_map[short] if w not in used_words]
            best = pick_deceptive(candidates, scores, 1) if candidates else None
            if best:
                picked.append((best[0], short))
                used.add(short)
                used_words.add(best[0])
            if len(picked) == 4:
                break

        if len(picked) == 4 and len(results) < count:
            words = [p[0] for p in picked]
            if len(set(words)) == 4 and not is_dupe(words, past):
                hidden = [p[1] for p in picked]
                # only keep if the hidden words are all DIFFERENT (no repeats)
                if len(set(hidden)) == 4:
                    why = ", ".join(f"{w.upper()} → {h.upper()}" for w, h in picked)
                    why += f" — all hidden words are {length} letters"
                    mode_label = {"start": "STARTING", "end": "ENDING", "inside": "HIDDEN IN"}
                    results.append(make(
                        f"{mode_label[mode]} {length}-LETTER WORDS",
                        words, why, f"two_layer_length_{mode}"))
    return results




def gen_compounds(common, past, count):
    """___ WORD or WORD ___ — the #1 purple pattern in real NYT data (34%)."""
    results = []
    connectors = [w for w in common if 3 <= len(w) <= 7]
    random.shuffle(connectors)

    for connector in connectors[:600]:
        if len(results) >= count:
            break

        hits = [(w, w + connector) for w in common
                if w != connector and len(w) >= 3 and w + connector in common]
        if len(hits) >= 4:
            picked = random.sample(hits, 4)
            words = [p[0] for p in picked]
            if not is_dupe(words, past):
                results.append(make("___ " + connector.upper(), words,
                    ", ".join(p[1].upper() for p in picked), "compound"))
                continue

        hits = [(w, connector + w) for w in common
                if w != connector and len(w) >= 3 and connector + w in common]
        if len(hits) >= 4:
            picked = random.sample(hits, 4)
            words = [p[0] for p in picked]
            if not is_dupe(words, past):
                results.append(make(connector.upper() + " ___", words,
                    ", ".join(p[1].upper() for p in picked), "compound"))
    return results


def gen_reversals(common, past, count):
    """Spell it backwards, get another word. Inherently non-obvious."""
    pairs = []
    seen = set()
    for w in common:
        rev = w[::-1]
        if rev in common and rev != w and len(w) >= 3:
            key = tuple(sorted([w, rev]))
            if key not in seen:
                seen.add(key)
                pairs.append((w, rev))

    results = []
    if len(pairs) >= 4:
        random.shuffle(pairs)
        words, expl = [], []
        for a, b in pairs[:4]:
            if random.random() < 0.5: a, b = b, a
            words.append(a)
            expl.append(f"{a.upper()} ← {b.upper()}")
        if not is_dupe(words, past):
            results.append(make("SPELLED BACKWARDS = ANOTHER WORD",
                words, ", ".join(expl), "reversal"))
    return results


def gen_homophones(common, past, w2p, p2w, count):
    """Sounds like a different word. Requires pronunciation knowledge."""
    pairs = []
    seen = set()
    for w in common:
        for pron in w2p.get(w, []):
            for h in p2w.get(pron, []):
                if h != w and h in common:
                    key = tuple(sorted([w, h]))
                    if key not in seen:
                        seen.add(key)
                        pairs.append((w, h))

    results = []
    if len(pairs) >= 4:
        random.shuffle(pairs)
        words = [p[0] for p in pairs[:4]]
        expl = [f"{a.upper()} = {b.upper()}" for a, b in pairs[:4]]
        if not is_dupe(words, past):
            results.append(make("EACH SOUNDS LIKE A DIFFERENT WORD",
                words, ", ".join(expl), "homophone"))
    return results


def gen_anagrams(common, past, count):
    """Rearrange letters to get another word. Requires letter-level insight."""
    groups = defaultdict(list)
    for w in common:
        groups["".join(sorted(w))].append(w)

    pairs = []
    for g in groups.values():
        if len(g) >= 2:
            for i in range(len(g)):
                for j in range(i + 1, len(g)):
                    pairs.append((g[i], g[j]))

    results = []
    if len(pairs) >= 4:
        random.shuffle(pairs)
        words = [p[0] for p in pairs[:4]]
        expl = [f"{a.upper()} ↔ {b.upper()}" for a, b in pairs[:4]]
        if not is_dupe(words, past):
            results.append(make("EACH IS AN ANAGRAM OF ANOTHER WORD",
                words, ", ".join(expl), "anagram"))
    return results


def gen_letter_drop(common, past, count):
    """Remove one letter from each, all become the same word."""
    groups = defaultdict(list)
    for w in common:
        if len(w) < 4:
            continue
        seen = set()
        for i in range(len(w)):
            shorter = w[:i] + w[i+1:]
            if shorter in common and shorter not in seen:
                seen.add(shorter)
                groups[shorter].append(w)

    good = {k: v for k, v in groups.items() if len(v) >= 4}
    results = []
    keys = list(good.keys())
    random.shuffle(keys)

    for target in keys:
        if len(results) >= count:
            break
        picked = random.sample(good[target], 4)
        if not is_dupe(picked, past):
            why = ", ".join(f"{w.upper()} → {target.upper()}" for w in picked)
            results.append(make(f"EACH MINUS A LETTER = \"{target.upper()}\"",
                picked, why, "letter_drop"))
    return results


def gen_word_ladder(common, past, count):
    """
    4 words that each differ from an invisible TARGET by exactly one letter,
    each at a DIFFERENT position. The solver has to figure out the target.
    """
    groups = defaultdict(set)
    for w in common:
        if not (3 <= len(w) <= 7):
            continue
        for i in range(len(w)):
            for c in "abcdefghijklmnopqrstuvwxyz":
                if c == w[i]:
                    continue
                swapped = w[:i] + c + w[i+1:]
                if swapped in common and swapped != w:
                    groups[swapped].add(w)

    good = {k: list(v) for k, v in groups.items() if len(v) >= 6}
    results = []
    keys = list(good.keys())
    random.shuffle(keys)

    for target in keys:
        if len(results) >= count:
            break
        candidates = list(good[target])
        random.shuffle(candidates)

        # pick 4 changing DIFFERENT positions
        used_pos = set()
        picked = []
        for w in candidates:
            for i in range(min(len(w), len(target))):
                if w[i] != target[i]:
                    if i not in used_pos:
                        picked.append(w)
                        used_pos.add(i)
                    break
            if len(picked) == 4:
                break

        if len(picked) == 4 and not is_dupe(picked, past):
            why = ", ".join(f"{w.upper()} → {target.upper()}" for w in picked)
            results.append(make(f"EACH ONE LETTER FROM \"{target.upper()}\"",
                picked, why, "word_ladder"))
    return results


# ---- main ----

def main():
    parser = argparse.ArgumentParser(description="Authentic purple-only Connections generator")
    parser.add_argument("--words", default="words.txt", help="Path to word list")
    parser.add_argument("--count", type=int, default=3, help="How many per generator")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    if not sync_repo() and not os.path.isfile(DATA_FILE):
        print("No puzzle data. Run: git clone " + REPO_URL)
        return

    common = load_words(args.words)
    past = load_past()
    w2p, p2w = build_pron()
    starts, ends, inside = build_hiding_maps(common)
    scores = build_misdirection(starts, ends, inside)

    results = []

    results += gen_hidden_rhyming(inside, past, w2p, scores, args.count, "inside")
    results += gen_hidden_rhyming(starts, past, w2p, scores, args.count, "start")
    results += gen_hidden_rhyming(ends, past, w2p, scores, args.count, "end")
    results += gen_hidden_drop_same(starts, past, common, scores, args.count, "start")
    results += gen_hidden_same_length(inside, past, scores, args.count, "inside")

    results += gen_compounds(common, past, args.count)
    results += gen_letter_drop(common, past, args.count)
    results += gen_word_ladder(common, past, args.count)
    results += gen_reversals(common, past, args.count)
    results += gen_homophones(common, past, w2p, p2w, args.count)
    results += gen_anagrams(common, past, args.count)

    for i, g in enumerate(results, 1):
        print(f"[{i}] {g['group']}  ({g['type']})")
        print(f"    {', '.join(g['members'])}")
        print(f"    {g['explanation']}\n")

    with open("purple_output.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
