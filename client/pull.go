package client

import (
	"fmt"
	"image-store/registry/api/errcode"
	"image-store/registry/api/v1"
	"image-store/utils"
	"io"
	"os"
)

// Pull a disk image
func (cln *ZImageClient) Pull(name string, reference string) error {
	resp, err := cln.Get(v1.GetManifestRoute(name, reference))
	if err != nil {
		return fmt.Errorf("failed in getting image manifest: %s", err.Error())
	}

	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		var e errcode.Error
		if err = utils.JsonDecode(resp.Body, &e); err != nil {
			return err
		}
		return e
	}

	var imf v1.ImageManifest
	if err = utils.JsonDecode(resp.Body, &imf); err != nil {
		return err
	}

	if !imf.Ok() {
		return fmt.Errorf("invalid image manifest for %s:%s", name, reference)
	}

	blobpath := GetImageBlobPath(name, imf.Blobsum)
	blobroute := v1.GetImageBlobRoute(name, imf.Blobsum)
	if info, err := os.Stat(blobpath); err == nil {
		if info.Size() != imf.Size {
			// continue from last
			resp, err = cln.RangeGet(blobroute, info.Size())
		} else {
			// TODO: current blob exists, check parent image blobs.
			return nil
		}
	} else {
		// download the blob and write manifest.
		resp, err = cln.Get(blobroute)
	}

	if err != nil {
		return fmt.Errorf("download image blob failed: %s", err.Error())
	}

	wr, err := os.OpenFile(blobpath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
	if err != nil {
		return err
	}

	defer wr.Close()

	_, err = io.Copy(wr, resp.Body)
	return err
}
