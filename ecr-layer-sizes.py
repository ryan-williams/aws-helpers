#!/usr/bin/env python
import json
import shlex
from subprocess import check_output
from sys import stderr

import click


@click.command()
@click.option('-h', '--human-readable', is_flag=True)
@click.option('-v', '--verbose', count=True)
@click.argument('image')
def main(human_readable, verbose, image):
    pcs = image.split(':')
    if len(pcs) == 2:
        [ repo, tag ] = pcs
    elif len(pcs) == 1:
        repo, tag = pcs[0], 'latest'
    else:
        raise ValueError(f"Unrecognized image: {image}")

    cmd = [
        'aws', 'ecr', 'batch-get-image',
        '--repository-name', repo,
        '--image-ids', f'imageTag={tag}',
    ]
    if verbose:
        stderr.write(f'Running: {shlex.join(cmd)}\n')
    res = json.loads(check_output(cmd).decode())
    [img] = res['images']
    manifest = json.loads(img['imageManifest'])
    layer_sizes = [
        layer['size']
        for layer in manifest['layers']
    ]
    total_size = sum(layer_sizes)

    def fmt(size):
        if human_readable:
            from humanize import naturalsize
            return naturalsize(size, gnu=True)
        else:
            return str(size)

    if verbose:
        print('\n'.join(map(fmt, layer_sizes)))
        print(f'Total: {fmt(total_size)}')
    else:
        print(fmt(total_size))


if __name__ == '__main__':
    main()

# cellranger-run 6.8G 15G 7.2G 15G
# cellranger-qc 2.3G 5.9G 2.6G 6.3G
# star-run 1.9G 5.1G 2.3G 5.5G
# somalier-run 644.7M 1.9G 711.1M 1.9G
# fastqc-run 807.8M 2.4G 877.7M 2.5G
# interop-run 741.5M 2.3G 811.4M 2.4G
# sample_aware-run 1.9G 5.1G 2.3G 5.6G

# somalier-run 644.7M 1.9G
# interop-run 741.5M 2.3G
# fastqc-run 807.8M 2.4G
# sample_aware-run 1.9G 5.1G
# star-run 1.9G 5.1G
# cellranger-qc 2.3G 5.9G
# cellranger-run 6.8G 15G
