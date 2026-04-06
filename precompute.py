from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from sentence_transformers import SentenceTransformer


# ------------------------------
# data model
# ------------------------------

@dataclass
class Category:
    color: str
    group: str
    members: List[str]
    cat_type: str = ""
    explanation: str = ""
    source_index: int = -1
    hybrid_vec: Optional[List[float]] = None


# ------------------------------
# helpers
# ------------------------------


def norm_text(value: Any) -> str:
    return str(value).strip().upper()



def normalize_vec(vec: np.ndarray) -> np.ndarray:
    vec = np.asarray(vec, dtype=np.float32)
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm



def centroid(vecs: List[np.ndarray]) -> np.ndarray:
    if not vecs:
        raise ValueError("Cannot compute centroid of empty list.")
    mean_vec = np.mean(np.stack(vecs), axis=0)
    return normalize_vec(mean_vec)



def embed_texts(model: SentenceTransformer, texts: List[str]) -> List[np.ndarray]:
    arr = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [np.asarray(v, dtype=np.float32) for v in arr]


# ------------------------------
# schema-aware loading
# ------------------------------


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)



def _category_from_yellow(item: Dict[str, Any], idx: int) -> Optional[Category]:
    category = item.get("category")
    words = item.get("words", [])
    if not category or not isinstance(words, list) or len(words) != 4:
        return None
    return Category(
        color="yellow",
        group=norm_text(category),
        members=[norm_text(w) for w in words],
        cat_type=norm_text(item.get("difficulty", "yellow")),
        explanation="",
        source_index=item.get("id", idx),
    )



def _category_from_green(item: Dict[str, Any], idx: int) -> Optional[Category]:
    # Tries a few common schema variants.
    group = item.get("group") or item.get("category") or item.get("label") or item.get("title")
    words = item.get("members") or item.get("words") or item.get("items")
    if not group or not isinstance(words, list) or len(words) != 4:
        return None
    return Category(
        color="green",
        group=norm_text(group),
        members=[norm_text(w) for w in words],
        cat_type=norm_text(item.get("type", item.get("difficulty", "green"))),
        explanation=item.get("explanation", "") or "",
        source_index=item.get("id", idx),
    )



def _category_from_blue(item: Dict[str, Any], idx: int) -> Optional[Category]:
    group = item.get("group") or item.get("category") or item.get("label") or item.get("title")
    words = item.get("members") or item.get("words") or item.get("items")
    if not group or not isinstance(words, list) or len(words) != 4:
        return None
    return Category(
        color="blue",
        group=norm_text(group),
        members=[norm_text(w) for w in words],
        cat_type=norm_text(item.get("type", item.get("difficulty", "blue"))),
        explanation=item.get("explanation", "") or "",
        source_index=item.get("id", idx),
    )



def _category_from_purple(item: Dict[str, Any], idx: int) -> Optional[Category]:
    group = item.get("group") or item.get("category") or item.get("label") or item.get("title")
    words = item.get("members") or item.get("words") or item.get("items")
    if not group or not isinstance(words, list) or len(words) != 4:
        return None
    return Category(
        color="purple",
        group=norm_text(group),
        members=[norm_text(w) for w in words],
        cat_type=norm_text(item.get("type", item.get("difficulty", "purple"))),
        explanation=item.get("explanation", "") or "",
        source_index=item.get("id", idx),
    )



def load_categories_schema_aware(path: Path, color: str) -> List[Category]:
    raw = _load_json(path)
    if not isinstance(raw, list):
        raise ValueError(f"Expected a list in {path}, got {type(raw).__name__}.")

    parser_map = {
        "yellow": _category_from_yellow,
        "green": _category_from_green,
        "blue": _category_from_blue,
        "purple": _category_from_purple,
    }
    if color not in parser_map:
        raise ValueError(f"Unsupported color: {color}")

    parser = parser_map[color]
    out: List[Category] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        cat = parser(item, idx)
        if cat is None:
            continue
        # Keep only fully unique 4-word groups.
        if len(cat.members) == 4 and len(set(cat.members)) == 4:
            out.append(cat)
    return out


# ------------------------------
# precompute
# ------------------------------


