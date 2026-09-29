"""Map an evidence-cleared experiment to the image-to-video pipeline contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .build_rag_prompt_bundle import build_bundle, load_canonical_records
except ImportError:
    from build_rag_prompt_bundle import build_bundle, load_canonical_records

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "reports" / "pipeline_handoff.json"


def make_scene(record: dict[str, Any], scene: dict[str, Any]) -> dict[str, Any]:
    return {
        "scene": scene["description"],
        "camera": "stable medium shot of a school laboratory bench",
        "lighting": "clear classroom laboratory lighting",
        "objects": record.get("materials", []),
        "background": "clean school chemistry laboratory",
        "metadata": {
            "scene_id": scene["scene_id"],
            "visible_actions": scene.get("visible_actions", []),
            "image_asset_id": scene.get("image_asset_id", ""),
        },
    }


def build_handoff(experiment_id: str) -> dict[str, Any]:
    records = load_canonical_records()
    if experiment_id not in records:
        raise ValueError(f"Unknown experiment_id: {experiment_id}")
    record = records[experiment_id]
    bundle = build_bundle(record["title"], top_k=1, experiment_id=experiment_id)
    if bundle["status"] != "explicit_selection" or not bundle["prompt_inputs"]:
        return {
            "status": "blocked",
            "experiment_id": experiment_id,
            "message": bundle["message"],
            "review_report": bundle.get("review_report", {}),
            "experiment": None,
            "validation": {"valid": False, "errors": ["Evidence gate did not produce prompts."]},
        }

    scenes_by_id = {scene["scene_id"]: scene for scene in record.get("scenes", [])}
    steps_by_id = {step["step_id"]: step for step in record.get("procedure_steps", [])}
    # Provisional CPU integration duration, not a scientifically calibrated action length.
    duration = 1.0
    clips = []
    errors: list[str] = []

    for index, prompt_input in enumerate(bundle["prompt_inputs"], 1):
        scene = scenes_by_id.get(prompt_input["scene_id"])
        step = steps_by_id.get(prompt_input["step_id"])
        if scene is None or step is None:
            errors.append(f"Prompt input {prompt_input['step_id']} has no canonical scene or step.")
            continue
        passage_ids = prompt_input.get("passage_ids", [])
        if not passage_ids:
            errors.append(f"Prompt input {prompt_input['step_id']} has no evidence passage IDs.")

        clips.append({
            "name": f"clip_{index}",
            "image_state": make_scene(record, scene),
            "motion_prompt": {
                "image_prompt": (
                    f"{scene['description']} Materials: {', '.join(record.get('materials', []))}."
                ),
                "motion_prompt": prompt_input["prompt"],
                "moving_object": ", ".join(scene.get("visible_actions", [])),
                "direction": "controlled, observable laboratory action",
                "motion": step["instruction"],
                "constraints": (
                    "Use only the listed apparatus and materials; preserve scientific order and quantities; "
                    + "; ".join(record.get("safety_notes", []))
                ),
                "stop_condition": step["observation"],
                "clip_duration_seconds": round(duration, 3),
                "negative_prompt": prompt_input["negative_prompt"],
                "metadata": {
                    "experiment_id": experiment_id,
                    "scene_id": scene["scene_id"],
                    "step_id": step["step_id"],
                    "source_ids": [source["source_id"] for source in record.get("sources", [])],
                    "passage_ids": passage_ids,
                    "image_status": "placeholder_requires_manual_image",
                    "starting_image_reference": prompt_input.get("starting_image", ""),
                },
            },
            "metadata": {
                "step_id": step["step_id"],
                "scene_id": scene["scene_id"],
                "new_scene": index == 1 or bundle["prompt_inputs"][index - 2]["scene_id"] != scene["scene_id"],
            },
        })

    experiment = {
        "name": record["title"],
        "description": record["educational_goal"],
        "subject": record["subject"],
        "educational_goal": record["educational_goal"],
        "knowledge_source": ", ".join(source["source_id"] for source in record.get("sources", [])),
        "metadata": {
            "experiment_id": experiment_id,
            "class_level": record["class_level"],
            "difficulty": record["difficulty"],
            "source_ids": [source["source_id"] for source in record.get("sources", [])],
            "evidence_status": "evidence_gate_passed",
            "duration_status": "provisional_cpu_test",
            "image_status": "placeholder_requires_manual_image",
        },
        "clips": clips,
    }
    required_experiment = ["name", "description", "subject", "educational_goal", "knowledge_source", "clips"]
    required_clip = ["name", "image_state", "motion_prompt"]
    required_scene = ["scene", "camera", "lighting", "objects", "background"]
    required_prompt = [
        "image_prompt", "motion_prompt", "moving_object", "direction", "motion",
        "constraints", "stop_condition", "clip_duration_seconds", "negative_prompt",
    ]
    for field in required_experiment:
        if field not in experiment:
            errors.append(f"Missing Experiment field: {field}")
    for clip in clips:
        for field in required_clip:
            if field not in clip:
                errors.append(f"Missing Clip field {field} in {clip.get('name')}")
        for field in required_scene:
            if field not in clip["image_state"]:
                errors.append(f"Missing Scene field {field} in {clip.get('name')}")
        for field in required_prompt:
            if field not in clip["motion_prompt"]:
                errors.append(f"Missing PromptBundle field {field} in {clip.get('name')}")

    return {
        "status": "ready" if not errors else "invalid",
        "experiment_id": experiment_id,
        "contract": "image-to-video-pipeline Experiment/Clip/Scene/PromptBundle",
        "validation": {
            "valid": not errors,
            "errors": errors,
            "clip_count": len(clips),
            "ordered_step_ids": [clip["motion_prompt"]["metadata"]["step_id"] for clip in clips],
            "all_clips_have_passages": all(
                bool(clip["motion_prompt"]["metadata"]["passage_ids"]) for clip in clips
            ),
        },
        "experiment": experiment,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a validated pipeline handoff without generation.")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    handoff = build_handoff(args.experiment_id)
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Status: {handoff['status']}")
    print(f"Saved handoff to {output_path}")
    print(json.dumps(handoff["validation"], indent=2))


if __name__ == "__main__":
    main()
