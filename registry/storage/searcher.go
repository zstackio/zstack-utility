package storage

import (
	"errors"
	"fmt"
	"github.com/docker/distribution/context"
	storagedriver "github.com/docker/distribution/registry/storage/driver"
	"image-store/registry/api/errcode"
	"image-store/registry/api/v1"
	"image-store/utils"
	"io"
	"strings"
	"time"
)

// TODO add caching layer
// Names and tags etc. will be converted to lowercase
type Searcher interface {
	// Returns images found in registry, empty array if not found.
	FindImages(ctx context.Context, name string) ([]*v1.ImageManifest, error)

	// Get the image manifest with a name and reference.
	GetManifest(ctx context.Context, name string, ref string) (*v1.ImageManifest, error)

	// Put a image manifest
	PutManifest(ctx context.Context, name string, ref string, imf *v1.ImageManifest) error

	// List tags under a name
	ListTags(ctx context.Context, name string) ([]string, error)

	// Get the blob reader
	GetBlobPathSpec(name string, digest string) (string, error)

	// Prepare blob upload
	PrepareBlobUpload(ctx context.Context, name string, info *v1.UploadInfo) (string, error)

	// Get uploaded chunk size
	GetUploadedSize(ctx context.Context, name string, uu string) (int64, error)

	// Cancel the upload
	CancelUpload(ctx context.Context, name string, uu string) error

	// Complete the upload
	CompleteUpload(ctx context.Context, name string, uu string) error

	// Get a writer closer instance
	GetChunkWriter(ctx context.Context, name string, uu string) (io.WriteCloser, error)
}

type ImageSearcher struct {
	driver storagedriver.StorageDriver
}

func NewSearcher(d storagedriver.StorageDriver) *ImageSearcher {
	return &ImageSearcher{driver: d}
}

func (ims ImageSearcher) FindImages(ctx context.Context, name string) ([]*v1.ImageManifest, error) {
	return nil, errors.New("not implemented")
}

func getImageJson(ctx context.Context, d storagedriver.StorageDriver, ps string) (*v1.ImageManifest, error) {
	buf, err := d.GetContent(ctx, ps)
	if err != nil {
		return nil, err
	}

	return v1.ParseImageManifest(buf)
}

