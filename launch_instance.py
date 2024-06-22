#!/usr/bin/env python
from os import chmod, environ
from os.path import exists, expanduser, join
from subprocess import check_call, CalledProcessError, Popen, PIPE
from sys import stderr

import boto3
from click import command, option


def err(*args):
    print(*args, file=stderr)


def default_vpc_id(ec2):
    """
    Get the default VPC ID for the current account.

    Parameters:
        ec2 (boto3.client): An EC2 client object.

    Returns:
        str: The default VPC ID.
    """
    response = ec2.describe_vpcs(Filters=[{'Name': 'isDefault', 'Values': ['true']}])
    vpcs = response['Vpcs']
    default_vpcs = [vpc for vpc in vpcs if vpc['IsDefault']]
    if len(default_vpcs) != 1:
        raise ValueError(f"Expected 1 default VPC, found {len(default_vpcs)}: {default_vpcs}")
    return default_vpcs[0]['VpcId']


def create_security_group(ec2, vpc_id, name, description=None, https_ingress=False):
    """
    Create a security group and set up SSH access.

    Parameters:
        ec2 (boto3.client): An EC2 client object.
        vpc_id (str): VPC ID where the security group will be created.
        name (str): Name for the new security group.
        description (str): Description of the security group.
        https_ingress (bool): Whether to allow HTTP ingress traffic.
    """
    if not vpc_id:
        vpc_id = default_vpc_id(ec2)
        err(f"Fetched default VPC ID: {vpc_id}")

    response = ec2.create_security_group(
        GroupName=name,
        Description=description,
        VpcId=vpc_id,
    )
    security_group_id = response['GroupId']
    err(f"Security Group Created: {security_group_id}")

    ssh_ingress_rule = {
        'IpProtocol': 'tcp',
        'FromPort': 22,
        'ToPort': 22,
        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
    }
    https_ingress_rule = {
        'IpProtocol': 'tcp',
        'FromPort': 443,
        'ToPort': 443,
        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
    }

    # Add a security group rule to allow SSH access
    ec2.authorize_security_group_ingress(
        GroupId=security_group_id,
        IpPermissions=[
            ssh_ingress_rule,
            *([https_ingress_rule] if https_ingress else [])
        ]
    )
    return security_group_id


