package client

import (
	"bytes"
	"fmt"
	"image-store/registry/api/errcode"
	"image-store/registry/api/v1"
	"image-store/utils"
	"io/ioutil"
	"net/http"
	"os"
	"path"
	"strconv"
	"strings"
)

func (cln *ZImageClient) getLocalParents(leaf *v1.ImageManifest) ([]*v1.ImageManifest, error) {
	var res []*v1.ImageManifest

	for cursor := leaf; cursor.Parent != ""; {

		imf, err := cln.getImageManifest(cursor.Name, cursor.Parent)
		if err == nil {
			break // manifest exists
		}

		// check Not Found error specifically
		if v, ok := err.(errcode.Error); ok && v.Code == http.StatusNotFound {
			res = append(res, imf)
		} else {
			return nil, err
		}

		manifest, err := FindImageManifest(cursor.Parent)
		if err != nil {
			return nil, fmt.Errorf("local cache corrupted: %s", err)
		}

		cursor = manifest
	}

	// reverse the list - so that we pull the parents first
	for i, j := 0, len(res)-1; i < j; i, j = i+1, j-1 {
		res[i], res[j] = res[j], res[i]
	}

	return res, nil
}

// Pushing an image involves the following steps:
// 1. upload blob chunks
// 2. upload image manifest
// 3. update local tag
func (cln *ZImageClient) Push(imgid string, tag string) error {
	leaf, err := FindImageManifest(imgid)
	if err != nil {
		return fmt.Errorf("image id not found: %s", imgid)
	}

	parents, err := cln.getLocalParents(leaf)
	if err != nil {
		return err
	}

	for _, p := range parents {
		tracePrintf("pushing parent: %s\n", p.Id)
		if err = cln.doPush(p, p.Id); err != nil {
			return err
		}
	}

	tracePrintf("pushing leaf: %s, tag = %s\n", leaf.Id, tag)
	if err = cln.doPush(leaf, tag); err != nil {
		return err
	}

	// update local tag file
	tagfile := GetImageTagPath(leaf.Name, tag)
	os.MkdirAll(path.Dir(tagfile), 0775)

	if err = ioutil.WriteFile(tagfile, []byte(leaf.Id), 0644); err != nil {
		return fmt.Errorf("failed to upload local tag file: %s", err)
	}

	return nil
}

func (cln *ZImageClient) doPush(imf *v1.ImageManifest, ref string) error {
	uinfo := v1.UploadInfo{Size: imf.Size}
	loc, err := cln.PrepareUpload(imf.Name, &uinfo)
	if err != nil {
		return fmt.Errorf("failed to prepare upload: %s", err)
	}

	tracePrintf("uploading image (%s) to: %s\n", imf.Id, loc)
	if err = cln.uploadFile(GetImageFilePath(imf.Name, imf.Id), uinfo.Size, loc); err != nil {
		return fmt.Errorf("failed to upload file: %s", err)
	}

	tracePrintf("constructing image manifest, ref = %s\n", ref)
	if err = cln.putImageManifest(imf.Name, ref, imf); err != nil {
		return fmt.Errorf("failed to create image manifest: %s", err)
	}

	return nil
}

func (cln *ZImageClient) uploadFile(blobpath string, size int64, loc string) error {
	fh, err := os.Open(blobpath)
	if err != nil {
		return err
	}

	defer fh.Close()

	var buffer []byte
	offset, cache := int64(0), make([]byte, v1.BlobChunkSize)

	for index := v1.ChunkStartIndex; offset < size; index++ {
		if offset+v1.BlobChunkSize <= size {
			buffer = cache
		} else {
			buffer = cache[:(size % v1.BlobChunkSize)]
		}

		_, err := fh.ReadAt(buffer, offset)
		if err != nil {
			return err
		}

		subhash, err := utils.GetChunkDigest(bytes.NewReader(buffer))
		if err != nil {
			return fmt.Errorf("failed to compute hash for chunk #%d: %s", index, err)
		}

		if err = cln.uploadBlobChunk(loc, index, subhash, buffer); err != nil {
			return fmt.Errorf("failed to upload chunk #%d: %s", index, err)
		}

		offset += v1.BlobChunkSize
	}

	return cln.CompleteBlobUpload(loc)
}

func (cln *ZImageClient) PrepareUpload(name string, uinfo *v1.UploadInfo) (loc string, err error) {
	var resp *http.Response

	route := cln.GetFullUrl(v1.GetUploadRoute(name))
	body := strings.NewReader(uinfo.String())
	req, err := http.NewRequest("POST", route, body)
	req.Header.Set("Content-Type", "application/json")

	resp, err = cln.Do(req)
	if err != nil {
		return
	}

	if resp.StatusCode != http.StatusAccepted {
		err = fmt.Errorf("unexpected http status code: %d", resp.StatusCode)
		return
	}

	loc = resp.Header.Get("Location")
	if loc == "" {
		err = fmt.Errorf("no location header from response header")
	}

	return
}

func (cln *ZImageClient) CancelUpload(loc string) error {
	req, err := http.NewRequest("DELETE", cln.GetFullUrl(loc), nil)
	if err != nil {
		return err
	}

	resp, err := cln.Do(req)
	if err != nil {
		return err
	}

	if resp.StatusCode != http.StatusAccepted {
		return fmt.Errorf("unexpected http status code: %d", resp.StatusCode)
	}

	return nil
}

func parseRangeHeader(hdr string) (int64, error) {
	var size int64
	n, err := fmt.Sscanf(hdr, "bytes=0-%d", &size)
	if err != nil {
		return 0, err
	}

	if n != 1 {
		return 0, fmt.Errorf("unexpected range header: %s", hdr)
	}

	return size, nil
}

func (cln *ZImageClient) GetProgress(loc string) (int64, error) {
	resp, err := cln.Get(cln.GetFullUrl(loc))
	if err != nil {
		return 0, err
	}

	if resp.StatusCode != http.StatusOK {
		return 0, fmt.Errorf("unexpected http status code: %d", resp.StatusCode)
	}

	hdr := resp.Header.Get("Content-Range")
	return parseRangeHeader(hdr)
}

func (cln *ZImageClient) putImageManifest(name string, ref string, imf *v1.ImageManifest) error {
	route, reader := v1.GetManifestRoute(name, ref), strings.NewReader(imf.String())
	req, err := http.NewRequest("PUT", cln.GetFullUrl(route), reader)
	if err != nil {
		return err
	}

	resp, err := cln.Do(req)
	if err != nil {
		return err
	}

	if resp.StatusCode != http.StatusAccepted {
		return fmt.Errorf("unexpected http status code: %d", resp.StatusCode)
	}

	return nil
}

func (cln *ZImageClient) uploadBlobChunk(loc string, index int, subhash string, data []byte) error {
	req, err := http.NewRequest("PATCH", cln.GetFullUrl(loc), bytes.NewReader(data))
	if err != nil {
		return fmt.Errorf("create upload request failed: '%s'", err.Error())
	}

	req.Header.Add(v1.HnChunkHash, subhash)
	req.Header.Add(v1.HnChunkIndex, strconv.Itoa(index))

	resp, err := cln.Do(req)
	if err != nil {
		return err
	}

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("unexpected http status code: %d", resp.StatusCode)
	}

	return nil
}

func (cln *ZImageClient) CompleteBlobUpload(loc string) error {
	req, err := http.NewRequest("POST", cln.GetFullUrl(loc), nil)
	if err != nil {
		return err
	}

	resp, err := cln.Do(req)
	if err != nil {
		return err
	}

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("unexpected http status code: %d", resp.StatusCode)
	}

	return nil
}
