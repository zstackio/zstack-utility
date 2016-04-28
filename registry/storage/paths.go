package storage

import (
	"fmt"
	"path"
	"regexp"
	"strconv"
	"strings"
)

const (
	storagePathRoot    = "/registry"
	storagePathVersion = "v1"

	chunkNamePrefix  = "chunk"
	chunkExistPrefix = "exist"
)

var (
	rootPrefix = path.Join(storagePathRoot, storagePathVersion)
	repoPrefix = path.Join(rootPrefix, "repos")
)

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
//      │              ├─ upload-info
//      │              ├─ chunk-1-<digest>
//      │              ├─ ...
//      │              └─ chunk-n-<digest>
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

// The pathSpec for blob manifest
type blobManifestPathSpec struct {
	digest string
}

func (ps blobManifestPathSpec) pathSpec() string {
	return path.Join(rootPrefix, "blob-manifests", ps.digest[:2], ps.digest[2:])
}

// The pathSpec for blob chunks
type blobChunkPathSpec struct {
	subhash string
}

func (ps blobChunkPathSpec) pathSpec() string {
	return path.Join(rootPrefix, "blobs", ps.subhash[:2], ps.subhash[2:])
}

// TODO get the "user" value from somewhere
// The pathSpec for image manifests
type manifestsPathSpec struct {
	user string // the user (can be empty)
	name string // image name
}

func (ps manifestsPathSpec) pathSpec() string {
	return path.Join(repoPrefix, ps.user, ps.name, "manifests")
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

// the upload chunk pathSpec
//
// It can be in two forms, depending on whether the chunk exists or not.
//  if not exists: upload-uuid-pathspec/chunk-1-d64c8e8e
//  if exists:     upload-uuid-pathspec/exist-2-11401362
type uploadChunkPathSpec struct {
	user    string
	name    string
	id      string // uuid
	index   int
	subhash string
	exist   bool
}

func getChunkPrefix(exist bool) string {
	if exist {
		return chunkExistPrefix
	}
	return chunkNamePrefix
}

func (ps uploadChunkPathSpec) pathSpec() string {
	ups := uploadsPathSpec{user: ps.user, name: ps.name}.pathSpec()
	prefix := getChunkPrefix(ps.exist)
	return path.Join(ups, ps.id, fmt.Sprintf("%s-%d-%s", prefix, ps.index, ps.subhash))
}

type ChunkInfo struct {
	index   int
	subhash string
	exist   bool
}

// Parse the 'chunkps'
// /registry/v1/repos/[user/]name/manifests/uploads/uuid/chunk-1-d64c8e8e
func parseChunkPathSpec(chunkps string) (*uploadChunkPathSpec, error) {
	items := strings.Split(path.Base(chunkps), "-")
	if len(items) != 3 {
		return nil, fmt.Errorf("unexpected chunk pathspec: '%s'", chunkps)
	}

	var ucps uploadChunkPathSpec
	switch items[0] {
	case chunkNamePrefix:
		ucps.exist = false
	case chunkExistPrefix:
		ucps.exist = true
	default:
		return nil, fmt.Errorf("unexpected chunk pathspec prefix: '%s'", chunkps)
	}

	idx, err := strconv.Atoi(items[1])
	if err != nil {
		return nil, fmt.Errorf("unexpected chunk pathspec index: '%s': %s", chunkps, err)
	}

	ucps.index = idx
	ucps.subhash = items[2]

	re := regexp.MustCompile(repoPrefix + `((/\w+){1,2})` + "/manifests/uploads/" + `(.*)`)
	res := re.FindStringSubmatch(path.Dir(chunkps))
	if len(res) != 4 {
		return nil, fmt.Errorf("unexpected chunk pathspec: '%s'", chunkps)
	}

	ucps.id = res[3]

	// res[1] might contain something like "/ubuntu", or "/david/ubuntu"
	xs := strings.Split(res[1][1:], "/")
	switch len(xs) {
	case 1:
		ucps.name = xs[0]
	case 2:
		ucps.user, ucps.name = xs[0], xs[1]
	default:
		return nil, fmt.Errorf("unexpected chunk pathspec uname: '%s'", chunkps)
	}

	return &ucps, nil
}
