#!/usr/bin/env python

import boto3
from click import argument, option, group
import re

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


@builds.command('list')
@option('-v', '--verbose', is_flag=True, help='Print full build details')
@option('-n', '--max-num', type=int, help='Maximum number of builds to list')
@argument('project_name')
def list(verbose, max_num, project_name):
    print(to_json(list_builds(verbose, max_num, project_name)))


def list_builds(verbose, max_num, project_name):
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


@builds.command('latest')
@option('-v', '--verbose', is_flag=True, help='Print full build details')
@argument('project_names', nargs=-1)
def latest(verbose, project_names):
    builds_dict = {}
    for project_name in project_names:
        project_builds = list_builds(verbose=verbose, max_num=1, project_name=project_name)
        if len(project_builds) == 1:
            builds_dict[project_name] = project_builds[0]
        elif not project_builds:
            builds_dict[project_name] = None
        else:
            raise RuntimeError("Found %d builds for project %s: %s" % (len(project_builds), project_name, str(project_builds)))

    print(to_json(builds_dict))


@builds.command('logs')
@argument('id')
def logs(id):
    [build] = founds(codebuild.batch_get_builds(ids=[id]), 'builds')
    logs = build['logs']
    log_group = logs['groupName']
    log_stream = logs['streamName']
    logs_client = boto3.client('logs')
    events = logs_client.get_log_events(logGroupName=log_group, logStreamName=log_stream)['events']
    messages = [ event['message'].rstrip('\n') for event in events ]
    print('\n'.join(messages))


if __name__ == '__main__':
    main()
