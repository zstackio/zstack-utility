package storage

import (
	"path"
)

const (
	storagePathRoot    = "/registry"
	storagePathVersion = "v1"
)

var rootPrefix = path.Join(storagePathRoot, storagePathVersion)

// The path layout in the storage backend is roughly as the following:
//
// registry/v1/
//  ├── blobs/
//  │   ├── 5f
//  │   │   └── 3b8cd435fa (qcow2 image file)
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
	return path.Join(rootPrefix, "blobs", ps.digest[:2], ps.digest[2:])
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

// the upload data pathSpec
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

// the upload data pathSpec
type uploadDataPathSpec struct {
	user string
	name string
	id   string // uuid
}

func (ps uploadDataPathSpec) pathSpec() string {
	ups := uploadsPathSpec{user: ps.user, name: ps.name}.pathSpec()
	return path.Join(ups, ps.id, "data")
}

// the upload check sum pathSpec
type uploadCheckSumPathSpec struct {
	user string
	name string
	id   string // uuid
}

func (ps uploadCheckSumPathSpec) pathSpec() string {
	ups := uploadsPathSpec{user: ps.user, name: ps.name}.pathSpec()
	return path.Join(ups, ps.id, "checksum")
}

// the upload start time pathSpec
type uploadStartTimePathSpec struct {
	user string
	name string
	id   string // uuid
}

func (ps uploadStartTimePathSpec) pathSpec() string {
	ups := uploadsPathSpec{user: ps.user, name: ps.name}.pathSpec()
	return path.Join(ups, ps.id, "started-time")
}
