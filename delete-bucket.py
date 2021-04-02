#!/usr/bin/env python

from argparse import ArgumentParser
import boto3

session = boto3.Session()
s3 = session.resource(service_name='s3')
parser = ArgumentParser()
parser.add_argument('-N','--no-dry-run',action='store_true',help='Actually execute deletions; by default, run in "dry run" mode: print summary info about objects/versions to be deleted and exit without performing any deletions')
parser.add_argument('bucket',nargs='+',help='Buckets to delete all objects+versions from')
args = parser.parse_args()
buckets = args.bucket
dry_run = not args.no_dry_run
if dry_run:
    print('Running in "dry run" mode; use -N to bypass "dry run" mode and actually perform deletions')
for bucket in buckets:
    if dry_run:
        print(f'Simulating bucket deletion: {bucket}')
    else:
        print(f'Deleting bucket, objects, and versions: {bucket}')
    bucket = s3.Bucket(bucket)
    object_versions = bucket.object_versions
    num_object_versions = len(list(object_versions.iterator()))
    objects = bucket.objects
    num_objects = len(list(objects.iterator()))
    if dry_run:
        print(f'Would delete: {num_object_versions} object versions')
    else:
        bucket.Versioning().suspend()
        print('Suspended versioning')
        resp = object_versions.delete()
        num_deleted = sum(len(p['Deleted']) for p in resp)
        print(f'{num_deleted} deleted versions across {len(resp)} pages')
        resp = bucket.objects.delete()
        num_deleted = sum(len(p['Deleted']) for p in resp)
        print(f'{num_deleted} deleted objects across {len(resp)} pages')
        print('Deleting bucket…')
        bucket.delete()
