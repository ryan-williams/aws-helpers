#!/usr/bin/env python
from datetime import datetime, timezone
import json
import re
from configparser import ConfigParser
from functools import partial
from getpass import getuser
from os import remove, environ, makedirs
from os.path import expanduser, join, exists, dirname
from subprocess import check_output
from sys import stderr, stdout
from typing import Callable

import yaml
from click import command, argument, option
from dateutil.parser import parse

SECTION_RGX = re.compile(r'profile (?P<profile>\w+)')
AWS_CONFIG_DIR = expanduser('~/.aws')
DEFAULT_CREDS_DIR = join(AWS_CONFIG_DIR, 'creds')
DEFAULT_CREDS_CONFIG_NAME = 'creds.yml'

err = partial(print, file=stderr)


def silent(*args, **kwargs):
    pass


def cred_key_to_env_var(k: str) -> str:
    var = ''
    idx = 0
    for m in re.finditer("[a-z][A-Z]", k):
        var += k[idx:m.start() + 1].upper() + '_' + k[m.start() + 1]
        idx = m.end()
    var += k[idx:].upper()
    return var


def creds_to_envs(creds: dict[str, str]) -> dict[str, str]:
    return {
        f'AWS_{cred_key_to_env_var(k)}': v
        for k, v in creds.items()
    }


def run(
    cmd: str,
    log: Callable[[str], None],
    envs: dict[str, str] | None = None,
) -> str:
    if envs:
        envs_str = ', '.join([ f'{k}={v}' for k, v in envs.items() ])
        log(f"Running: {cmd} ({envs_str})")
        env = { **environ, **envs }
    else:
        log(f"Running: {cmd}")
        env=None
    return check_output(cmd, shell=True, env=env).decode().rstrip('\n')


def run_json(
    cmd: str,
    log: Callable[[str], None],
    envs: dict[str, str] | None = None,
) -> dict[str, str]:
    output = run(cmd=cmd, log=log, envs=envs)
    return json.loads(output)


def load_creds(
    creds_dir: str,
    quiet: bool,
    session_name: str | None,
    profile_name: str,
):
    log = silent if quiet else err
    if not profile_name:
        profile_name = environ.get('AWS_PROFILE')
        if not profile_name:
            raise RuntimeError("No <profile> passed, and AWS_PROFILE not set")
    log(f'aws-creds.py: {profile_name=}')
    creds_path = join(creds_dir, f'{profile_name}.json')
    creds = None
    if exists(creds_path):
        with open(creds_path, 'r') as f:
            creds = json.load(f)
        expiration_str = creds['Expiration']
        expiration = parse(expiration_str)

        now = datetime.now(timezone.utc)
        if expiration <= now:
            log(f"{profile_name}: cached creds at {creds_path} expired at {expiration_str}; removing:")
            if not quiet:
                json.dump(creds, stderr)
            log()
            remove(creds_path)
            creds = None
        else:
            log(f"{profile_name}: using cached creds from {creds_path}")
    else:
        log(f"{profile_name}: no cached creds found at {creds_path}")

    if not creds:
        config = ConfigParser()
        config.read(expanduser('~/.aws/config'))
        profile_key = f'profile {profile_name}'
        profile = config[profile_key]
        creds = None
        if 'role_arn' in profile:
            role_arn = profile['role_arn']
            source_profile = profile.get('source_profile')
            if source_profile:
                source_envs = { 'AWS_PROFILE': source_profile }
            else:
                source_envs = {**environ}
                del source_envs['AWS_PROFILE']

            if not session_name:
                user = getuser()
                session_name = f'{user}-{profile_name}'
            resp = run_json(
                f'aws sts assume-role --role-arn {role_arn} --role-session-name {session_name}',
                log=log,
                envs=source_envs,
            )
            creds = resp['Credentials']
        elif 'mfa_serial' in profile:
            mfa_serial = profile['mfa_serial']
            source_profile = profile.get('source_profile')
            if source_profile:
                source_envs = { 'AWS_PROFILE': source_profile }
            else:
                source_envs = {**environ}
                del source_envs['AWS_PROFILE']
            creds_config_path = join(dirname(creds_dir), DEFAULT_CREDS_CONFIG_NAME)
            with open(creds_config_path, 'r') as f:
                creds_config = yaml.safe_load(f)
            mfa_configs = creds_config['mfa']
            mfa_cmd = None
            for mfa_config in mfa_configs:
                if mfa_config['arn'] == mfa_serial:
                    mfa_cmd = mfa_config['cmd']
                    break
            if not mfa_cmd:
                raise RuntimeError(f"No MFA config found in {creds_config_path} for ARN {mfa_serial}")
            mfa_code = run(mfa_cmd, log=log)
            log(f"MFA code: {mfa_code}")
            resp = run_json(
                f'aws sts get-session-token --duration-seconds 43200 --serial-number {mfa_serial} --token-code {mfa_code}',
                log=log,
                envs=source_envs,
            )
            creds = resp['Credentials']
        if creds:
            log(f"Saving credentials to {creds_path}:")
            if not quiet:
                json.dump(creds, stderr)
            log()
            makedirs(creds_dir, exist_ok=True)
            with open(creds_path, 'w') as f:
                json.dump(creds, f, indent=2)
    return creds


@command("aws-creds.py")
@option('-d', '--creds-dir', default=DEFAULT_CREDS_DIR)
@option('-o', '--output-format', default='json')
@option('-q', '--quiet', is_flag=True)
@option('-s', '--session-name')
@argument("profile", required=False)
def main(
    creds_dir: str,
    output_format: str | None,
    quiet: bool,
    session_name: str | None,
    profile: str,
):
    """AWS credentials helper, suitable for use as `credentials_process` in one or more `[profile …]` sections of ~/.aws/config.

    Caches credentials in `~/.aws/creds/<profile>.json`.
    """
    creds = load_creds(
        creds_dir=creds_dir,
        quiet=quiet,
        session_name=session_name,
        profile_name=profile,
    )
    if output_format in ['s', 'sh', 'shell']:
        envs = creds_to_envs(creds)
        for k, v in envs.items():
            print(f"export {k}='{v}'")
    elif output_format in ['j', 'json']:
        creds['Version'] = 1
        json.dump(creds, stdout, indent=2)
        print()


if __name__ == '__main__':
    main()
