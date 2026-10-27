"""Cross-check translation keys, enum options, services and icons of the integration.

Usage:  python scripts/check_translations.py   (needs PyYAML)
Exits non-zero when something is inconsistent.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import sys

import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
COMPONENT = (
    pathlib.Path(sys.argv[1])
    if len(sys.argv) > 1
    else REPO / "custom_components" / "myskoda_public_api"
)
PLATFORMS = [
    "sensor",
    "binary_sensor",
    "switch",
    "climate",
    "number",
    "select",
    "button",
    "image",
    "device_tracker",
]
# Translation keys used in code that are exceptions, not entity names.
EXCEPTION_KEYS_IN_PLATFORMS = {"spin_required"}

problems: list[str] = []


def load(name: str) -> dict:
    return json.loads((COMPONENT / name).read_text(encoding="utf-8"))


def leaves(data: dict, prefix: str = ""):
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            yield from leaves(value, path)
        else:
            yield path, value


strings = load("strings.json")
en = load("translations/en.json")
de = load("translations/de.json")
icons = load("icons.json")

if strings != en:
    problems.append("translations/en.json differs from strings.json")

en_leaves = dict(leaves(strings))
de_leaves = dict(leaves(de))
for key in sorted(set(en_leaves) - set(de_leaves)):
    problems.append(f"de.json missing: {key}")
for key in sorted(set(de_leaves) - set(en_leaves)):
    problems.append(f"de.json extra: {key}")
for key, text in en_leaves.items():
    if key in de_leaves and set(re.findall(r"\{(\w+)\}", text)) != set(
        re.findall(r"\{(\w+)\}", de_leaves[key])
    ):
        problems.append(f"placeholder mismatch: {key}")

for platform in PLATFORMS:
    source = (COMPONENT / f"{platform}.py").read_text(encoding="utf-8")
    used = set(re.findall(r'translation_key="([a-z_]+)"', source))
    used |= set(re.findall(r'_attr_translation_key = "([a-z_]+)"', source))
    used -= EXCEPTION_KEYS_IN_PLATFORMS
    defined = set(strings["entity"].get(platform, {}))
    for key in sorted(used - defined):
        problems.append(f"{platform}: translation_key {key} missing in strings.json")
    for key in sorted(defined - used):
        problems.append(f"{platform}: strings.json entity {key} is unused")
    for key in sorted(set(icons["entity"].get(platform, {})) - defined):
        problems.append(f"icons.json: {platform}.{key} is not an entity")

# Enum sensor options must match their state translations.
tree = ast.parse((COMPONENT / "sensor.py").read_text(encoding="utf-8"))
constants: dict[str, list] = {}
for node in tree.body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = node.targets[0]
        if isinstance(target, ast.Name):
            try:
                constants[target.id] = ast.literal_eval(node.value)
            except ValueError:
                pass
const_tree = ast.parse((COMPONENT / "const.py").read_text(encoding="utf-8"))
for node in const_tree.body:
    if (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "CHARGE_MODES"
    ):
        constants["CHARGE_MODE_OPTIONS"] = [m.lower() for m in ast.literal_eval(node.value)]

for node in ast.walk(tree):
    if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "MySkodaSensorDescription":
        keywords = {kw.arg: kw.value for kw in node.keywords}
        key = keywords["key"].value
        states = set(strings["entity"]["sensor"][key].get("state", {}))
        if "options" in keywords:
            option_node = keywords["options"]
            options = (
                constants[option_node.id]
                if isinstance(option_node, ast.Name)
                else ast.literal_eval(option_node)
            )
            if set(options) != states:
                problems.append(f"sensor {key}: options {sorted(set(options) ^ states)} differ")
        elif states:
            problems.append(f"sensor {key}: has state translations but no options")

select_states = set(strings["entity"]["select"]["charge_mode"]["state"])
if set(constants["CHARGE_MODE_OPTIONS"]) != select_states:
    problems.append("select charge_mode: options differ from state translations")

# Exceptions and issues.
used_exceptions: set[str] = set()
for name in ("coordinator.py", "services.py"):
    used_exceptions |= set(
        re.findall(r'translation_key="(\w+)"', (COMPONENT / name).read_text(encoding="utf-8"))
    )
used_exceptions.discard("api_key_expiring")
used_exceptions |= EXCEPTION_KEYS_IN_PLATFORMS
for key in sorted(used_exceptions - set(strings["exceptions"])):
    problems.append(f"exception {key} missing in strings.json")
for key in sorted(set(strings["exceptions"]) - used_exceptions):
    problems.append(f"exception {key} unused")
if "api_key_expiring" not in strings["issues"]:
    problems.append("issue api_key_expiring missing")

# Config flow steps, errors and aborts.
config_flow = (COMPONENT / "config_flow.py").read_text(encoding="utf-8")
for step in set(re.findall(r'step_id="(\w+)"', config_flow)):
    section = "options" if step == "init" else "config"
    if step not in strings[section]["step"]:
        problems.append(f"step {step} missing in strings.{section}")
for error in set(re.findall(r'return "(\w+)"', config_flow)) | {"invalid_vin"}:
    if error not in strings["config"]["error"]:
        problems.append(f"config error {error} missing")
for abort in ("already_configured", "reauth_successful", "reconfigure_successful"):
    if abort not in strings["config"]["abort"]:
        problems.append(f"abort {abort} missing")

# services.yaml vs strings vs icons.
services = yaml.safe_load((COMPONENT / "services.yaml").read_text(encoding="utf-8"))
if set(services) != set(strings["services"]):
    problems.append("services.yaml and strings.json list different services")
for name, service in services.items():
    if set(service["fields"]) != set(strings["services"][name]["fields"]):
        problems.append(f"service {name}: fields differ between services.yaml and strings.json")
if set(services) != set(icons["services"]):
    problems.append("icons.json services differ from services.yaml")

if problems:
    print("\n".join(problems))
    sys.exit(1)
print("translations, enums, services and icons are consistent")
