#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "boto3",
#     "click",
# ]
# ///
import boto3
from click import *


@command()
@argument('instance_id')
@argument('security_group_id')
def main(instance_id, security_group_id):
    ec2 = boto3.client('ec2')
    instance = ec2.describe_instances(InstanceIds=[instance_id])
    # aws ec2 modify-network-interface-attribute --network-interface-id $eni --groups sg-047567708e7574f0b
    print(instance)
    # network_interface_id = '"Reservations[*].Instances[*].NetworkInterfaces[*].NetworkInterfaceId"'
    # ec2.modify_instance_attribute(
    #     InstanceId=instance_id,
    #     Groups=[security_group_id]
    # )
    # echo(f"Changed security group for instance {instance_id} to {security_group_id}")


if __name__ == '__main__':
    main()
