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

// The pathSpec for blob digest
type blobDigestPathSpec struct {
	digest string
}

func (ps blobDigestPathSpec) pathSpec() string {
	return path.Join(rootPrefix, "blobs", ps.digest[:2], ps.digest[2:])
}

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
	manifestsPathSpec
}

func (ps tagsPathSpec) pathSpec() string {
	return path.Join(ps.manifestsPathSpec.pathSpec(), "tags")
}

// The pathSpec for the revisions directory
type revsPathSpec struct {
	manifestsPathSpec
}

func (ps revsPathSpec) pathSpec() string {
	return path.Join(ps.manifestsPathSpec.pathSpec(), "revisions")
}

// The image JSON  pathSpec
type imageJsonPathSpec struct {
	manifestsPathSpec
	id string // image id
}

func (ps imageJsonPathSpec) pathSpec() string {
	t := ps.manifestsPathSpec.pathSpec()
	return path.Join(t, "revisions", ps.id, "json")
}

// the tag pathSpec
type tagPathSpec struct {
	manifestsPathSpec
	tag string // tag name
}

func (ps tagPathSpec) pathSpec() string {
	t := ps.manifestsPathSpec.pathSpec()
	return path.Join(t, "tags", ps.tag)
}

// the uploads pathSpec
type uploadsPathSpec struct {
	manifestsPathSpec
}

func (ps uploadsPathSpec) pathSpec() string {
	t := ps.manifestsPathSpec.pathSpec()
	return path.Join(t, "uploads")
}

// the upload data pathSpec
type uploadDataPathSpec struct {
	uploadsPathSpec
	id string // uuid
}

func (ps uploadDataPathSpec) pathSpec() string {
	t := ps.uploadsPathSpec.pathSpec()
	return path.Join(t, ps.id, "data")
}

// the upload check sum pathSpec
type uploadCheckSumPathSpec struct {
	uploadDataPathSpec
}

func (ps uploadCheckSumPathSpec) pathSpec() string {
	t := ps.uploadsPathSpec.pathSpec()
	return path.Join(t, ps.id, "checksum")
}

// the upload start time pathSpec
type uploadStartTimePathSpec struct {
	uploadDataPathSpec
}

func (ps uploadStartTimePathSpec) pathSpec() string {
	t := ps.uploadsPathSpec.pathSpec()
	return path.Join(t, ps.id, "started-time")
}
