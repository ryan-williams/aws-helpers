#!/usr/bin/env python
import pandas as pd
from click import argument, command, option
import re
from re import fullmatch

from utz import basename, concat, DF, dirname, dt, env, exists, o, process, splitext, sxs, to_dt, urlparse


LINE_RGX = '(?P<mtime>\d{4}-\d{2}-\d{2} \d\d:\d\d:\d\d) +(?P<size>\d+) (?P<key>.*)'


def parse_line(line):
    m = re.fullmatch(LINE_RGX, line)
    if not m:
        raise ValueError(f'Unrecognized line: {line}')

    mtime = to_dt(m['mtime'])
    size = int(m['size'])
    key = m['key']
    return o(mtime=mtime, size=size, key=key)


def dirs(file):
    rv = [file]
    cur = file
    while True:
        dir = dirname(cur)
        if dir == cur:
            break
        else:
            rv.append(dir)
            cur = dir
    return list(reversed(rv))


def flatmap(self, func):
    dfs = []
    for idx, row in self.iterrows():
        df = func(row)
        dfs.append(df)
    return concat(dfs)

DF.flatmap = flatmap


def expand_file_row(r):
    file = r['key']
    file_df = r.to_frame().transpose()
    ancestors = dirs(file)
    dirs_df = DF([ dict(mtime=r['mtime'], size=r['size'], key=dir, type='dir') for dir in ancestors ])
    rows = concat([file_df, dirs_df]).reset_index(drop=True)
    return rows


def agg_dirs(files, k='path'):
    files['type'] = 'file'
    expanded = files.flatmap(expand_file_row)
    groups = expanded.groupby([k, 'type',])
    if len(groups) == len(files):
        return files
    sizes = groups['size'].sum()
    mtimes = groups['mtime'].max()
    num_descendents = groups.size().rename('num_descendents')
    aggd = sxs(mtimes, sizes, num_descendents).reset_index()
    return aggd


def strip_prefix(key, prefix):
    if key.startswith(prefix):
        return key[len(prefix):]
    else:
        raise ValueError(f"Key {key} doesn't start with expected prefix {prefix}")


@command('s3-usage')
@option('-o', '--output-path')
@option('-p', '--profile', help='AWS profile to use')
@argument('path')
def main(path, output_path, profile):
    if profile:
        env['AWS_PROFILE'] = profile

    url = urlparse(path)
    if url.scheme is None:
        print('Prepending "s3://"')
        path = f's3://{path}'

    m = fullmatch('s3://(?P<bucket>[^/]+)(?:/(?P<root_key>.*))?', path)
    if not m:
        raise ValueError(f'Unrecognized S3 URL: {path}')
    bucket = m['bucket']
    root_key = m['root_key'] or ''

    now = to_dt(dt.now())
    lines = process.lines('aws', 's3', 'ls', '--recursive', path)
    files = DF([ parse_line(line) for line in lines ])
    files['path'] = files['key'].apply(strip_prefix, prefix=f'{root_key}/')
    aggd = agg_dirs(files).sort_values('path')
    aggd['bucket'] = bucket
    aggd['root_key'] = root_key
    aggd['key'] = aggd['root_key'] + '/' + aggd['path']
    aggd['checked_dt'] = now
    aggd = aggd.drop(columns=['path', 'root_key'])

    if output_path:

        def merge(prev, cur):
            passthrough = prev[(prev.bucket != bucket)]
            if root_key:
                passthrough = concat([ passthrough, prev[(prev.bucket == bucket) & ~(prev.key.str.startswith(root_key))] ])
            merged = concat([ cur, passthrough ]).sort_values(['bucket', 'key'])
            num_passthrough = len(passthrough)
            num_overwritten = len(prev) - num_passthrough
            num_new = len(cur) - num_overwritten
            print(f"Overwriting {output_path}: {len(prev)} previous records, {num_passthrough} passing through, {num_overwritten} overwritten {num_new} new")
            return merged

        base, ext = splitext(output_path)
        if ext in {'.db', '.sqlite'}:
            sqlite_url = f'sqlite:///{output_path}'
            name = basename(base)
            if exists(output_path):
                prev = pd.read_sql_table(name, sqlite_url)
                aggd = merge(prev, aggd)
            aggd.to_sql(name, sqlite_url, if_exists='replace')
        elif ext in {'.pqt', '.parquet'}:
            if exists(output_path):
                prev = pd.read_parquet(output_path)
                aggd = merge(prev, aggd)
            aggd.to_parquet(output_path)
        else:
            raise ValueError(f'Unrecognized output path type: {output_path}')

    print(aggd)


if __name__ == '__main__':
    main()