def sample_categories(cats: List[Category], n: Optional[int], rng: random.Random) -> List[Category]:
    if n is None or n <= 0 or n >= len(cats):
        return list(cats)
    return rng.sample(cats, n)



def preprocess_categories(model: SentenceTransformer, cats: List[Category]) -> None:
    if not cats:
        return

    label_texts = [c.group for c in cats]
    combo_texts = [f"{c.group}: {', '.join(c.members)}" for c in cats]

    label_vecs = embed_texts(model, label_texts)
    combo_vecs = embed_texts(model, combo_texts)

    # Member words are embedded category-by-category so we can keep the 4-word structure.
    for i, cat in enumerate(cats):
        member_vecs = embed_texts(model, cat.members)
        member_centroid = centroid(member_vecs)

        weighted = centroid(
            [
                0.55 * combo_vecs[i],
                0.30 * member_centroid,
                0.15 * label_vecs[i],
            ]
        )
        cat.hybrid_vec = weighted.astype(np.float32).tolist()



def compute_cross_color_neighbors(cats: List[Category], top_k: int = 10) -> Dict[str, List[Dict[str, Any]]]:
    vectors = [np.asarray(c.hybrid_vec, dtype=np.float32) for c in cats]
    neighbor_map: Dict[str, List[Dict[str, Any]]] = {}

    for i, src in enumerate(cats):
        scored: List[Dict[str, Any]] = []
        for j, dst in enumerate(cats):
            if i == j or src.color == dst.color:
                continue
            sim = float(np.dot(vectors[i], vectors[j]))
            scored.append(
                {
                    "index": j,
                    "color": dst.color,
                    "group": dst.group,
                    "members": dst.members,
                    "similarity": sim,
                }
            )
        scored.sort(key=lambda x: x["similarity"], reverse=True)
        neighbor_map[str(i)] = scored[:top_k]

    return neighbor_map



def categories_to_records(cats: List[Category]) -> List[Dict[str, Any]]:
    return [asdict(c) for c in cats]



def save_processed(output_path: Path, cats: List[Category], neighbors: Dict[str, List[Dict[str, Any]]], metadata: Dict[str, Any]) -> None:
    payload = {
        "metadata": metadata,
        "categories": categories_to_records(cats),
        "neighbors": neighbors,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f)



def main() -> None:
    parser = argparse.ArgumentParser(description="Precompute processed category data and neighbor lists.")
    parser.add_argument("--yellow", required=True, help="Path to yellow JSON file")
    parser.add_argument("--green", required=True, help="Path to green JSON file")
    parser.add_argument("--blue", required=True, help="Path to blue JSON file")
    parser.add_argument("--purple", required=True, help="Path to purple JSON file")
    parser.add_argument("--output", default="processed/processed_categories.json", help="Output JSON path")
    parser.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2", help="SentenceTransformer model name")
    parser.add_argument("--sample-per-color", type=int, default=200, help="How many categories to sample per color; use <=0 for all")
    parser.add_argument("--top-k", type=int, default=10, help="How many cross-color neighbors to store per category")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    yellow = load_categories_schema_aware(Path(args.yellow), "yellow")
    green = load_categories_schema_aware(Path(args.green), "green")
    blue = load_categories_schema_aware(Path(args.blue), "blue")
    purple = load_categories_schema_aware(Path(args.purple), "purple")

    trial_cats = (
        sample_categories(yellow, args.sample_per_color, rng)
        + sample_categories(green, args.sample_per_color, rng)
        + sample_categories(blue, args.sample_per_color, rng)
        + sample_categories(purple, args.sample_per_color, rng)
    )

    model = SentenceTransformer(args.model)
    preprocess_categories(model, trial_cats)
    neighbors = compute_cross_color_neighbors(trial_cats, top_k=args.top_k)

    metadata = {
        "model_name": args.model,
        "sample_per_color": args.sample_per_color,
        "top_k": args.top_k,
        "seed": args.seed,
        "counts": {
            "yellow": len(yellow),
            "green": len(green),
            "blue": len(blue),
            "purple": len(purple),
            "trial_total": len(trial_cats),
        },
    }
    save_processed(Path(args.output), trial_cats, neighbors, metadata)

    print(f"Saved processed data to {args.output}")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
