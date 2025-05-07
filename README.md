# aws-helpers
Scripts / Aliases for working with AWS.

See usage as a submodule of [runsascoded/.rc].

## [`aws-creds.py`]

`credential_process` for seamless MFA sessions and AssumeRole support in `aws`.

### `~/.aws/creds.yml` <a id="aws-creds-yml"></a>
This file provides `aws-creds.py` with commands to generate OTP codes for MFA devices (by ARN), e.g.:
```yml
mfa:
  - arn: arn:aws:iam::<account>:mfa/<device>
    cmd: op read "op://<vault>/<item>/one-time password?attribute=otp"
```

In this example, the AWS MFA has been loaded into 1Password, and [1Password CLI] is used to programmatically print OTP codes (use `op {vault,item} list` to find relevant vault and item IDs).

### `~/.aws/{config,credentials}` example <a id="aws-config"></a>
Given an access/secret keypair in `~/.aws/credentials`, for profile `base`:
```ini
[base]
aws_access_key_id=…
aws_secret_access_key=…
```

Insert the MFA device ARN into `~/.aws/config`, along with configs like e.g.:
```ini
# "base" profile + MFA
[profile mfa]
source_profile = base
mfa_serial = # ‼️ Your MFA ARN here ‼️
credential_process = aws-creds.py

# Assume role "dev-admin" from a "profile mfa" MFA session
[profile my-role]
source_profile = mfa
role_arn = arn:aws:iam::<account>:role/<role>
credential_process = aws-creds.py
```

Note the `credential_process = aws-creds.py` items.

### Test: "base" profile → MFA session → assumed role <a id="test"></a>
```bash
export AWS_PROFILE=my-role  # Requires AssumeRole from an intermediate MFA session (profile "mfa")
aws sts get-caller-identity  # ✅ Success! (after TouchID'ing into 1Password)
# {
#     "UserId": "AROAYTDQ4QDJOF3T7JZ6F:botocore-session-1746591050",
#     "Account": "<account>",
#     "Arn": "arn:aws:sts::<account>:assumed-role/<role>/botocore-session-1746591050"
# }
```

[runsascoded/.rc]: https://github.com/runsascoded/.rc
[`aws-creds.py`]: aws-creds.py
[1Password CLI]: https://developer.1password.com/docs/cli/get-started/
