package client

import (
	"fmt"
	"image-store/registry/api/errcode"
	"image-store/registry/api/v1"
	"image-store/utils"
	"io"
	"io/ioutil"
	"net/http"
	"os"
	"path"
)

// Pull a disk image
func (cln *ZImageClient) Pull(name string, reference string) error {
	imf, err := cln.getImageManifest(name, reference)
	if err != nil {
		return err
	}

	blobpath := GetImageBlobPath(name, imf.Blobsum)
	blobroute := v1.GetImageBlobRoute(name, imf.Blobsum)

	err = cln.pullImageBlob(blobpath, blobroute, imf)
	if err != nil {
		return err
	}

	// write image manifest
	if err = writeLocalManifest(name, imf); err != nil {
		return fmt.Errorf("failed to update manifest file: %s", err.Error())
	}

	os.Link(blobpath, GetImageFilePath(name, imf.Id))
	return nil
}

func (cln *ZImageClient) getImageManifest(name, reference string) (*v1.ImageManifest, error) {
	resp, err := cln.Get(v1.GetManifestRoute(name, reference))
	if err != nil {
		return nil, fmt.Errorf("failed in getting image manifest: %s", err.Error())
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

func (cln *ZImageClient) pullImageBlob(blobpath string, blobroute string, imf *v1.ImageManifest) error {

	var resp *http.Response
	var err error

	if info, err := os.Stat(blobpath); err == nil {
		if info.Size() != imf.Size {
			// continue from last
			resp, err = cln.RangeGet(blobroute, info.Size())
		} else {
			// TODO: current blob exists, check parent image blobs.
			return nil
		}
	} else {
		resp, err = cln.Get(blobroute)
	}

	if err != nil {
		return nil
	}

	defer resp.Body.Close()

	if err = writeLocalImageBlob(blobpath, resp.Body); err != nil {
		return fmt.Errorf("download image blob failed: %s", err.Error())
	}

	// verify the blobsum
	if err = checkBlobDigest(blobpath, imf.Blobsum); err != nil {
		return err
	}

	return nil
}

func writeLocalManifest(name string, imf *v1.ImageManifest) error {
	fname := GetImageManifestPath(name, imf.Id)
	if err := os.MkdirAll(path.Dir(fname), 0775); err != nil {
		return fmt.Errorf("failed to create directory: %s", err.Error())
	}

	return ioutil.WriteFile(fname, []byte(imf.String()), 0644)
}

func writeLocalImageBlob(blobpath string, r io.Reader) error {
	if err := os.MkdirAll(path.Dir(blobpath), 0775); err != nil {
		return fmt.Errorf("failed to create directory: %s", err.Error())
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

func checkBlobDigest(blobpath string, digest string) error {
	fd, err := os.Open(blobpath)
	if err != nil {
		return err
	}

	defer fd.Close()

	d, err := utils.GetImageDigest(fd)
	if err != nil {
		return err
	}

	if d != digest {
		return fmt.Errorf("image digest mismatch")
	}

	return nil
}
