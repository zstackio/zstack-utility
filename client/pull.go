package client

import (
	"fmt"
	"image-store/registry/api/errcode"
	"image-store/registry/api/v1"
	"image-store/utils"
	"io"
	"io/ioutil"
	"os"
	"path"
)

// Pull a disk image
func (cln *ZImageClient) Pull(name string, reference string) error {
	imf, err := cln.getImageManifest(name, reference)
	if err != nil {
		return err
	}

	bmf, err := cln.getBlobManifest(name, imf.Blobsum)
	if err != nil {
		return err
	}

	imgfile, err := cln.downloadChunks(bmf, name, imf.Blobsum)
	if err != nil {
		return err
	}

	// the file name for saving the blob image
	blobpath := GetImageBlobPath(name, imf.Blobsum)
	os.MkdirAll(path.Dir(blobpath), 0775)
	if err = os.Rename(imgfile, blobpath); err != nil {
		return fmt.Errorf("failed to commit image blob: %s", err)
	}

	return finalizeBlobAndManifest(blobpath, imf)
}

func finalizeBlobAndManifest(blobpath string, imf *v1.ImageManifest) error {
	dest := GetImageFilePath(imf.Name, imf.Id)
	os.MkdirAll(path.Dir(dest), 0755)

	if err := os.Link(blobpath, dest); err != nil {
		return fmt.Errorf("failed to create image file: %s", err)
	}

	// write image manifest
	if err := writeLocalManifest(imf); err != nil {
		return fmt.Errorf("failed to update manifest file: %s", err)
	}

	return nil
}

func (cln *ZImageClient) downloadChunk(dldir string, subhash string, route string) error {
	dlfile := path.Join(dldir, subhash)

	if checkChunkDigest(dlfile, subhash) == nil {
		return nil
	}

	w, err := os.OpenFile(dlfile, os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return err
	}

	defer w.Close()

	resp, err := cln.Get(route)
	if resp.StatusCode != 200 {
		return fmt.Errorf("failed to download chunk %s", subhash)
	}

	defer resp.Body.Close()
	if _, err = io.Copy(w, resp.Body); err != nil {
		return fmt.Errorf("failed to download chunk %s: %s", subhash, err)
	}

	return nil
}

// TODO
// 1. continue from last interrupt
// 2. check parent blobs
func (cln *ZImageClient) downloadChunks(bmf *v1.BlobManifest, name, tophash string) (string, error) {
	// create the directory for saving chunks
	dldir := GetBlobDownloadDir(name, tophash)
	if err := os.MkdirAll(dldir, 0775); err != nil {
		return "", err
	}

	// download chunks
	for _, subhash := range bmf.Chunks {
		route := cln.GetFullUrl(v1.GetBlobChunkRoute(name, tophash, subhash))
		if err := cln.downloadChunk(dldir, subhash, route); err != nil {
			return "", err
		}

		dlfile := path.Join(dldir, subhash)
		if err := checkChunkDigest(dlfile, subhash); err != nil {
			return "", fmt.Errorf("chunk %s corrupted: %s", subhash, err)
		}
	}

	// combine chunk
	imgfile := path.Join(dldir, tophash)
	w, err := os.OpenFile(imgfile, os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return "", fmt.Errorf("failed to create blob file: %s", err)
	}

	defer w.Close()

	for _, subhash := range bmf.Chunks {
		r, err := os.Open(path.Join(dldir, subhash))
		if err != nil {
			return "", fmt.Errorf("failed to read chunk %s", subhash)
		}

		defer r.Close()

		if _, err = io.Copy(w, r); err != nil {
			return "", fmt.Errorf("failed to write image file: %s", err)
		}
	}

	for _, subhash := range bmf.Chunks {
		os.Remove(path.Join(dldir, subhash))
	}

	return imgfile, nil
}

func (cln *ZImageClient) getBlobManifest(name, tophash string) (*v1.BlobManifest, error) {
	resp, err := cln.Get(cln.GetFullUrl(v1.GetBlobManifestRoute(name, tophash)))
	if err != nil {
		return nil, fmt.Errorf("failed in getting blob manifest: %s", err)
	}

	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		var e errcode.Error
		if err = utils.JsonDecode(resp.Body, &e); err != nil {
			return nil, err
		}
		return nil, e
	}

	var bmf v1.BlobManifest
	if err = utils.JsonDecode(resp.Body, &bmf); err != nil {
		return nil, err
	}

	return &bmf, nil
}

func (cln *ZImageClient) getImageManifest(name, reference string) (*v1.ImageManifest, error) {
	resp, err := cln.Get(cln.GetFullUrl(v1.GetManifestRoute(name, reference)))
	if err != nil {
		return nil, fmt.Errorf("failed in getting image manifest: %s", err)
	}

	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		var e errcode.Error
		if err = utils.JsonDecode(resp.Body, &e); err != nil {
			return nil, err
		}
		return nil, e
	}

	var imf v1.ImageManifest
	if err = utils.JsonDecode(resp.Body, &imf); err != nil {
		return nil, err
	}

	if !imf.Ok() {
		return nil, fmt.Errorf("invalid image manifest for %s:%s", name, reference)
	}

	return &imf, nil
}

func writeLocalManifest(imf *v1.ImageManifest) error {
	fname := GetImageManifestPath(imf.Name, imf.Id)
	if err := os.MkdirAll(path.Dir(fname), 0775); err != nil {
		return fmt.Errorf("failed to create directory: %s", err)
	}

	return ioutil.WriteFile(fname, []byte(imf.String()), 0644)
}

func writeLocalImageBlob(blobpath string, r io.Reader) error {
	if err := os.MkdirAll(path.Dir(blobpath), 0775); err != nil {
		return fmt.Errorf("failed to create directory: %s", err)
	}

	w, err := os.OpenFile(blobpath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
	if err != nil {
		return err
	}

	defer w.Close()

	if _, err = io.Copy(w, r); err != nil {
		return err
	}

	return nil
}

func checkChunkDigest(blobpath string, digest string) error {
	fd, err := os.Open(blobpath)
	if err != nil {
		return err
	}

	defer fd.Close()

	d, err := utils.GetChunkDigest(fd)
	if err != nil {
		return err
	}

	if d != digest {
		return fmt.Errorf("image digest mismatch")
	}

	return nil
}
