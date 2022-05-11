#!/usr/bin/env python

import boto3
from click import command, argument, option
from datetime import datetime
import json
import re


# class Encoder(json.JSONEncoder):
def default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    else:
        return json.JSONEncoder.default(o)


@command('codebuild_projects')
@option('-v', '--verbose', required=False, is_flag=True, help='Print project details')
@option('-f', '--fullmatch', required=False, is_flag=True, help='Use re.fullmatch instead of re.search when matching <regex> argument(s)')
@argument('regexs', required=False, nargs=-1)
def main(verbose, fullmatch, regexs):
    codebuild = boto3.client('codebuild')
    all_project_names = codebuild.list_projects()['projects']

    project_names = all_project_names
    if regexs:
        match_fn = re.fullmatch if fullmatch else re.search
        for regex in regexs:
            project_names = [
                project_name
                for project_name in project_names
                if match_fn(regex, project_name)
            ]
    elif fullmatch:
        raise ValueError(f'-f/--fullmatch without <regexs>')
    else:
        project_names = all_project_names

    if verbose:
        resp = codebuild.batch_get_projects(names=project_names)
        projects = resp['projects']
        projectsNotFound = resp['projectsNotFound']
        if projectsNotFound:
            raise RuntimeError("Didn't find projects:\n\t%s" % '\n\t'.join(projectsNotFound))
        print(json.dumps(projects, indent=4, default=default))
    else:
        print('\n'.join(project_names))


if __name__ == '__main__':
    main()