func (ims ImageSearcher) GetManifest(ctx context.Context, nam string, ref string) (*v1.ImageManifest, error) {
	// If the reference is a tag -
	//  1. get the digest via tag
	//  2. get the manifest via digest
	// Digest can be only first few digests - as long as there is no ambiguity.
	refstr := strings.ToLower(ref)
	name := strings.ToLower(nam)

	if utils.IsDigest(refstr) {
		ps := imageJsonPathSpec{name: name, id: refstr}.pathSpec()
		res, err := ims.driver.List(ctx, ps)
		if err != nil {
			if _, ok := err.(storagedriver.PathNotFoundError); ok {
				return nil, fmt.Errorf("digest not found: %s", ref)
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
	tps := tagPathSpec{name: name, tag: refstr}.pathSpec()
	buf, err := ims.driver.GetContent(ctx, tps)
	if err != nil {
		return nil, err
	}

	idstr := strings.ToLower(strings.TrimSpace(string(buf)))
	if utils.ParseImageId(idstr) == nil {
		return nil, fmt.Errorf("unexpected digest '%s' for tag '%s'", idstr, refstr)
	}

	ips := imageJsonPathSpec{name: name, id: idstr}.pathSpec()
	return getImageJson(ctx, ims.driver, ips)
}

func (ims ImageSearcher) PutManifest(ctx context.Context, nam string, ref string, imf *v1.ImageManifest) error {
	// If the reference is a tag -
	//  1. put the manifest
	//  2. update the tag
	//
	// If the reference is a digest
	//  1. check whether digest matches imf.Id
	//  2. put the manifest
	refstr := strings.ToLower(ref)
	idstr := strings.ToLower(imf.Id)
	name := strings.ToLower(nam)
	isdigest := utils.ParseImageId(refstr) != nil

	if isdigest {
		if refstr != idstr {
			return errors.New("digest and content body mismatch")
		}
	}

	if !imf.Ok() {
		return errors.New("unexpected image manifest format")
	}

	// Check whether its parents exists
	for _, pid := range imf.Parents {
		ps := imageJsonPathSpec{name: name, id: pid}.pathSpec()
		if _, err := ims.driver.Stat(ctx, ps); err != nil {
			return err
		}
	}

	// Check whether the image blob has been uploaded
	bps := blobDigestPathSpec{digest: imf.Blobsum}.pathSpec()
	if _, err := ims.driver.Stat(ctx, bps); err != nil {
		return fmt.Errorf("image blob missing: %s", imf.Blobsum)
	}

	ps := imageJsonPathSpec{name: name, id: idstr}.pathSpec()
	if err := ims.driver.PutContent(ctx, ps, []byte(imf.String())); err != nil {
		return errors.New("failed to update manifest")
	}

	if !isdigest {
		tps := tagPathSpec{name: name, tag: refstr}.pathSpec()
		if err := ims.driver.PutContent(ctx, tps, []byte(idstr)); err != nil {
			return fmt.Errorf("failed to update tag '%s' with digest '%s'", refstr, idstr)
		}
	}

	return nil
}

func (ims ImageSearcher) ListTags(ctx context.Context, name string) ([]string, error) {
	ps := tagsPathSpec{name: name}.pathSpec()

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

func (ims ImageSearcher) GetBlobPathSpec(name string, digest string) (string, error) {
	ps := blobDigestPathSpec{digest: digest}
	if utils.IsBlobDigest(digest) {
		return ps.pathSpec(), nil
	}

	return "", fmt.Errorf("invalid image digest: %s", digest)
}

// Prepare blob upload involves the following steps:
//  1. generate a UUID to identify the upload session
//  2. save the target digest value
//  3. return the target location
func (ims ImageSearcher) PrepareBlobUpload(ctx context.Context, name string, info *v1.UploadInfo) (string, error) {
	digest := strings.TrimSpace(info.Digest)
	bps := blobDigestPathSpec{digest: digest}.pathSpec()
	if _, err := ims.driver.Stat(ctx, bps); err == nil {
		return "", errcode.ConflictError{Resource: digest}
	}

	uu := utils.NewUUID()
	ucps := uploadCheckSumPathSpec{name: name, id: uu}.pathSpec()
	if err := ims.driver.PutContent(ctx, ucps, []byte(digest)); err != nil {
		return "", err
	}

	urlps := uploadUuidPathSpec{name: name, id: uu}.urlSpec()
	return urlps, nil
}

func (ims ImageSearcher) GetUploadedSize(ctx context.Context, name string, uu string) (int64, error) {
	dps := uploadDataPathSpec{name: name, id: uu}.pathSpec()

	info, err := ims.driver.Stat(ctx, dps)
	if err != nil {
		return 0, err
	}

	return info.Size(), nil
}

func (ims ImageSearcher) CancelUpload(ctx context.Context, name string, uu string) error {
	uups := uploadUuidPathSpec{name: name, id: uu}.pathSpec()

	_, err := ims.driver.Stat(ctx, uups)
	if err != nil {
		return err
	}

	go ims.driver.Delete(ctx, uups)
	return nil
}

func (ims ImageSearcher) CompleteUpload(ctx context.Context, name string, uu string) error {
	csps := uploadCheckSumPathSpec{name: name, id: uu}.pathSpec()
	buf, err := ims.driver.GetContent(ctx, csps)
	if err != nil {
		return err
	}

	// TODO: verify digest
	bdps := blobDigestPathSpec{digest: string(buf)}.pathSpec()
	dps := uploadDataPathSpec{name: name, id: uu}.pathSpec()
	if err = ims.driver.Move(ctx, dps, bdps); err != nil {
		return err
	}

	uups := uploadUuidPathSpec{name: name, id: uu}.pathSpec()
	ims.driver.Delete(ctx, uups)

	return nil
}

func (ims ImageSearcher) GetChunkWriter(ctx context.Context, name string, uu string) (io.WriteCloser, error) {
	// Check whether the upload UUID exists
	uups := uploadUuidPathSpec{name: name, id: uu}.pathSpec()

	_, err := ims.driver.Stat(ctx, uups)
	if err != nil {
		return nil, err
	}

	// Write the record of started time
	stps := uploadStartTimePathSpec{name: name, id: uu}.pathSpec()
	ts := time.Now().Format(time.RFC3339)
	ims.driver.PutContent(ctx, stps, []byte(ts))

	dps := uploadDataPathSpec{name: name, id: uu}.pathSpec()
	return ims.driver.Writer(ctx, dps, true)
}
