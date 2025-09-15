#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "boto3",
#     "click",
# ]
# ///
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
    cmd: str | list[str],
    log: Callable[[str], None],
    env: dict[str, str] | None = None,
    envs: dict[str, str] | None = None,
) -> str:
    shell = isinstance(cmd, str)
    if envs:
        envs_str = ', '.join([ f'{k}={v}' for k, v in envs.items() ])
        log(f"Running: {cmd} ({envs_str})")
        env = env or environ
        env = { **env, **envs }
    else:
        log(f"Running: {cmd}")

    return check_output(cmd, shell=shell, env=env).decode().rstrip('\n')


def run_json(
    cmd: str | list[str],
    log: Callable[[str], None],
    env: dict[str, str] | None = None,
    envs: dict[str, str] | None = None,
) -> dict[str, str]:
    output = run(cmd=cmd, log=log, env=env, envs=envs)
    return json.loads(output)


def load_creds(
    no_cache_level: int,
    creds_dir: str,
    quiet: bool,
    session_name: str | None,
    profile_name: str,
):
    def log(msg: str):
        if not quiet:
            err(f"{profile_name}: {msg}")

    def log_json(obj, **kwargs):
        if not quiet:
            json.dump(obj, stderr, **kwargs)
            err()

    if not profile_name:
        profile_name = environ.get('AWS_PROFILE')
        if not profile_name:
            raise RuntimeError("No <profile> passed, and AWS_PROFILE not set")
    creds_path = join(creds_dir, f'{profile_name}.json')
    creds = None
    if no_cache_level:
        log(f"skipping checking for cached creds at {creds_path}")
    elif exists(creds_path):
        with open(creds_path, 'r') as f:
            creds = json.load(f)
        expiration_str = creds['Expiration']
        expiration = parse(expiration_str)

        now = datetime.now(timezone.utc)
        if expiration <= now:
            log(f"cached creds at {creds_path} expired at {expiration_str}; removing:")
            log_json(creds)
            remove(creds_path)
            creds = None
        else:
            log(f"using cached creds from {creds_path}")
    else:
        log(f"no cached creds found at {creds_path}")

    if not creds:
        config = ConfigParser()
        config.read(expanduser('~/.aws/config'))
        profile_key = f'profile {profile_name}'
        profile = config[profile_key]
        creds = None
        if 'role_arn' in profile:
            role_arn = profile['role_arn']
            duration_seconds = profile.get('duration_seconds')
            source_profile = profile.get('source_profile')
            if source_profile:
                env = None
                envs = { 'AWS_PROFILE': source_profile }
            else:
                env = {**environ}
                del env['AWS_PROFILE']
                envs = None

            if not session_name:
                user = getuser()
                session_name = f'{user}-{profile_name}'
            resp = run_json(
                [
                    'aws', 'sts', 'assume-role',
                    *(['--duration-seconds', duration_seconds] if duration_seconds else []),
                    '--role-arn', role_arn,
                    '--role-session-name', session_name,
                ],
                log=log,
                env=env,
                envs=envs,
            )
            creds = resp['Credentials']
        elif 'mfa_serial' in profile:
            mfa_serial = profile['mfa_serial']
            duration_seconds = profile.get('duration_seconds')
            source_profile = profile.get('source_profile')
            if source_profile:
                env = None
                envs = { 'AWS_PROFILE': source_profile }
            else:
                env = {**environ}
                del env['AWS_PROFILE']
                envs = None

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
            log(f"MFA code {mfa_code}")
            resp = run_json(
                [
                    'aws', 'sts', 'get-session-token',
                    *(['--duration-seconds', duration_seconds] if duration_seconds else []),
                    '--serial-number', mfa_serial,
                    '--token-code', mfa_code,
                ],
                log=log,
                env=env,
                envs=envs,
            )
            creds = resp['Credentials']
        if creds:
            if no_cache_level > 1:
                log(f"skipping writing credentials to cache path {creds_path}")
            else:
                log(f"saving credentials to {creds_path}:")
                log_json(creds)
                makedirs(creds_dir, exist_ok=True)
                with open(creds_path, 'w') as f:
                    json.dump(creds, f, indent=2)

    return creds


AWS_CREDS_NO_CACHE_LEVEL_VAR = 'AWS_CREDS_NO_CACHE_LEVEL'


@command("aws-creds.py")
@option('-C', '--no-cache', 'no_cache_level', count=True, help=f"0x: read and write creds from cache; 1x: skip reading, but write new creds; 2x: don't read or write creds. Falls back to ${AWS_CREDS_NO_CACHE_LEVEL_VAR} (should be \"0\", \"1\", or \"2\").")
@option('-d', '--creds-dir', default=DEFAULT_CREDS_DIR, help=f"Directory to cache creds in; defaults to {DEFAULT_CREDS_DIR}")
@option('-o', '--output-format', default='json', help='Output credentials as JSON ("j", "json"), shell ("s", "sh", "shell"), or env ("e", "env") formats')
@option('-q', '--quiet', is_flag=True, help="Suppress logging to stderr")
@option('-s', '--session-name', help="Session name (passed to `aws sts assume-role … --role-session-name`)")
@argument("profile", required=False)
def main(
    no_cache_level: int,
    creds_dir: str,
    output_format: str | None,
    quiet: bool,
    session_name: str | None,
    profile: str,
):
    """AWS credentials helper, suitable for use as `credentials_process` in one or more `[profile …]` sections of ~/.aws/config.

    Caches credentials in `~/.aws/creds/<profile>.json`.
    """
    if not no_cache_level:
        env_no_cache_level = environ.get(AWS_CREDS_NO_CACHE_LEVEL_VAR)
        if env_no_cache_level:
            no_cache_level = int(env_no_cache_level)
    creds = load_creds(
        no_cache_level=no_cache_level,
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
    elif output_format in ['e', 'env']:
        envs = creds_to_envs(creds)
        for k, v in envs.items():
            print(f"{k}={v}")


if __name__ == '__main__':
    main()
