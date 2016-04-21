package client

import (
	"errors"
	"image-store/registry/api/v1"
)

func (cln *ZImageClient) Search(name string) ([]*v1.ImageManifest, error) {
	return nil, errors.New("not implemented")
}

func dumpManifests(xms []*v1.ImageManifest) {
}
