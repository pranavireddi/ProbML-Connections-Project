from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from checkPriorPuzzles import (
    compile_puzzle_answers,
    git_pull,
    is_valid_puzzle,
    load_answers,
)


class PuzzleGenerator:
    def __init__(
        self,
        processed_path: str | Path,
        seed: Optional[int] = None,
        prior_puzzles_repo: Optional[str | Path] = None,
        auto_check_duplicates: bool = True,
        refresh_repo_on_generate: bool = True,
    ) -> None:
        self.processed_path = Path(processed_path)
        with self.processed_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        self.metadata: Dict[str, Any] = payload.get("metadata", {})
        self.categories: List[Dict[str, Any]] = payload["categories"]
        self.neighbors: Dict[str, List[Dict[str, Any]]] = payload["neighbors"]
        self.rng = random.Random(seed)

        self.categories_by_color: Dict[str, List[Tuple[int, Dict[str, Any]]]] = {
            color: [] for color in ["yellow", "green", "blue", "purple"]
        }
        for idx, cat in enumerate(self.categories):
            color = cat["color"]
            if color in self.categories_by_color:
                self.categories_by_color[color].append((idx, cat))

        self.auto_check_duplicates = auto_check_duplicates
        self.refresh_repo_on_generate = refresh_repo_on_generate
        repo_from_env = os.environ.get("NYT_CONNECTIONS_ANSWERS_REPO")
        self.prior_puzzles_repo = (
            Path(prior_puzzles_repo).expanduser().resolve()
            if prior_puzzles_repo is not None
            else (Path(repo_from_env).expanduser().resolve() if repo_from_env else None)
        )
        self._prior_puzzle_signatures: Set[str] = set()

    @staticmethod
    def _norm(word: Any) -> str:
        return str(word).strip().upper()

    def _word_set(self, cat: Dict[str, Any]) -> Set[str]:
        return {self._norm(w) for w in cat["members"]}

    def _valid_16_words(self, groups: Sequence[Dict[str, Any]]) -> bool:
        words: List[str] = []
        for cat in groups:
            words.extend(self._norm(w) for w in cat["members"])
        return len(words) == 16 and len(set(words)) == 16

    def _choose_random_from_color(
        self,
        color: str,
        used_word_set: Set[str],
        exclude_indices: Optional[Set[int]] = None,
        max_attempts: int = 50,
    ) -> Optional[Tuple[int, Dict[str, Any]]]:
        exclude_indices = exclude_indices or set()
        pool = [(idx, cat) for idx, cat in self.categories_by_color.get(color, []) if idx not in exclude_indices]
        if not pool:
            return None

        self.rng.shuffle(pool)
        for idx, cat in pool[:max_attempts]:
            if self._word_set(cat).isdisjoint(used_word_set):
                return idx, cat
        return None

    def _choose_neighbor(
        self,
        source_index: int,
        used_word_set: Set[str],
        exclude_colors: Optional[Set[str]] = None,
    ) -> Optional[Tuple[int, Dict[str, Any], float]]:
        exclude_colors = exclude_colors or set()
        for entry in self.neighbors.get(str(source_index), []):
            idx = entry["index"]
            cat = self.categories[idx]
            if cat["color"] in exclude_colors:
                continue
            if self._word_set(cat).isdisjoint(used_word_set):
                return idx, cat, float(entry["similarity"])
        return None

    def _load_prior_puzzle_signatures(self) -> Set[str]:
        if not self.prior_puzzles_repo:
            raise ValueError(
                "Duplicate checking is enabled, but no prior-puzzle repo was provided. "
                "Pass prior_puzzles_repo=... or set NYT_CONNECTIONS_ANSWERS_REPO."
            )

        repo_path = self.prior_puzzles_repo
        if not repo_path.is_dir():
            raise ValueError(f"Prior-puzzle repo directory not found: {repo_path}")

        if self.refresh_repo_on_generate:
            git_pull(str(repo_path))

        data_path = repo_path / "connections.json"
        if not data_path.is_file():
            raise ValueError(f"connections.json not found in repo: {data_path}")

        puzzles = load_answers(str(data_path))
        signatures: Set[str] = set()
        for puz in puzzles:
            if is_valid_puzzle(puz):
                signatures.add(compile_puzzle_answers(puz))
        return signatures

    def _refresh_prior_puzzle_index(self) -> None:
        if self.auto_check_duplicates:
            self._prior_puzzle_signatures = self._load_prior_puzzle_signatures()
        else:
            self._prior_puzzle_signatures = set()

    def _puzzle_signature(self, groups: Sequence[Dict[str, Any]]) -> str:
        puzzle_like = {
            "answers": [
                {
                    "members": [self._norm(w) for w in cat["members"]],
                }
                for cat in groups
            ]
        }
        return compile_puzzle_answers(puzzle_like)

    def _is_duplicate_puzzle(self, groups: Sequence[Dict[str, Any]]) -> bool:
        if not self.auto_check_duplicates:
            return False
        return self._puzzle_signature(groups) in self._prior_puzzle_signatures

    def generate_puzzle(self, max_tries: int = 200) -> Dict[str, Any]:
        self._refresh_prior_puzzle_index()

        purple_pool = self.categories_by_color.get("purple", [])
        if not purple_pool:
            raise ValueError("No purple categories available in processed data.")

        for _ in range(max_tries):
            purple_idx, purple_cat = self.rng.choice(purple_pool)
            used_words = set(self._word_set(purple_cat))

            neighbor_result = self._choose_neighbor(purple_idx, used_words)
            if neighbor_result is None:
                continue
            neighbor_idx, neighbor_cat, neighbor_similarity = neighbor_result
            used_words |= self._word_set(neighbor_cat)

            remaining_colors = [c for c in ["yellow", "green", "blue"] if c != neighbor_cat["color"]]
            if len(remaining_colors) != 2:
                continue

            selected: List[Tuple[int, Dict[str, Any]]] = [(purple_idx, purple_cat), (neighbor_idx, neighbor_cat)]
            valid = True
            for color in remaining_colors:
                pick = self._choose_random_from_color(
                    color,
                    used_words,
                    exclude_indices={purple_idx, neighbor_idx},
                )
                if pick is None:
                    valid = False
                    break
                idx, cat = pick
                used_words |= self._word_set(cat)
                selected.append((idx, cat))

            if not valid:
                continue

            groups = [cat for _, cat in selected]
            if not self._valid_16_words(groups):
                continue
            if self._is_duplicate_puzzle(groups):
                continue

            board: List[str] = []
            for cat in groups:
                board.extend(self._norm(w) for w in cat["members"])
            self.rng.shuffle(board)

            return {
                "board": board,
                "groups": [
                    {
                        "color": cat["color"],
                        "group": cat["group"],
                        "members": [self._norm(w) for w in cat["members"]],
                        "cat_type": cat.get("cat_type", ""),
                        "explanation": cat.get("explanation", ""),
                        "source_index": cat.get("source_index", -1),
                    }
                    for cat in groups
                ],
                "purple_query_group": purple_cat["group"],
                "neighbor_group": neighbor_cat["group"],
                "neighbor_color": neighbor_cat["color"],
                "neighbor_similarity": neighbor_similarity,
            }

        if self.auto_check_duplicates:
            raise ValueError(
                "Could not build a valid 16-word puzzle with no prior match after max_tries."
            )
        raise ValueError("Could not build a valid 16-word puzzle after max_tries.")


if __name__ == "__main__":
    default_path = Path("processed_categories.json")
    generator = PuzzleGenerator(default_path)
    puzzle = generator.generate_puzzle()
    print(json.dumps(puzzle, indent=2))
