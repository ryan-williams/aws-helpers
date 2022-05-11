from datetime import datetime
from functools import partial
import json
import re


def default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    else:
        return json.JSONEncoder.default(o)


to_json = partial(json.dumps, indent=4, default=default)


def rgx_filter(all_names, fullmatch, regexs, key=None):
    if regexs:
        match_fn = re.fullmatch if fullmatch else re.search
        for regex in regexs:
            names = [
                name for name in all_names
                if match_fn(regex, name[key] if key else name)
            ]
    elif fullmatch:
        raise ValueError(f'-f/--fullmatch without <regexs>')
    else:
        names = all_names

    return names
