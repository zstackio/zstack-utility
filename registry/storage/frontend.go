package storage

import (
	"bytes"
	"errors"
	"fmt"
	"github.com/docker/distribution/context"
	storagedriver "github.com/docker/distribution/registry/storage/driver"
	"image-store/registry/api/v1"
	"image-store/utils"
	"io"
	"path"
	"strings"
)

// The storage front-end. Names and tags etc. will be converted to lowercase
//
// TODO add a caching layer
type IStorageFE interface {
	// Returns images found in registry, empty array if not found.
	FindImages(ctx context.Context, name string) ([]*v1.ImageManifest, error)

	// Get the image manifest with a name and reference.
	GetManifest(ctx context.Context, name string, ref string) (*v1.ImageManifest, error)

	// Put a image manifest
	PutManifest(ctx context.Context, name string, ref string, imf *v1.ImageManifest) error

	// List tags under a name
	ListTags(ctx context.Context, name string) ([]string, error)

	// Get the blob json
	GetBlobJsonSpec(name string, digest string) (string, error)

	// Get a read-closer instance
	GetBlobChunkReader(ctx context.Context, name string, tophash string, subhash string, offset int64) (io.ReadCloser, error)

	// Prepare blob upload
	PrepareBlobUpload(ctx context.Context, name string, info *v1.UploadInfo) (string, error)

	// Get uploaded chunk size
	GetUploadedSize(ctx context.Context, name string, uu string) (int64, error)

	// Cancel the upload
	CancelUpload(ctx context.Context, name string, uu string) error

	// Complete the upload - returns tophash
	CompleteUpload(ctx context.Context, name string, uu string) (string, error)

	// Get a write-closer instance
	GetChunkWriter(ctx context.Context, name string, uu string, indx int, subhash string) (storagedriver.FileWriter, error)
}

type StorageFE struct {
	IStorageFE
	driver storagedriver.StorageDriver
}

func NewStorageFrontend(d storagedriver.StorageDriver) IStorageFE {
	return &StorageFE{driver: d}
}

func (sf StorageFE) FindImages(ctx context.Context, name string) ([]*v1.ImageManifest, error) {
	return nil, errors.New("not implemented")
}

func getImageJson(ctx context.Context, d storagedriver.StorageDriver, ps string) (*v1.ImageManifest, error) {
	buf, err := d.GetContent(ctx, ps)
	if err != nil {
		return nil, err
	}

	return v1.ParseImageManifest(buf)
}

// When given a partial digest, we search it and check its uniqueness.
func findImageIdInArray(lst []string, prefix string) (string, error) {
	var res []string

	// FIXME the code logic here assumes the schema of pathspec
	for _, ps := range lst {
		imageId := path.Base(ps)
		if strings.HasPrefix(imageId, prefix) {
			res = append(res, imageId)
		}
	}

	switch len(res) {
	case 1:
		return res[0], nil
	case 0:
		return "", fmt.Errorf("no manifest found for digest: %s", prefix)
	default:
		return "", fmt.Errorf("digest is ambiguous: %s", prefix)
	}
}

func (sf StorageFE) GetManifest(ctx context.Context, nam string, ref string) (*v1.ImageManifest, error) {
	// If the reference is a tag -
	//  1. get the digest via tag
	//  2. get the manifest via digest
	// Digest can be only first few digests - as long as there is no ambiguity.
	refstr := strings.ToLower(ref)
	name := strings.ToLower(nam)

	if utils.IsDigest(refstr) {
		topdir := imageJsonPathSpec{name: name, id: refstr}.revisionsDir()
		res, err := sf.driver.List(ctx, topdir)
		if err != nil {
			if _, ok := err.(storagedriver.PathNotFoundError); ok {
				return nil, fmt.Errorf("digest not found: %s", ref)
			}
			return nil, err
		}

		id, err := findImageIdInArray(res, ref)
		if err != nil {
			return nil, err
		}

		ps := imageJsonPathSpec{name: name, id: id}.pathSpec()
		return getImageJson(ctx, sf.driver, ps)
	}

	// ok - it is a tag
	tps := tagPathSpec{name: name, tag: refstr}.pathSpec()
	buf, err := sf.driver.GetContent(ctx, tps)
	if err != nil {
		return nil, err
	}

	idstr := strings.ToLower(strings.TrimSpace(string(buf)))
	if utils.ParseImageId(idstr) == nil {
		return nil, fmt.Errorf("unexpected digest '%s' for tag '%s'", idstr, refstr)
	}

	ips := imageJsonPathSpec{name: name, id: idstr}.pathSpec()
	return getImageJson(ctx, sf.driver, ips)
}

