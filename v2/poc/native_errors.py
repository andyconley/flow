"""Decode explicit native error envelopes; missing telemetry never implies denial."""
import json

PREFIX = 'GLG_NATIVE_BOUNDARY:'


def boundary_error(text):
    def inspect(value):
        if isinstance(value, dict):
            for nested in value.values():
                result = inspect(nested)
                if result:
                    return result
        elif isinstance(value, list):
            for nested in value:
                result = inspect(nested)
                if result:
                    return result
        elif isinstance(value, str) and PREFIX in value:
            try:
                error, _ = json.JSONDecoder().raw_decode(value.split(PREFIX, 1)[1])
            except (ValueError, TypeError):
                return None
            if isinstance(error, dict) and error.get('schema_version') == 1 and error.get('kind') in {'permission_required', 'scope_required'} and isinstance(error.get('error'), dict):
                return error
        return None
    for line in text.splitlines():
        try:
            event = json.loads(line)
            result = inspect(event) if isinstance(event, dict) and event.get('type') == 'error' else None
        except ValueError:
            result = inspect(line) if line.lstrip().startswith(('Error:', 'error:')) else None
        if result:
            return result
    return None
