package v1

import (
	"encoding/json"
	"errors"
	"fmt"
	"image-store/utils"
	"strings"
)

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

	if imf.Size <= 0 {
		return false
	}

	if imf.Name == "" {
		return false
	}

	return utils.IsDigest(imf.Blobsum)
}

// Parse the buffer into an image manifest
func ParseImageManifest(buf []byte) (*ImageManifest, error) {
	var imf ImageManifest
	if err := json.Unmarshal(buf, &imf); err != nil {
		return nil, fmt.Errorf("failed in parsing image manifest: %s", err.Error())
	}

	if imf.Ok() {
		return &imf, nil
	}

	return nil, errors.New("invalid image manifest")
}

// Get existing image Id or generate a new one
func (imf ImageManifest) GenImageId() string {
	if imf.Id != "" {
		return imf.Id
	}

	imf.Created = ""
	s, _ := utils.Sha1Sum(strings.NewReader(imf.String()))
	return s
}