// TODO check existence, simplify logic
func (sf StorageFE) PutManifest(ctx context.Context, nam string, ref string, imf *v1.ImageManifest) error {
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
		if _, err := sf.driver.Stat(ctx, ps); err != nil {
			return err
		}
	}

	// Check whether the image blob has been uploaded
	bps := blobManifestPathSpec{digest: imf.Blobsum}.pathSpec()
	if _, err := sf.driver.Stat(ctx, bps); err != nil {
		return fmt.Errorf("image blob not exist: %s", imf.Blobsum)
	}

	// Check whether image digest already exists
	ps := imageJsonPathSpec{name: name, id: idstr}.pathSpec()
	if _, err := sf.driver.Stat(ctx, ps); err == nil {
		return fmt.Errorf("image manifest already exist")
	}

	if err := sf.driver.PutContent(ctx, ps, []byte(imf.String())); err != nil {
		return errors.New("failed to update manifest")
	}

	if !isdigest {
		tps := tagPathSpec{name: name, tag: refstr}.pathSpec()
		if err := sf.driver.PutContent(ctx, tps, []byte(idstr)); err != nil {
			return fmt.Errorf("failed to update tag '%s' with digest '%s'", refstr, idstr)
		}
	}

	return nil
}

func (sf StorageFE) ListTags(ctx context.Context, name string) ([]string, error) {
	ps := tagsPathSpec{name: name}.pathSpec()

	xs, err := sf.driver.List(ctx, ps)
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

func (sf StorageFE) GetBlobJsonSpec(name string, digest string) (string, error) {
	ps := blobManifestPathSpec{digest: digest}
	if utils.IsBlobDigest(digest) {
		return ps.pathSpec(), nil
	}

	return "", fmt.Errorf("invalid image digest: %s", digest)
}

// Prepare blob upload involves the following steps:
//  1. generate a UUID to identify the upload session
//  2. save the target digest value
//  3. return the target location
func (sf StorageFE) PrepareBlobUpload(ctx context.Context, name string, info *v1.UploadInfo) (string, error) {
	uu := utils.NewUUID()
	uips := uploadInfoPathSpec{name: name, id: uu}.pathSpec()
	if err := sf.driver.PutContent(ctx, uips, []byte(info.String())); err != nil {
		return "", err
	}

	return uu, nil
}

func (sf StorageFE) CancelUpload(ctx context.Context, name string, uu string) error {
	uups := uploadUuidPathSpec{name: name, id: uu}.pathSpec()

	_, err := sf.driver.Stat(ctx, uups)
	if err != nil {
		return err
	}

	go sf.driver.Delete(ctx, uups)
	return nil
}

func (sf StorageFE) getChunkSize(ctx context.Context, ucps *uploadChunkPathSpec) (int64, error) {
	var ps string
	if ucps.exist {
		ps = blobChunkPathSpec{subhash: ucps.subhash}.pathSpec()
	} else {
		ps = ucps.pathSpec()
	}

	info, err := sf.driver.Stat(ctx, ps)
	if err != nil {
		return 0, fmt.Errorf("failed to get chunk #%d size: %s", ucps.index, err)
	}

	return info.Size(), nil
}

func (sf StorageFE) GetUploadedSize(ctx context.Context, name string, uu string) (int64, error) {
	chunks, err := sf.getChunkPathSpecs(ctx, name, uu)
	if err != nil {
		return 0, err
	}

	var size int64
	for _, info := range chunks {
		sz, err := sf.getChunkSize(ctx, info)
		if err != nil {
			return 0, fmt.Errorf("failed to get chunk #%d size: %s", info.index, err)
		}

		size += sz
	}

	return size, nil
}

func (sf StorageFE) getChunkPathSpecs(ctx context.Context, name string, uu string) ([]*uploadChunkPathSpec, error) {
	uups := uploadUuidPathSpec{name: name, id: uu}.pathSpec()

	// List all chunks and check its size
	ls, err := sf.driver.List(ctx, uups)
	if err != nil {
		return nil, err
	}

	var result []*uploadChunkPathSpec
	for _, ps := range ls {
		if ucps, err := parseChunkPathSpec(ps); err == nil {
			result = append(result, ucps)
		}
	}

	return result, nil
}

// generate the blob manifest
func getBlobManifest(size int64, indexMap map[int]string) (*v1.BlobManifest, error) {
	var chunks []string

	for i := v1.ChunkStartIndex; i <= len(indexMap); i++ {
		subhash, ok := indexMap[i]
		if !ok {
			return nil, fmt.Errorf("missing digest for chunk #%d", i)
		}

		chunks = append(chunks, subhash)
	}

	return &v1.BlobManifest{
		Size:   size,
		Chunks: chunks,
	}, nil
}

// the top hash is computed by hashing the ordered sub-hashes.
func getTopHash(indexMap map[int]string) (string, error) {
	var buffer bytes.Buffer

	for i := v1.ChunkStartIndex; i <= len(indexMap); i++ {
		subhash, ok := indexMap[i]
		if !ok {
			return "", fmt.Errorf("missing digest for chunk #%d", i)
		}

		buffer.WriteString(subhash)
	}

	return utils.Sha256Sum(bytes.NewReader(buffer.Bytes()))
}

func (sf StorageFE) buildMaps(ctx context.Context, chunks []*uploadChunkPathSpec, totalSize int64) (map[string]string, map[int]string, error) {
	// A map of chunk filepath to digest
	chunkMap := make(map[string]string)

	// A map of existing indexes
	indexMap := make(map[int]string)

	var size int64
	for _, ucps := range chunks {
		sz, err := sf.getChunkSize(ctx, ucps)
		if err != nil {
			return nil, nil, err
		}
		size += sz

		chunkMap[ucps.pathSpec()] = ucps.subhash
		indexMap[ucps.index] = ucps.subhash
	}

	clen, ilen := len(chunkMap), len(indexMap)
	if len(chunkMap) != len(indexMap) {
		return nil, nil, fmt.Errorf("chunk number (%d) and index number (%d) mismatch", clen, ilen)
	}

	if size != totalSize {
		return nil, nil, fmt.Errorf("uploaded size (%d) not equal to file size (%d)", size, totalSize)
	}

	return chunkMap, indexMap, nil
}

func (sf StorageFE) CompleteUpload(ctx context.Context, name string, uu string) (string, error) {
	uips := uploadInfoPathSpec{name: name, id: uu}.pathSpec()
	content, err := sf.driver.GetContent(ctx, uips)
	if err != nil {
		return "", err
	}

	var uploadinfo v1.UploadInfo
	if err = utils.JsonDecode(bytes.NewReader(content), &uploadinfo); err != nil {
		return "", err
	}

	chunks, err := sf.getChunkPathSpecs(ctx, name, uu)
	if err != nil {
		return "", err
	}

	if len(chunks) == 0 {
		return "", fmt.Errorf("no chunks found for %s", uu)
	}

	chunkMap, indexMap, err := sf.buildMaps(ctx, chunks, uploadinfo.Size)
	if err != nil {
		return "", err
	}

	tophash, err := getTopHash(indexMap)
	if err != nil {
		return "", fmt.Errorf("failed to compute blob digest:", err)
	}

	blobmfst, err := getBlobManifest(uploadinfo.Size, indexMap)
	if err != nil {
		return "", fmt.Errorf("failed to compute blob manifest:", err)
	}

	// move chunks to blobs store
	for k, v := range chunkMap {
		bcps := blobChunkPathSpec{subhash: v}.pathSpec()
		// only move those not exists
		if _, err := sf.driver.Stat(ctx, bcps); err == nil {
			continue
		}

		if err = sf.driver.Move(ctx, k, bcps); err != nil {
			return "", fmt.Errorf("failed to move chunks: %s", err)
		}
	}

	// create a blob manifest
	bmps := blobManifestPathSpec{digest: tophash}.pathSpec()
	if err = sf.putContentIfNotExist(ctx, bmps, []byte(blobmfst.String())); err != nil {
		return "", fmt.Errorf("failed to write blob manifest: %s", err)
	}

	uups := uploadUuidPathSpec{name: name, id: uu}.pathSpec()
	sf.driver.Delete(ctx, uups)

	return tophash, nil
}

func (sf StorageFE) putContentIfNotExist(ctx context.Context, ps string, data []byte) error {
	if _, err := sf.driver.Stat(ctx, ps); err == nil {
		return nil
	}

	return sf.driver.PutContent(ctx, ps, data)
}

func (sf StorageFE) GetChunkWriter(ctx context.Context, name string, uu string, index int, subhash string) (storagedriver.FileWriter, error) {
	// Check whether the upload UUID exists
	uups := uploadUuidPathSpec{name: name, id: uu}.pathSpec()

	_, err := sf.driver.Stat(ctx, uups)
	if err != nil {
		return nil, fmt.Errorf("no upload workspace for %s", uu)
	}

	// Upon new chunks, we check whether it exists before constructing FileWriter.
	ucps := uploadChunkPathSpec{name: name, id: uu, index: index, subhash: subhash, exist: false}
	_, err = sf.driver.Stat(ctx, blobChunkPathSpec{subhash: subhash}.pathSpec())
	if err != nil {
		// chunk does not exist
		//
		// In order to compute the chunk digest w/o reading partial chunks,
		// we can't continue from the point of interruption.
		return sf.driver.Writer(ctx, ucps.pathSpec(), false /* append */)
	}

	// chunk exists
	ucps.exist = true
	if err := sf.driver.PutContent(ctx, ucps.pathSpec(), []byte("0")); err != nil {
		return nil, fmt.Errorf("failed to upload chunk #%d: %s", index, err)
	}

	return utils.NopFileWriter, nil
}

func (sf StorageFE) GetBlobChunkReader(ctx context.Context, name string, tophash string, subhash string, offset int64) (io.ReadCloser, error) {
	bcps := blobChunkPathSpec{subhash: subhash}.pathSpec()

	return sf.driver.Reader(ctx, bcps, offset)
}
