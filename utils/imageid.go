package utils

import (
	"bytes"
	"crypto/sha1"
	"github.com/pborman/uuid"
)

// Image Id is global randomly generated
type ImageId struct {
	v string
}

// Create a new Image Id
func NewImageId() *ImageId {
	hasher := sha1.New()
	r := bytes.NewReader([]byte(NewUUID()))
	s, _ := Hashing(r, hasher)
	return &ImageId{v: s}
}

// Convert Image Id to string
func (id *ImageId) String() string {
	return id.v
}

// Try to parse an existing Image Id
func ParseImageId(s string) *ImageId {
	if len(s) != sha1.Size*2 {
		return nil
	}

	if !IsDigest(s) {
		return nil
	}

	return &ImageId{v: s}
}

// Generate a new UUID string
func NewUUID() string {
	return uuid.New()
}

// Check whether a string is a valid UUID
func IsUUID(uu string) bool {
	return uuid.Parse(uu) != nil
}
