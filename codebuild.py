#!/usr/bin/env python

import boto3
from click import argument, option, group
from sys import stderr

from aws_utils import to_json, rgx_filter


codebuild = boto3.client('codebuild')


@group('codebuild')
def main():
    pass


@main.command('projects')
@option('-v', '--verbose', required=False, is_flag=True, help='Print project details')
@option('-f', '--fullmatch', required=False, is_flag=True, help='Use re.fullmatch instead of re.search when matching <regex> argument(s)')
@argument('regexs', required=False, nargs=-1)
def projects(verbose, fullmatch, regexs):
    all_project_names = codebuild.list_projects()['projects']

    project_names = rgx_filter(all_project_names, fullmatch=fullmatch, regexs=regexs)
    if not project_names:
        raise RuntimeError(f'No projects found matching {regexs}')

    if verbose:
        resp = codebuild.batch_get_projects(names=project_names)
        projects = resp['projects']
        projectsNotFound = resp['projectsNotFound']
        if projectsNotFound:
            raise RuntimeError("Didn't find projects:\n\t%s" % '\n\t'.join(projectsNotFound))
        print(to_json(projects))
    else:
        print('\n'.join(project_names))


@main.group('builds')
def builds(): pass


def get_page(cmd, max_num, **kwargs):
    paginator = codebuild.get_paginator(cmd)
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


def get_builds(verbose, max_num, project_name):
    build_ids = get_page('list_builds_for_project', max_num, projectName=project_name)['ids']
    if not build_ids:
        return []
    builds = founds(codebuild.batch_get_builds(ids=build_ids), 'builds')
    if not verbose:
        builds = [
            { k: build[k] for k in [ 'id', 'startTime', 'buildStatus', ] }
            for build in builds
        ]
    return builds


@builds.command('list')
@option('-v', '--verbose', count=True, help='0 (default): print build IDs only; 1 ("-v"): print {id, startTime, buildStatus}; 2 ("-vv"): print full build objects')
@option('-n', '--max-num', type=int, help='Maximum number of builds to list')
@argument('project_name')
def list(verbose, max_num, project_name):
    builds = get_builds(verbose=verbose == 2, max_num=max_num, project_name=project_name)
    if verbose:
        print(to_json(builds))
    else:
        ids = [ build['id'] for build in builds ]
        print('\n'.join(ids))


@builds.command('latest')
@option('-v', '--verbose', count=True, help='0 (default): print build IDs only; 1 ("-v"): print {id, startTime, buildStatus}; 2 ("-vv"): print full build objects')
@argument('project_names', nargs=-1)
def latest(verbose, project_names):
    builds_dict = {}
    for project_name in project_names:
        project_builds = get_builds(verbose=verbose == 2, max_num=1, project_name=project_name)
        if len(project_builds) == 1:
            builds_dict[project_name] = project_builds[0]
        elif not project_builds:
            builds_dict[project_name] = None
        else:
            raise RuntimeError("Found %d builds for project %s: %s" % (len(project_builds), project_name, str(project_builds)))

    if verbose:
        print(to_json(builds_dict))
    else:
        ids = [ build['id'] for build in builds_dict.values() ]
        print('\n'.join(ids))


@builds.command('logs')
@option('-e', '--event-json', is_flag=True, help='Print a JSON array with the full events ({datetime, level, message}) rather than just printing the messages (which is the default behavior)')
@option('-n', '--max-num', type=int, default='-1', help='Only fetch this many events; -1 (default) means "no limit" / "fetch all"')
@option('-s', '--page-size', type=int, default='10000', help='Only fetch this many events; -1 (default) means "no limit" / "fetch all"')
@argument('id')
def logs(event_json, max_num, page_size, id):
    [build] = founds(codebuild.batch_get_builds(ids=[id]), 'builds')
    logs = build['logs']
    log_group = logs['groupName']
    log_stream = logs['streamName']
    logs_client = boto3.client('logs')
    events = []
    next_token = None
    page_idx = 1
    while max_num == -1 or len(events) < max_num:
        if max_num == -1:
            limit = page_size
        else:
            limit = min(max_num - len(events), page_size)
        kwargs = dict(logGroupName=log_group, logStreamName=log_stream, limit=limit, startFromHead=True)
        if next_token:
            kwargs['nextToken'] = next_token

        stderr.write(f'Fetching page {page_idx} (currently {len(events)} events), size {page_size}, limit {limit}, token {next_token}, group {log_group}, stream {log_stream}\n')
        resp = logs_client.get_log_events(**kwargs)
        page_idx += 1

        new_events = resp['events']
        stderr.write(f'got {len(new_events)} new events\n')
        events += new_events

        if resp['nextForwardToken'] == next_token:
            break
        next_token = resp['nextForwardToken']

    if event_json:
        print(to_json(events))
    else:
        messages = [ event['message'].rstrip('\n') for event in events ]
        print('\n'.join(messages))


if __name__ == '__main__':
    main()
