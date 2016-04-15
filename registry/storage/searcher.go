package storage

import (
	"encoding/json"
	"errors"
	"fmt"
	"github.com/docker/distribution/context"
	storagedriver "github.com/docker/distribution/registry/storage/driver"
	"image-store/utils"
	"strings"
)

var NotImplemented = errors.New("not implemented")

// The image manifest
type ImageManifest struct {
	Id      string   `json:"id"`
	Parents []string `json:"parents"`
	Blobsum string   `json:"blobsum"`
	Created string   `json:"created"`
	Author  string   `json:"author"`
	Arch    string   `json:"architecture"`
	Desc    string   `json:"desc"`
	Size    int64    `json:"size"`
	Name    string   `json:"name"`
}

// Encode the image manifest to JSON string
func (imf *ImageManifest) String() string {
	buf, _ := json.Marshal(imf)
	return string(buf)
}

// Check whether an image manifest is acceptable
func (imf *ImageManifest) Ok() bool {
	if utils.ParseImageId(imf.Id) == nil {
		return false
	}

	if imf.Size == 0 {
		return false
	}

	// TODO check others
	return utils.IsDigest(imf.Blobsum)
}

// TODO add caching layer
// Names and tags etc. will be converted to lowercase
type Searcher interface {
	// Returns images found in registry, empty array if not found.
	FindImages(ctx context.Context, name string) ([]*ImageManifest, error)

	// Get the image manifest with a name and reference.
	GetManifest(ctx context.Context, name string, ref string) (*ImageManifest, error)

	// Put a image manifest
	PutManifest(ctx context.Context, name string, ref string, imf *ImageManifest) error

	// List tags under a name
	ListTags(ctx context.Context, name string) ([]string, error)
}

type ImageSearcher struct {
	driver storagedriver.StorageDriver
}

func NewSearcher(d storagedriver.StorageDriver) *ImageSearcher {
	return &ImageSearcher{driver: d}
}

func (ims ImageSearcher) FindImages(ctx context.Context, name string) ([]*ImageManifest, error) {
	return nil, NotImplemented
}

func getImageJson(ctx context.Context, d storagedriver.StorageDriver, ps string) (*ImageManifest, error) {
	buf, err := d.GetContent(ctx, ps)
	if err != nil {
		return nil, err
	}

	var imf ImageManifest
	if err = json.Unmarshal(buf, &imf); err != nil {
		return nil, err
	}

	if imf.Ok() {
		return &imf, nil
	}

	return nil, fmt.Errorf("invalid image manifest for %s", ps)
}

func (ims ImageSearcher) GetManifest(ctx context.Context, name string, ref string) (*ImageManifest, error) {
	// If the reference is a tag -
	//  1. get the digest via tag
	//  2. get the manifest via digest
	// Digest can be only first few digests - as long as there is no ambiguity.
	refstr := strings.ToLower(ref)
	mps := manifestsPathSpec{name: strings.ToLower(name)}

	if utils.IsDigest(refstr) {
		ps := imageJsonPathSpec{manifestsPathSpec: mps, id: refstr}.pathSpec()
		res, err := ims.driver.List(ctx, ps)
		if err != nil {
			if _, ok := err.(storagedriver.PathNotFoundError); ok {
				return nil, errors.New("Not found")
			}
			return nil, err
		}

		switch len(res) {
		case 1:
			return getImageJson(ctx, ims.driver, res[0])
		case 0:
			return nil, fmt.Errorf("internal error - no manifest found")
		default:
			return nil, fmt.Errorf("digest is ambiguous: %s", refstr)
		}
	}

	// ok - it is a tag
	tps := tagPathSpec{manifestsPathSpec: mps, tag: refstr}.pathSpec()
	buf, err := ims.driver.GetContent(ctx, tps)
	if err != nil {
		return nil, err
	}

	idstr := strings.ToLower(strings.TrimSpace(string(buf)))
	if utils.ParseImageId(idstr) == nil {
		return nil, fmt.Errorf("unexpected digest '%s' for tag '%s'", idstr, refstr)
	}

	ips := imageJsonPathSpec{manifestsPathSpec: mps, id: idstr}.pathSpec()
	return getImageJson(ctx, ims.driver, ips)
}

func (ims ImageSearcher) PutManifest(ctx context.Context, name string, ref string, imf *ImageManifest) error {
	// If the reference is a tag -
	//  1. put the manifest
	//  2. update the tag
	//
	// If the reference is a digest
	//  1. check whether digest matches imf.Id
	//  2. put the manifest
	refstr := strings.ToLower(ref)
	idstr := strings.ToLower(imf.Id)
	isdigest := utils.ParseImageId(refstr) != nil

	if isdigest {
		if refstr != idstr {
			return errors.New("digest and content body mismatch")
		}
	}

	// TODO check manifest content and existence
	mps := manifestsPathSpec{name: idstr}
	ps := imageJsonPathSpec{manifestsPathSpec: mps, id: idstr}.pathSpec()

	if err := ims.driver.PutContent(ctx, ps, []byte(imf.String())); err != nil {
		return errors.New("failed to update manifest")
	}

	if !isdigest {
		tps := tagPathSpec{manifestsPathSpec: mps, tag: refstr}.pathSpec()
		if err := ims.driver.PutContent(ctx, tps, []byte(idstr)); err != nil {
			return fmt.Errorf("failed to update tag '%s' with digest '%s'", refstr, idstr)
		}
	}

	return nil
}

func (ims ImageSearcher) ListTags(ctx context.Context, name string) ([]string, error) {
	mps := manifestsPathSpec{name: name}
	ps := tagsPathSpec{manifestsPathSpec: mps}.pathSpec()

	xs, err := ims.driver.List(ctx, ps)
	if err != nil {
		if _, ok := err.(storagedriver.PathNotFoundError); !ok {
			return nil, err
		}
	}

	res := make([]string, len(xs))
	for i, v := range xs {
		res[i] = strings.TrimPrefix(v, ps+"/")
	}

	return res, nil
}
