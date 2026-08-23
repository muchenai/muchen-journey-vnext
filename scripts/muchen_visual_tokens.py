#!/usr/bin/env python3
"""Validate the isolated five-map visual token contract."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


HEX_COLOR = re.compile(r"^#[0-9a-f]{6}$")
COLOR_KEYS = (
    "canvas",
    "canvas_ink",
    "surface",
    "surface_ink",
    "accent",
    "accent_ink",
    "path",
)


def relative_luminance(color: str) -> float:
    channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first: str, second: str) -> float:
    high, low = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(repo: Path, contract_path: Path, css_path: Path) -> tuple[list[str], list[str]]:
    contract = load_json(contract_path)
    product = load_json(repo / "config/muchen_journey_product.json")
    css = css_path.read_text(encoding="utf-8")
    errors: list[str] = []
    evidence: list[str] = []

    if contract.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if contract.get("contract_type") != "ISOLATED_SHARED_VISUAL_CONTRACT":
        errors.append("contract_type must identify the isolated shared visual contract")
    if contract.get("state") != "DRAFT_ONLY":
        errors.append("state must remain DRAFT_ONLY")
    if contract.get("formal_golden_path_promoted") is not False:
        errors.append("formal_golden_path_promoted must be false")
    if contract.get("interaction_semantics") != "NONE":
        errors.append("interaction_semantics must be NONE")

    maps = contract.get("maps")
    product_maps = product.get("maps")
    if not isinstance(maps, list) or not isinstance(product_maps, list):
        return [*errors, "maps must be lists"], evidence
    expected = [(item["order"], item["key"], item["name"]) for item in product_maps]
    actual = [(item.get("order"), item.get("key"), item.get("name")) for item in maps]
    if actual != expected:
        errors.append("visual map order must exactly match the product contract")

    minimum = float(contract.get("minimum_contrast_ratio", 0))
    if minimum < 4.5:
        errors.append("minimum_contrast_ratio must be at least 4.5")
    for item in maps:
        key = str(item.get("key", ""))
        colors = item.get("colors")
        if not isinstance(colors, dict):
            errors.append(f"{key}: colors must be an object")
            continue
        for color_key in COLOR_KEYS:
            value = colors.get(color_key)
            if not isinstance(value, str) or not HEX_COLOR.fullmatch(value):
                errors.append(f"{key}: invalid {color_key}")
                continue
            css_key = f"--mj-map-{key}-{color_key.replace('_', '-')}"
            match = re.search(rf"{re.escape(css_key)}:\s*(#[0-9a-f]{{6}})", css)
            if not match or match.group(1) != value:
                errors.append(f"{key}: CSS token drift for {color_key}")
        for background_key, foreground_key in (
            ("canvas", "canvas_ink"),
            ("surface", "surface_ink"),
            ("accent", "accent_ink"),
        ):
            background = colors.get(background_key)
            foreground = colors.get(foreground_key)
            if isinstance(background, str) and isinstance(foreground, str):
                ratio = contrast(background, foreground)
                evidence.append(f"{key}.{background_key}={ratio:.2f}:1")
                if ratio < minimum:
                    errors.append(
                        f"{key}: {background_key}/{foreground_key} contrast {ratio:.2f} is below {minimum:.2f}"
                    )
    return errors, evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument(
        "--contract",
        default="prototypes/shared/five-map-visual-tokens.json",
    )
    parser.add_argument(
        "--css",
        default="prototypes/shared/five-map-visual-tokens.css",
    )
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    contract_path = (repo / args.contract).resolve()
    css_path = (repo / args.css).resolve()
    for path in (contract_path, css_path):
        try:
            path.relative_to(repo)
        except ValueError:
            print("VISUAL_TOKENS=FAIL\nERROR=inputs must stay inside repository")
            return 2
    errors, evidence = validate(repo, contract_path, css_path)
    if errors:
        print("VISUAL_TOKENS=FAIL")
        for error in errors:
            print(f"ERROR={error}")
        return 2
    print("VISUAL_TOKENS=PASS")
    print("MAPS=5")
    print("FORMAL_GOLDEN_PATH_PROMOTED=false")
    print("INTERACTION_SEMANTICS=NONE")
    for item in evidence:
        print(f"CONTRAST={item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
