package client

import (
	"errors"
	"image-store/registry/api/v1"
	"io/ioutil"
	"os"
	"path"
	"path/filepath"
	"strings"
)

func (cln *ZImageClient) Search(name string) ([]*v1.ImageManifest, error) {
	return nil, errors.New("not implemented")
}

func dumpManifests(xms []*v1.ImageManifest) {
}

func FindImageManifest(imgid string) (*v1.ImageManifest, error) {
	var result *v1.ImageManifest

	target := imgid + ".json"

	err2 := filepath.Walk(ImageRepoTopDir,
		func(pathname string, fi os.FileInfo, err error) (e error) {
			if fi.IsDir() {
				return nil
			}

			if strings.Contains(pathname, "/manifests/tags/") {
				return filepath.SkipDir
			}

			if path.Base(pathname) == target {
				result, e = parseImageManifest(pathname)
				if e != nil {
					return e
				}
			}

			return nil
		})

	if err2 != nil {
		return nil, err2
	}

	if result == nil {
		return nil, errors.New("not found")
	}

	return result, nil
}

func parseImageManifest(f string) (*v1.ImageManifest, error) {
	buf, err := ioutil.ReadFile(f)
	if err != nil {
		return nil, err
	}

	return v1.ParseImageManifest(buf)
}
