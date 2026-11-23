"""Tolerant tool arguments (pure): repair what a model sends before a tool runs, and say exactly what is missing when it cannot.

A watched run called use_hm {"hm": "Dig"} and got "Tool use_hm failed: 'move'" — a bare KeyError that names no schema. The harness should meet the model halfway: rename an
argument that is plainly the one the tool wants, coerce "5" to 5, and otherwise answer with the tool's own signature."""
import json

# argument names models use for another tool's parameter; applied only when the tool has the target parameter and it was not sent
_SYNONYMS = {
    "hm": "move", "hm_name": "move", "field_move": "move", "move_name": "move", "ability": "move", "action": "move",
    "item_name": "item", "item_id": "item", "name": None,                  # `name` is ambiguous (quest name / milestone name / nickname): only the one-missing rule applies
    "pokemon_name": "pokemon", "species": "pokemon", "mon": "pokemon", "target_pokemon": "pokemon", "party_member": "pokemon",
    "dest": "destination", "location": "destination", "place": "destination", "map": "destination", "town": "destination",
    "direction_name": "direction", "dir": "direction", "side": "direction", "edge": "direction",
    "x_coord": "x", "y_coord": "y", "tile_x": "x", "tile_y": "y", "col": "x", "row": "y",
    "button_name": "button", "key": "button", "buttons": "button",
    "count": "times", "repeat": "times", "n": "times",
}


def _coerce(value, spec: dict):
    kind = spec.get("type")
    try:
        if kind == "integer" and isinstance(value, (str, float)) and not isinstance(value, bool):
            return int(float(str(value).strip()))
        if kind == "number" and isinstance(value, str):
            return float(value.strip())
        if kind == "boolean" and isinstance(value, str):
            low = value.strip().lower()
            if low in ("true", "yes", "1"):
                return True
            if low in ("false", "no", "0"):
                return False
        if kind == "string" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
    except (TypeError, ValueError):
        pass
    return value


def signature(name: str, schema: dict) -> str:
    props, req = schema.get("properties", {}), set(schema.get("required", []))
    parts = []
    for key, spec in props.items():
        kind = spec.get("type", "any")
        if spec.get("enum"):
            kind = "|".join(map(str, spec["enum"]))
        parts.append(f"{key}{'' if key in req else '?'}: {kind}")
    return f"{name}({', '.join(parts)})"


def repair_args(name: str, args, schema: dict | None):
    """(args, error). `args` is the parsed JSON the model sent; `schema` the tool's JSON-schema parameters (None = unknown tool: untouched).
    error is '' when the call can go ahead (args possibly repaired), else a message that quotes the tool's signature and what was sent."""
    if not schema:
        return (args if isinstance(args, dict) else {}), ""
    props, req = schema.get("properties", {}), list(schema.get("required", []))
    if args is None:
        args = {}
    if not isinstance(args, dict):                          # a bare value: the tool's only required parameter
        if len(req) == 1:
            args = {req[0]: args}
        else:
            return {}, f"{name} takes named arguments — {signature(name, schema)}. You sent {json.dumps(args)[:80]}."
    out = dict(args)
    missing = [r for r in req if r not in out]
    unknown = [k for k in out if k not in props]
    for k in list(unknown):                                  # known synonyms first
        target = _SYNONYMS.get(k)
        if target and target in props and target not in out:
            out[target] = out.pop(k)
            unknown.remove(k)
            missing = [r for r in req if r not in out]
    if len(unknown) == 1 and len(missing) == 1:              # one stray name and one missing requirement: they are the same thing
        out[missing[0]] = out.pop(unknown[0])
        missing = []
    for k, v in list(out.items()):
        if k in props:
            out[k] = _coerce(v, props[k])
    missing = [r for r in req if r not in out]
    if missing:
        sent = ", ".join(f"{k}={json.dumps(v)[:30]}" for k, v in args.items()) or "nothing"
        return out, f"{name} needs {', '.join(missing)} — {signature(name, schema)}. You sent: {sent}."
    return out, ""
