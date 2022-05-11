#!/usr/bin/env python

import boto3
from click import group, argument, option

from aws_utils import to_json, rgx_filter


@group('codepipeline')
def codepipeline():
    pass

@codepipeline.command('list')
@option('-f', '--fullmatch', required=False, is_flag=True, help='Use re.fullmatch instead of re.search when matching <regex> argument(s)')
@option('-v', '--verbose', required=False, is_flag=True, help='Print project details')
@argument('regexs', required=False, nargs=-1)
def list(fullmatch, verbose, regexs):
    client = boto3.client('codepipeline')
    all_pipelines = client.list_pipelines()['pipelines']
    pipelines = rgx_filter(all_pipelines, fullmatch=fullmatch, regexs=regexs, key='name')
    if verbose:
        pipelines = [
            client.get_pipeline(name=pipeline['name'])['pipeline']
            for pipeline in pipelines
        ]
    print(to_json(pipelines))


if __name__ == '__main__':
    codepipeline()
