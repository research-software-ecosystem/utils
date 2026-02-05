import logging


def normalize_version_to_string(value):
    """
    Recursively convert version values to strings.

    This function processes version data by converting numeric types to strings
    while preserving None and boolean values. It recursively processes nested
    structures (lists and dicts).

    Args:
        value: The value to normalize. Can be any type.

    Returns:
        - None and bool values are returned unchanged
        - int and float values are converted to strings
        - Lists are processed recursively, returning a new list with normalized values
        - Dicts are processed recursively, returning a new dict with normalized values
        - Other types are returned unchanged

    Examples:
        >>> normalize_version_to_string(1)
        '1'
        >>> normalize_version_to_string([1, 2, 3])
        ['1', '2', '3']
        >>> normalize_version_to_string({'version': 1.5})
        {'version': '1.5'}
    """
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
    """
    Normalize version fields to strings in a data dictionary.

    This function takes a dictionary and a collection of field paths, then normalizes
    the version values at those paths to strings using normalize_version_to_string.

    Args:
        data (dict): The dictionary to process.
        field_paths (iterable): An iterable of field path strings. Supports:
            - Simple fields: "version"
            - Nested fields: "tool.version"
            - List fields: "versions[]"
            - List item nested fields: "versions[].version"

    Returns:
        dict: The modified data dictionary with normalized version fields.

    Raises:
        TypeError: If data is not a dictionary.

    Examples:
        >>> data = {"version": 1, "versions": [{"version": 2}]}
        >>> normalize_version_fields(data, ["version", "versions[].version"])
        {'version': '1', 'versions': [{'version': '2'}]}
    """
    if not isinstance(data, dict):
        raise TypeError(f"Expected dict, got {type(data).__name__}")

    for field_path in field_paths:
        try:
            if "[" in field_path:
                if "[]." not in field_path:
                    list_key = field_path[:-2] if field_path.endswith("[]") else field_path
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
        except (KeyError, TypeError, IndexError, AttributeError) as e:
            logging.debug(f"Skipping field path '{field_path}': {e}")
            continue

    return data
