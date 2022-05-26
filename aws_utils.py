from datetime import datetime
from functools import partial
import json
import re

import boto3


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


def get_page(client, cmd, max_num, **kwargs):
    paginator = client.get_paginator(cmd)
    page_iterator = paginator.paginate(
        **kwargs,
        PaginationConfig={ 'MaxItems': max_num if max_num else None },
    )
    page = next(page for page in page_iterator)
    return page


def founds(resp, key, not_found_key=None):
    not_found_key = not_found_key if not_found_key else f'{key}NotFound'
    not_founds = resp[not_found_key]
    if not_founds:
        raise RuntimeError("%s:\n%s" % (not_found_key, to_json(not_founds)))
    return resp[key]
