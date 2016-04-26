package storage

import (
	"fmt"
	"path"
)

const (
	storagePathRoot    = "/registry"
	storagePathVersion = "v1"
	chunkNamePrefix    = "chunk-"
)

var rootPrefix = path.Join(storagePathRoot, storagePathVersion)

// The path layout in the storage backend is roughly as the following:
//
// registry/v1/
//  ├── blob-manifests/
//  │   ├── 63
//  │   │   └── 579fa6c44e (blob json)
//  │   │
//  │   └── b0
//  │       └── 4a8ddf3219
//  │
//  ├── blobs/
//  │   ├── 5f
//  │   │   └── 3b8cd435fa (chunk of qcow2 image file)
//  │   │
//  │   └── a8
//  │       └── 7dea4c293b
//  │
//  └── repos/
//      ├── ubuntu
//      │   └── manifests
//      │       ├── revisions
//      │       │   ├─ Image-Id1
//      │       │   │  └─ json (image manifest)
//      │       │   │
//      │       │   └─ Image-Id2
//      │       │      └─ json
//      │       ├── tags
//      │       │   ├─ latest (contains image id)
//      │       │   └─ v3.14
//      │       │
//      │       └── uploads
//      │           └─ <uuid>
//      │              ├─ data (accumulative uploaded data)
//      │              ├─ checksum (sha256:....)
//      │              └─ started-time (of current chunk)
//      ├── fedora
//      │   └── ...
//      │
//      └── david/gentoo
//          └── ...

type pathSpec interface {
	pathSpec() string
}

type urlSpec interface {
	urlSpec() string
}

// The pathSpec for blob digest
type blobDigestPathSpec struct {
	digest string
}

func (ps blobDigestPathSpec) pathSpec() string {
	return path.Join(rootPrefix, "blobs", ps.digest[:2], ps.digest[2:], "json")
}

// The pathSpec for blob chunks
type blobChunkPathSpec struct {
	digest  string
	subhash string
}

func (ps blobChunkPathSpec) pathSpec() string {
	return path.Join(rootPrefix, "blobs", ps.digest[:2], ps.digest[2:], ps.subhash)
}

// TODO get the "user" value from somewhere
// The pathSpec for image manifests
type manifestsPathSpec struct {
	user string // the user (can be empty)
	name string // image name
}

func (ps manifestsPathSpec) pathSpec() string {
	return path.Join(rootPrefix, "repos", ps.user, ps.name, "manifests")
}

// The pathSpec for the tags directory
type tagsPathSpec struct {
	user string
	name string
}

func (ps tagsPathSpec) pathSpec() string {
	mps := manifestsPathSpec{user: ps.user, name: ps.name}.pathSpec()
	return path.Join(mps, "tags")
}

// The pathSpec for the revisions directory
type revsPathSpec struct {
	user string
	name string
}

func (ps revsPathSpec) pathSpec() string {
	mps := manifestsPathSpec{user: ps.user, name: ps.name}.pathSpec()
	return path.Join(mps, "revisions")
}

// The image JSON  pathSpec
type imageJsonPathSpec struct {
	user string
	name string
	id   string // image id
}

func (ps imageJsonPathSpec) pathSpec() string {
	mps := manifestsPathSpec{user: ps.user, name: ps.name}.pathSpec()
	return path.Join(mps, "revisions", ps.id, "json")
}

// the tag pathSpec
type tagPathSpec struct {
	user string
	name string
	tag  string // tag name
}

func (ps tagPathSpec) pathSpec() string {
	mps := manifestsPathSpec{user: ps.user, name: ps.name}.pathSpec()
	return path.Join(mps, "tags", ps.tag)
}

// the uploads pathSpec
type uploadsPathSpec struct {
	user string
	name string
}

func (ps uploadsPathSpec) pathSpec() string {
	mps := manifestsPathSpec{user: ps.user, name: ps.name}.pathSpec()
	return path.Join(mps, "uploads")
}

// the upload uuid pathSpec
type uploadUuidPathSpec struct {
	user string
	name string
	id   string // uuid
}

func (ps uploadUuidPathSpec) pathSpec() string {
	ups := uploadsPathSpec{user: ps.user, name: ps.name}.pathSpec()
	return path.Join(ups, ps.id)
}

func (ps uploadUuidPathSpec) urlSpec() string {
	u := path.Join("/", storagePathVersion, ps.name, "blobs", "uploads", ps.id)
	return u
}

// the upload info pathSpec
type uploadInfoPathSpec struct {
	user string
	name string
	id   string // uuid
}

func (ps uploadInfoPathSpec) pathSpec() string {
	ups := uploadsPathSpec{user: ps.user, name: ps.name}.pathSpec()
	return path.Join(ups, ps.id, "upload-info")
}

// the upload check sum pathSpec
type uploadChunkPathSpec struct {
	user  string
	name  string
	id    string // uuid
	index int
}

func (ps uploadChunkPathSpec) pathSpec() string {
	ups := uploadsPathSpec{user: ps.user, name: ps.name}.pathSpec()
	return path.Join(ups, ps.id, fmt.Sprintf("%s%d", chunkNamePrefix, ps.index))
}
