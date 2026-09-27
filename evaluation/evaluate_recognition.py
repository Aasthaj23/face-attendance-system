"""Evaluate face recognition against known and unknown image samples.

Dataset layout:
    evaluation/dataset/known/<student-name>/*.jpg
    evaluation/dataset/unknown/*.jpg

Optional evaluation/dataset/manifest.json:
    [{"path": "known/Aastha Jain/side.jpg", "expected": "Aastha Jain", "condition": "angle"}]

The gallery defaults to the application's Known/ directory. Use --gallery to
point at another gallery directory when evaluating an isolated model set.
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import KNOWN_DIR, RECOGNITION_THRESHOLD
from services import face_service

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
CONDITIONS = {"lighting", "angle", "distance"}


def image_paths(directory: Path):
    return sorted(
        path for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def load_gallery(gallery_dir: Path):
    encodings = []
    names = []
    for path in image_paths(gallery_dir):
        try:
            image = np.array(Image.open(path).convert("RGB"), dtype=np.uint8)
            image_encodings = face_service.face_recognition.face_encodings(image)
            if image_encodings:
                encodings.append(image_encodings[0])
                names.append(path.parent.name if path.parent != gallery_dir else path.stem.rsplit("_", 1)[0])
        except (OSError, ValueError) as error:
            print(f"Skipping gallery image {path}: {error}", file=sys.stderr)
    return encodings, names


def load_samples(dataset_dir: Path):
    manifest_path = dataset_dir / "manifest.json"
    if manifest_path.exists():
        with manifest_path.open(encoding="utf-8") as manifest_file:
            return json.load(manifest_file)

    samples = []
    known_dir = dataset_dir / "known"
    for path in image_paths(known_dir) if known_dir.exists() else []:
        relative = path.relative_to(known_dir)
        samples.append({
            "path": str(path.relative_to(dataset_dir)).replace("\\", "/"),
            "expected": relative.parts[0] if len(relative.parts) > 1 else path.stem.rsplit("_", 1)[0],
            "condition": next((part for part in relative.parts[:-1] if part.lower() in CONDITIONS), "general"),
        })

    unknown_dir = dataset_dir / "unknown"
    for path in image_paths(unknown_dir) if unknown_dir.exists() else []:
        relative = path.relative_to(unknown_dir)
        samples.append({
            "path": str(path.relative_to(dataset_dir)).replace("\\", "/"),
            "expected": None,
            "condition": next((part for part in relative.parts[:-1] if part.lower() in CONDITIONS), "general"),
        })
    return samples


def evaluate_sample(sample, dataset_dir: Path):
    path = dataset_dir / sample["path"]
    expected = sample.get("expected")
    condition = sample.get("condition", "general")
    result = {
        "path": sample["path"],
        "expected": expected,
        "condition": condition,
        "predicted": None,
        "distance": None,
        "error": None,
    }
    try:
        image = np.array(Image.open(path).convert("RGB"), dtype=np.uint8)
        locations = face_service.face_recognition.face_locations(image)
        encodings = face_service.face_recognition.face_encodings(image, locations)
        if len(encodings) != 1:
            result["error"] = "expected exactly one face"
            return result
        predicted, distance = face_service.recognize_face(encodings[0])
        result["predicted"] = predicted
        result["distance"] = None if not np.isfinite(distance) else round(float(distance), 6)
    except (OSError, TypeError, ValueError) as error:
        result["error"] = str(error)
    return result


def metrics(results):
    total = len(results)
    known = [result for result in results if result["expected"] is not None]
    unknown = [result for result in results if result["expected"] is None]
    true_positive = sum(
        result["predicted"] == result["expected"] for result in known
    )
    accepted = sum(result["predicted"] is not None for result in results)
    false_positive = accepted - true_positive
    correct = sum(
        not result["error"] and result["predicted"] == result["expected"]
        for result in results
    )
    unknown_accepted = sum(result["predicted"] is not None for result in unknown)
    known_rejected = len(known) - true_positive
    return {
        "total_samples": total,
        "known_samples": len(known),
        "unknown_samples": len(unknown),
        "errored_samples": sum(bool(result["error"]) for result in results),
        "accuracy": correct / total if total else 0.0,
        "precision": true_positive / accepted if accepted else 0.0,
        "recall": true_positive / len(known) if known else 0.0,
        "false_acceptance_rate": unknown_accepted / len(unknown) if unknown else 0.0,
        "false_rejection_rate": known_rejected / len(known) if known else 0.0,
        "true_positive": true_positive,
        "false_positive": false_positive,
    }


def evaluate(dataset_dir: Path, gallery_dir: Path):
    if face_service.face_recognition is None:
        raise RuntimeError("face_recognition is required to run evaluation")

    encodings, names = load_gallery(gallery_dir)
    face_service.known_encodings[:] = encodings
    face_service.known_names[:] = names
    results = [evaluate_sample(sample, dataset_dir) for sample in load_samples(dataset_dir)]

    grouped = defaultdict(list)
    for result in results:
        grouped[result["condition"]].append(result)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold": RECOGNITION_THRESHOLD,
        "gallery_directory": str(gallery_dir),
        "gallery_faces": len(names),
        "metrics": metrics(results),
        "by_condition": {condition: metrics(items) for condition, items in sorted(grouped.items())},
        "samples": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path(__file__).parent / "dataset")
    parser.add_argument("--gallery", type=Path, default=KNOWN_DIR)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "results.json")
    args = parser.parse_args()
    report = evaluate(args.dataset, args.gallery)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["metrics"], indent=2))


if __name__ == "__main__":
    main()
