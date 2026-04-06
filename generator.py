from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


class PuzzleGenerator:
    def __init__(self, processed_path: str | Path, seed: Optional[int] = None) -> None:
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

    def generate_puzzle(self, max_tries: int = 200) -> Dict[str, Any]:
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

        raise ValueError("Could not build a valid 16-word puzzle after max_tries.")


if __name__ == "__main__":
    default_path = Path("processed_categories.json")
    generator = PuzzleGenerator(default_path)
    puzzle = generator.generate_puzzle()
    print(json.dumps(puzzle, indent=2))
