#!/usr/bin/env bash

if [ "$#" -ne 7 ]; then
    echo "Usage: $0 <repo relpath> <old version tmpfile> <old hexsha> <old filemode> <new version tmpfile> <new hexsha> <new filemode>" >&2
    exit 1
fi

path="$1"; shift  # repo relpath
pqt0="$(dvc_local_cache_path -r "$1")"; shift
hex0="$1"; shift  # old hexsha
mode0="$1"; shift  # old filemode
pqt1="$(dvc_local_cache_path -r "$1")"; shift
hex1="$1"; shift  # new hexsha
mode1="$1"; shift  # old filemode

parquet-diff.sh "$path" "$pqt0" "$hex0" "$mode0" "$pqt1" "$hex1" "$mode1"
