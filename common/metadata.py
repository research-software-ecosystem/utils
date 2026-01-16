def normalize_version_to_string(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return [normalize_version_to_string(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize_version_to_string(v) for k, v in value.items()}
    return value


def normalize_version_fields(data, field_paths):
    if not isinstance(data, dict):
        raise TypeError(f"Expected dict, got {type(data).__name__}")

    for field_path in field_paths:
        try:
            if "[" in field_path:
                if "[]." not in field_path:
                    list_key = field_path.rstrip("[]")
                    if list_key in data and isinstance(data[list_key], list):
                        data[list_key] = normalize_version_to_string(data[list_key])
                else:
                    list_key, item_path = field_path.split("[].", 1)
                    if list_key in data and isinstance(data[list_key], list):
                        for item in data[list_key]:
                            if isinstance(item, dict) and item_path in item:
                                item[item_path] = normalize_version_to_string(
                                    item[item_path]
                                )
            elif "." in field_path:
                keys = field_path.split(".")
                current = data
                for key in keys[:-1]:
                    if not isinstance(current, dict) or key not in current:
                        break
                    current = current[key]
                else:
                    final_key = keys[-1]
                    if isinstance(current, dict) and final_key in current:
                        current[final_key] = normalize_version_to_string(
                            current[final_key]
                        )
            else:
                if field_path in data:
                    data[field_path] = normalize_version_to_string(data[field_path])
        except Exception:
            continue

    return data
