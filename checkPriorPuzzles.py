#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

##NOTE: To run this checker, here is a sample command. you need to have the repo for the answers to the connections
# puzzles cloned locally first, though. 
# Sample command: python3 checkPriorPuzzles.py \
#   --repo NYT-Connections-Answers \
#   --words "Hail,rain,sleet,snow,bucks,heat,jazz,nets,option,return,shift,tab,kayak,level,mom,lol"
# Also, note that the puzzle you are checking against needs to be 16 comma-separated words encased in quotes.

#NOTE: this is to normalize all the input words in case they're formatted weirdly
def normalize_words(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = " ".join(s.strip().split())
    return s.lower()


def is_valid_puzzle(puz: Dict[str, Any]) -> bool:
    answers = puz.get("answers")
    if not isinstance(answers, list) or len(answers) != 4:
        return False
    
    total = 0
    for a in answers:
        if not isinstance(a, dict):
            return False
        members = a.get("members")
        if not isinstance(members, list) or len(members) != 4:
            return False
        total += len(members)
        
    return total == 16


def compile_puzzle_answers(puz: Dict[str, Any]) -> str:
    words = []
    
    #NOTE: this is based on the structure of the connections answers in the git repo
    for ans in puz.get("answers", []):
        for m in ans.get("members", []):
            words.append(normalize_words(str(m)))
            
    words.sort()
    
    return ",".join(words)

#NOTE: need to re-pull form repo bc it updates everyday with neww puzzle results, and we need that to mkae sure our checker is always up to date
def git_pull(repo_path: str, verbose: bool = False) -> None:
    cmd = ["git", "-C", repo_path, "pull", "--ff-only"]
    if verbose:
        print(f"[info] {' '.join(cmd)}", file=sys.stderr)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("[warn] git pull failed; using local repo state.", file=sys.stderr)
        if verbose:
            print(res.stdout, file=sys.stderr)
            print(res.stderr, file=sys.stderr)


def load_answers(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        # fallback: sometimes lists are nested in a dict field
        for v in data.values():
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                return v
        return [data]
    return []

#NOTE: create ways to index puzzles in a clean way
@dataclass(frozen=True)
class MatchInfo:
    date: Optional[str]
    puzzle_id: Optional[Any]

#NOTE: this is for the puzzle we create that we wanna cross-check against the prev puzzle
def parse_input_words(words_arg: Optional[str]) -> List[str]:
    raw = (words_arg or "").strip()
    
    if not raw:
        if sys.stdin.isatty():
            return []
        raw = sys.stdin.read().strip()
    if not raw:
        return []
    
    #NOTE: need to pass in the 16 words for our puzzle as comma-separated words
    return [t.strip() for t in raw.split(",") if t.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="Path to cloned repo")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--words", help="16 comma-separated words")
    args = ap.parse_args()

    repo_path = os.path.abspath(args.repo)
    if not os.path.isdir(repo_path):
        print(f"Repo dir not found: {repo_path}", file=sys.stderr)
        return 2

    git_pull(repo_path, verbose=args.verbose)

    answers_file_path = "connections.json"
    if not os.path.isabs(answers_file_path):
        data_path = os.path.join(repo_path, answers_file_path)
    if not os.path.isfile(data_path):
        print(f"Data file not found: {data_path}", file=sys.stderr)
        return 2

    puzzles = load_answers(data_path)
    if args.verbose:
        print(f"[info] loaded {len(puzzles)} objects from {data_path}", file=sys.stderr)

    # Build index: signature -> list of matches (in case duplicates ever exist)
    index: Dict[str, List[MatchInfo]] = {}
    valid = 0
    for puz in puzzles:
        if not is_valid_puzzle(puz):
            continue
        puzzKey = compile_puzzle_answers(puz)
        index.setdefault(puzzKey, []).append(
            MatchInfo(
                date=str(puz.get("date")) if puz.get("date") is not None else None,
                puzzle_id=puz.get("id"),
            )
        )
        valid += 1

    if args.verbose:
        print(f"[info] indexed {valid} valid puzzles", file=sys.stderr)

    words = parse_input_words(args.words)
    if len(words) != 16:
        print(f"Expected 16 words, got {len(words)}", file=sys.stderr)
        return 2

    input_sig = ",".join(sorted(normalize_words(w) for w in words))

    matches = index.get(input_sig, [])
    if not matches:
        print("NO MATCH")
        return 1

    print(f"MATCHES: {len(matches)}")
    for m in sorted(matches, key=lambda x: (x.date or "", str(x.puzzle_id or ""))):
        print(f"- date={m.date} id={m.puzzle_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())