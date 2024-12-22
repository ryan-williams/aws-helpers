#!/usr/bin/env bash

set -e

# echo "git-diff-dvc.sh ($#):"
# for arg in "$@"; do
#   echo "  $arg"
# done
# echo

if [ "$#" -eq 7 ]; then
  dvc_path="$1"; shift  # repo dvc_path
  if ! [[ $dvc_path =~ .dvc$ ]]; then
      echo "Error: repo dvc_path $dvc_path must end in .dvc" >&2
      exit 1
  fi
  relpath="${dvc_path%.dvc}"
  if [ "$1" == /dev/null ]; then
    md0=
    path0=/dev/null; shift
  else
    md0="$(dvc_to_md5 "$1")"; shift
    path0="$(dvc_mdf_cache_path -r "$md0")"
  fi
  hex0="$1"; shift  # old hexsha
  mode0="$1"; shift  # old filemode
  if [ "$1" == /dev/null ]; then
    md1=
    path1=/dev/null; shift
  else
    md1="$(dvc_to_md5 "$1")"; shift
    path1="$(dvc_mdf_cache_path -r "$md1")"
  fi
  hex1="$1"; shift  # new hexsha
  mode1="$1"; shift  # old filemode

  echo "$relpath"
  echo "--- $path0 $hex0"
  echo "+++ $path1 $hex1"

  if [[ $md1 = *.dir ]] || [[ $md0 = *.dir ]]; then
    set +e
    cmd=(jq 'map({ "key": .relpath, "value": .md5 }) | from_entries')
    obj0="$("${cmd[@]}" "$path0")"
    obj1="$("${cmd[@]}" "$path1")"
    diff --color=always <(echo "$obj0") <(echo "$obj1")
    (echo "$obj0"; echo "$obj1") | \
    jq -rs '
      .[0] as $first | .[1] as $second |
      (($first | keys) + ($second | keys) | unique) as $allkeys |
      $allkeys | map({ key: ., value: [$first[.] // null, $second[.] // null] }) | from_entries |
      to_entries[] |
      select(.value[0] != .value[1]) |
      [ .key, .value[0], .value[1] ] | join(" ")
    ' | while read -r rel m0 m1; do
      rel="$relpath/$rel"
      f0="$(dvc_mdf_cache_path -r "$m0")"
      f1="$(dvc_mdf_cache_path -r "$m1")"
#      echo "Recursing: $0 $rel $f0 $f1"
      echo
      echo "$rel"
      echo "--- $f0 $m0"
      echo "+++ $f1 $m1"
      "$0" "$rel" "$f0" "$f1"
    done
    exit 0
  fi
elif [ $# -eq 3 ]; then
  relpath="$1"; shift
  path0="$1"; shift
  path1="$1"; shift
else
  echo "Usage: $0 <repo dvc_path> <old version tmpfile> <old hexsha> <old filemode> <new version tmpfile> <new hexsha> <new filemode>" >&2
  exit 1
fi

tmpdir=$(mktemp -d)
cleanup() {
  # echo "Cleaning up $tmpdir" >&2
  rm -rf "$tmpdir"
}
trap cleanup EXIT

reldir="$(dirname "$relpath")"
name="$(basename "$relpath")"

tmpdir0="$tmpdir/0/$reldir"
tmpdir1="$tmpdir/1/$reldir"
mkdir -p "$tmpdir0" "$tmpdir1"
tmppath0="$tmpdir0/$name"
tmppath1="$tmpdir1/$name"
ln -s "$PWD/$path0" "$tmppath0"
ln -s "$PWD/$path1" "$tmppath1"
cmd=(git diff --no-index --ext-diff "$tmppath0" "$tmppath1")
# echo "git-diff-dvc.sh running ${cmd[*]}" >&2
set +e
"${cmd[@]}"
exit 0
