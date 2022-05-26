#!/usr/bin/env python

import boto3
from click import group, argument, option

from aws_utils import to_json, rgx_filter


@group('codepipeline')
def codepipeline():
    pass


@codepipeline.command('list')
@option('-f', '--fullmatch', required=False, is_flag=True, help='Use re.fullmatch instead of re.search when matching <regex> argument(s)')
@option('-v', '--verbose', required=False, is_flag=True, help='Print pipeline details')
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


@codepipeline.group('executions')
def executions():
    pass


@executions.command('list')
@option('-n', '--max-num', type=int, default='-1', help='Only fetch this many pipeline executions; -1 (default) means "no limit" / "fetch all"')
@option('-v', '--verbose', required=False, count=True, help='0: print pipeline execution ID only; 1: print id, status, start/end times; 2: print all pipeline execution details')
@argument('pipeline_name', required=True)
def list_pipeline_executions(max_num, verbose, pipeline_name):
    client = boto3.client('codepipeline')

    kwargs = dict()
    if max_num != -1:
        kwargs['maxResults'] = max_num

    pipeline_executions = client.list_pipeline_executions(pipelineName=pipeline_name, **kwargs)['pipelineExecutionSummaries']
    if verbose == 0:
        pipeline_executions = [
            pipeline_execution['pipelineExecutionId']
            for pipeline_execution in pipeline_executions
        ]
    elif verbose == 1:
        pipeline_executions = [
            { k: pipeline_execution[k] for k in [ 'pipelineExecutionId', 'status', 'startTime', 'lastUpdateTime', ] }
            for pipeline_execution in pipeline_executions
        ]
    # else:

    print(to_json(pipeline_executions))


if __name__ == '__main__':
    codepipeline()
