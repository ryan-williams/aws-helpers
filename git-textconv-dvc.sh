#!/usr/bin/env bash

set -e

err() {
  echo "$0: $*" >&2
}
# err "$0 ($#):"
# for arg in "$@"; do
#   err "  $arg"
# done
# err

if [ $# -eq 1 ]; then
  dvc_path="$1"; shift
  md5="$(dvc_to_md5 "$dvc_path")"
  path="${dvc_path%.dvc}"
  name="$(basename "$path")"
  blob_path="$(dvc_mdf_cache_path -r "$md5")"
  if [ -z "$blob_path" ]; then
    err "Error: dvc_path $dvc_path not found" >&2
    exit 1
  fi
  if [[ $md5 = *.dir ]]; then
    jq -r '.[] | [.relpath, .md5] | join(" ")' "$blob_path" | \
    if which parallel &>/dev/null; then
      parallel -k --colsep ' ' "$0" "\$(basename "$path/"'{1}'"")" "\$(dvc_mdf_cache_path -r {2})"
    else
      while read -r rel m; do
        rel="$path/$rel"
        f="$(dvc_mdf_cache_path -r "$m")"
        n="$(basename "$rel")"
        # err "Recursing: $rel $f"
        "$0" "$n" "$f"
      done
    fi
    exit 0
  fi
elif [ $# -eq 2 ]; then
  # path="$1"; shift
  name="$1"; shift
  blob_path="$1"; shift
  # md5="$1"; shift
else
  err "Usage: $0 <dvc_path>" >&2
  err "Usage: $0 <basename> <blob_path>" >&2
  exit 1
fi

echo
echo "$name" "$blob_path"
diff_driver=$(git check-attr diff "$name" | sed -E 's/.*: diff: (.*)/\1/')
if [ "$diff_driver" != "unset" ] && [ "$diff_driver" != "unspecified" ]; then
  textconv_cmd="$(git config "diff.${diff_driver}.textconv")"
  if [ -n "$textconv_cmd" ]; then
    # echo "Running:"
    $textconv_cmd "$blob_path"
    exit $?
  fi
fi

if file -b --mime-encoding "$blob_path" | grep -q binary; then
  echo "Binary file: $blob_path"
  exit 0
else
  cat "$blob_path"
fi
