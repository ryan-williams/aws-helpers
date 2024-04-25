#!/usr/bin/env python
from sys import stderr

import boto3
from click import argument, command, echo, option


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
    print(f"Security Group Created: {security_group_id}")

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
@option('-a', '--ami-id', required=True, help='The AMI ID to use for the instance.')
@option('-c', '--count', default=1, type=int, help='The number of instances to launch.')
@option('-d', '--device-name', default='/dev/sda1', help='The device name for the root volume.')
@option('-g', '--security-group', help='The security group to use for the instance; one will ')
@option('--security-group-description', help='The description of the security group (if one is created).')
@option('--security-group-name', help='The name of the security group (if one is created).')
@option('-H', '--no-https-ingress', is_flag=True, help='Do not allow HTTPS ingress traffic.')
@option('-k', '--key-name', help='The name of the key pair to use.')
@option('-n', '--name', help='The name of the instance.')
@option('-p', '--profile', help='The AWS profile to use.')
@option('-r', '--region', help='The region to use.')
@option('-s', '--size', type=int, default=256, help='The size of the root volume (in GB).')
@option('-t', '--tags', multiple=True, help='The tags to apply to the instance.')
@option('-T', '--no-delete-on-termination', is_flag=True, help='Do not delete the root volume on termination.')
@option('-v', '--vpc-id', help='The VPC ID to use for the security group.')
@option('--volume-type', default='gp3', help='The volume type for the root volume.')
@argument('instance-type')
def main(
        ami_id,
        count,
        device_name,
        security_group,
        security_group_description,
        security_group_name,
        no_https_ingress,
        key_name,
        name,
        profile,
        region,
        size,
        tags,
        no_delete_on_termination,
        vpc_id,
        volume_type,
        instance_type,
):
    """Launch an EC2 instance."""
    session = boto3.Session(profile_name=profile, region_name=region)
    ec2 = session.client('ec2')

    if not security_group:
        if not security_group_name:
            security_group_name = f'{name}-sg'
        if not security_group_description:
            security_group_description = f'Security group for instance {name}, allowing SSH{"" if no_https_ingress else "and HTTPS"} ingress'
        security_group = create_security_group(
            ec2,
            vpc_id=vpc_id,
            name=security_group_name,
            description=security_group_description,
            https_ingress=not no_https_ingress,
        )

    response = ec2.run_instances(
        ImageId=ami_id,
        InstanceType=instance_type,
        KeyName=key_name,
        MinCount=count,
        MaxCount=count,
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

    instance_ids = [instance['InstanceId'] for instance in response['Instances']]
    echo(f'Launched instance(s): {", ".join(instance_ids)}')


if __name__ == '__main__':
    main()
