#!/bin/bash
#
# usage: build-test-repo.sh [ topdir ]

set -e

PATH=/bin:/usr/bin

# The default top directory is the same as in zstore.yaml
topdir=${1:-/tmp/zstore}

# The top directory for the v1 registry
v1regdir="$topdir"/registry/v1

# This script will generate a fake image store with the layout like below:
#
# registry/v1/
# └── blobs/
# │   ├── 5f
# │   │   └── 3b8cd435fa ...   (sha256)
# │   └── a8
# │       └── 7dea4c293b ...
# │
# └── repos/
#     └── ubuntu
#         └── manifests
#             ├── revisions
#             │   ├─ Image-Id1 (sha1)
#             │   │  └─ json   (image metadata)
#             │   │
#             │   └─ Image-Id2
#             │      └─ json
#             └── tags
#                 ├─ latest    (contains image id)
#                 └─ v3.14

# Create the directories
blobdir="$v1regdir/blobs"
name="ubuntu"
mnftdir="$v1regdir/repos/$name/manifests"
mkdir -p "$blobdir" "$mnftdir"

# get-image-blobname (digest) => fullpath
get-image-blobname () {
    if test $# -ne 1; then
        echo "get-image-blobname: missing image digest"
        exit 1
    fi

    local digest="$1"
    local head=$(expr substr "$digest" 1 2)
    local tail=$(expr substr "$digest" 3 62)

    echo "$blobdir/$head/$tail"
}

# get-file-digest (filename) => digest
get-file-digest () {
    if test $# -ne 1; then
        echo "get-file-digest: missing file name"
        exit 1
    fi

    sha256sum "$1" | awk '{print $1}'
}

# move-image-to-store (filename) => image-digest
move-image-to-store () {
    if test $# -ne 1; then
        echo "move-image-to-store: missing file name"
        exit 1
    fi

    local fname="$1"
    local digest=$(sha256sum "$fname" | awk '{print $1}')
    local blobname=$(get-image-blobname "$digest")

    mkdir -p $(dirname "$blobname")
    mv -f "$fname" "$blobname"
    echo $digest
}

# add-image () => image-digest
add-image () {
    local fname=$(tempfile)

    qemu-img create -q -f qcow2 "$fname" 10m
    move-image-to-store "$fname"
}

# add-child-image (parent-image-digest) => child-image-digest
add-child-image () {
    if test $# -ne 1; then
        echo "add-child-image: missing image digest"
        exit 1
    fi

    local parent=$(get-image-blobname "$1")
    local child=$(tempfile)

    # create a hard link from the parent image
    ln "$parent" "$1"
    qemu-img create -q -f qcow2 -b "$1" "$child" 10m

    # unlink the hard link
    unlink "$1"

    move-image-to-store "$child"
}

# build-image-json (digest) => image-id
build-image-json () {
    if test $# -ne 1; then
        echo "build-image-json: missing image digest"
        exit 1
    fi

    local imgid=$(echo -n $name $1 | sha1sum | awk '{print $1}')
    local jsdir="$mnftdir/revisions/$imgid"

    mkdir -p "$jsdir"
    cat > "$jsdir/json" <<EOF
{
  "id": "$imgid",
  "blobsum": "$1",
  "created": "2016-03-28T21:19:18.674353812Z",
  "author": "Alyssa P. Hacker",
  "architecture": "amd64",
  "size": 271828,
  "name": "$name",
  "desc": "An $name image"
}
EOF
    echo "$imgid"
}

# build-image-json-with-parent (digest, parent-image-id) => image-id
build-image-json-with-parent () {
    if test $# -ne 2; then
        echo "build-image-json: invalid arguments - $@"
        exit 1
    fi

    local imgid=$(echo -n $name $1 | sha1sum | awk '{print $1}')
    local jsdir="$mnftdir/revisions/$imgid"

    mkdir -p "$jsdir"
    cat > "$jsdir/json" <<EOF
{
  "id": "$imgid",
  "blobsum": "$1",
  "parents": [ "$2" ],
  "created": "2016-03-28T21:19:18.674353812Z",
  "author": "Alyssa P. Hacker",
  "architecture": "amd64",
  "size": 171828,
  "name": "$name",
  "desc": "A derived $name image"
}
EOF
    echo "$imgid"
}

# add-tag (image-id, tag)
add-tag () {
    if test $# -ne 2; then
        echo "add-tag: invalid argument - $@"
        exit 1
    fi

    mkdir -p "$mnftdir/tags"
    echo $1 > "$mnftdir/tags/$2"
}

parent=$(add-image)
child=$(add-child-image "$parent")

parentId=$(build-image-json "$parent")
childId=$(build-image-json-with-parent "$child" "$parentId")

add-tag "$parentId" p0
add-tag "$childId"  c0

# vim: set et ts=4 sw=4 ai:
