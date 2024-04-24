#!/usr/bin/env python
import boto3
from click import *


@command()
@option('-h', '--https', is_flag=True, help='Allow HTTPS ingress')
@option('-s', '--ssh', is_flag=True, help='Allow SSH ingress')
@argument('id')
def main(https, ssh, id):
    ingress_rules = []
    if ssh:
        ingress_rules.append({
            'IpProtocol': 'tcp',
            'FromPort': 22,
            'ToPort': 22,
            'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
        })
    if https:
        ingress_rules.append({
            'IpProtocol': 'tcp',
            'FromPort': 443,
            'ToPort': 443,
            'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
        })

    if not ingress_rules:
        echo('No ingress rules specified')
        return

    session = boto3.Session()
    ec2 = session.client('ec2')
    try:
        ec2.authorize_security_group_ingress(
            GroupId=id,
            IpPermissions=ingress_rules
        )
    except Exception as e:
        echo(f"Failed to add ingress rules: {e}")
    else:
        echo(f"Added ingress rules to security group {id}")


if __name__ == '__main__':
    main()