@command()
@option('-A', '--ssh-hostname-alias', 'ssh_hostname_aliases', multiple=True, help='Hostname aliases to include in the generated SSH config file entry.')
@option('-a', '--ami-id', help='The AMI ID to use for the instance.')
@option('-C', '--no-copy-clipboard', is_flag=True, help='Do not copy the instance ID to the clipboard.')
@option('-d', '--device-name', help='The device name for the root volume. By default, verifies a lone EBS volume in the AMI, and uses that "DeviceName".')
@option('-g', '--security-group', help='The security group to use for the instance; one will ')
@option('--security-group-description', '--sgd', help='The description of the security group (if one is created).')
@option('--security-group-name', '--sgn', help='The name of the security group (if one is created).')
@option('-H', '--no-https-ingress', is_flag=True, help='Do not allow HTTPS ingress traffic.')
@option('-i', '--instance-type', help='The instance type to use.')
@option('-I', '--instance-id', help='Fallback to property values from this instance: AMI, key pair, security group, instance-type')
@option('-k', '--key-name', help='The name of the key pair to use.')
@option('-K', '--key-path', help='The path to the key pair file to use.')
@option('-n', '--name', help='The name of the instance (tag "Key=Name,Value=<name>").')
@option('-p', '--profile', help='The AWS profile to use.')
@option('-r', '--region', help='The region to use.')
@option('-s', '--size', type=int, default=256, help='The size of the root volume (in GB).')
@option('-S', '--ssh-dir', default='~/.ssh', help='The directory to store the key pair in (if one is created). Default: `~/.ssh`')
@option('-t', '--tags', multiple=True, help='The tags to apply to the instance.')
@option('-T', '--no-delete-on-termination', is_flag=True, help='Do not delete the root volume on termination.')
@option('-u', '--ssh-user', help='The SSH user to use for the instance. Default: `ec2-user` on Amazon Linux, `ubuntu` on Ubuntu.')
@option('-v', '--vpc-id', help='The VPC ID to use for the security group.')
@option('--volume-type', default='gp3', help='The volume type for the root volume.')
def main(
        ssh_hostname_aliases,
        ami_id,
        no_copy_clipboard,
        device_name,
        security_group,
        security_group_description,
        security_group_name,
        no_https_ingress,
        instance_type,
        instance_id,
        key_name,
        key_path,
        name,
        profile,
        region,
        size,
        ssh_dir,
        tags,
        no_delete_on_termination,
        ssh_user,
        vpc_id,
        volume_type,
):
    """Launch an EC2 instance."""
    session = boto3.Session(profile_name=profile, region_name=region)
    ec2 = session.client('ec2')

    _instance = None

    def instance():
        nonlocal instance_id
        nonlocal _instance
        if _instance is None:
            if not instance_id:
                raise ValueError("No instance ID provided")
            response = ec2.describe_instances(InstanceIds=[instance_id])
            [reservation] = response['Reservations']
            [_instance] = reservation['Instances']
        return _instance

    if not ami_id:
        ami_id = instance()['ImageId']
        err(f"Using AMI from instance {instance_id}: {ami_id}")

    _image = None

    def image():
        nonlocal ami_id
        nonlocal _image
        if _image is None:
            if not ami_id:
                raise ValueError("No AMI ID provided")
            response = ec2.describe_images(ImageIds=[ami_id])
            [_image] = response['Images']
        return _image

    if not instance_type:
        instance_type = instance()['InstanceType']
        err(f"Using instance type from instance {instance_id}: {instance_type}")

    if not name:
        user = environ.get('EC2_USERNAME') or environ['USER']
        if not user:
            raise ValueError("Could not determine username from environment variables (EC2_USERNAME, USER)")
        name = f"{user}-{instance_type}"
        err(f"Using instance name: {name}")

    ssh_dir = expanduser(ssh_dir)
    if not key_name:
        if instance_id:
            key_name = instance()['KeyName']
            err(f"Using key pair from instance {instance_id}: {key_name}")
        else:
            if key_path:
                raise ValueError("Would Create new key pair, but -K/--key-path was provided ")
            key_name = f"{name}.pem"
            key_path = join(ssh_dir, key_name)
            if exists(key_path):
                raise ValueError(f"Key pair file already exists: {key_path}")
            response = ec2.create_key_pair(KeyName=key_name, KeyType='ed25519')
            key_material = response['KeyMaterial']
            with open(key_path, 'w') as f:
                f.write(key_material)
            chmod(key_path, 0o600)
            err(f"Created key pair {key_name} at {key_path}")

    if not security_group:
        if instance_id:
            [security_group] = instance()['SecurityGroups']
            security_group = security_group['GroupId']
            err(f"Using security group from instance {instance_id}: {security_group}")
        else:
            if not security_group_name:
                security_group_name = f'{name}-sg'
            if not security_group_description:
                security_group_description = f'Security group for instance {name}'
            security_group = create_security_group(
                ec2,
                vpc_id=vpc_id,
                name=security_group_name,
                description=security_group_description,
                https_ingress=not no_https_ingress,
            )

    if not device_name:
        bdms = image()['BlockDeviceMappings']
        ebs_mappings = [ bdm for bdm in bdms if 'Ebs' in bdm ]
        if len(ebs_mappings) != 1:
            raise ValueError(f"Expected 1 'Ebs' block device mapping, found {len(ebs_mappings)}: {ebs_mappings}")
        device_name = ebs_mappings[0]['DeviceName']
        err(f"Using device name from AMI EBS mapping: {device_name}")

    response = ec2.run_instances(
        ImageId=ami_id,
        InstanceType=instance_type,
        KeyName=key_name,
        MinCount=1,
        MaxCount=1,
        SecurityGroupIds=[security_group] if security_group else [],
        TagSpecifications=[
            {
                'ResourceType': 'instance',
                'Tags': [
                    {'Key': k, 'Value': v}
                    for k, v in (
                        tag.split('=', 1)
                        for tag in [ *tags, f"Name={name}" ]
                    )
                ],
            },
        ],
        BlockDeviceMappings=[
            {
                'DeviceName': device_name,
                'Ebs': {
                    'VolumeSize': int(size),
                    'DeleteOnTermination': not no_delete_on_termination,
                    'VolumeType': volume_type,
                },
            },
        ] if size else [],
    )

    [instance_id] = [instance['InstanceId'] for instance in response['Instances']]
    err(f'Launched instance:')
    print(instance_id)

    if not ssh_user:
        image_name = image()['Name']
        if image_name.startswith('ubuntu'):
            ssh_user = 'ubuntu'
        elif image_name.startswith('amzn'):
            ssh_user = 'ec2-user'
        else:
            raise ValueError(f"Could not determine SSH user from AMI {ami_id} (name: {image_name})")

    ssh_config_path = join(ssh_dir, 'config')
    with open(ssh_config_path, 'a') as f:
        ssh_config_entry = (f"""
Host {" ".join((instance_id,) + ssh_hostname_aliases)}
    # {instance_type}, AMI {ami_id}
    # Each instance run, update this file with the instance's dynamic PublicDnsName via: `ec2-ssh-hostname {instance_id}`
    Include ~/.ssh/include/{instance_id}
    User {ssh_user}
    IdentitiesOnly yes
    IdentityFile {key_path}
    StrictHostKeyChecking no
    ForwardAgent yes
""")
        f.write(ssh_config_entry)
        err(f"Appended to {ssh_config_path}:")
        err(ssh_config_entry)

    err(f"Fetching PublicDnsName + writing to ~/.ssh/include/{instance_id}:")
    check_call(['ec2-ssh-hostname', instance_id], stdout=stderr)
    if not no_copy_clipboard:
        try:
            proc = Popen(['xclip', '-selection', 'clipboard'], stdin=PIPE)
            proc.communicate(input=instance_id.encode())
        except FileNotFoundError:
            try:
                proc = Popen(['pbcopy'], stdin=PIPE)
                proc.communicate(input=instance_id.encode())
            except FileNotFoundError:
                err("Could not copy instance ID to clipboard: xclip and pbcopy not found")


if __name__ == '__main__':
    main()
