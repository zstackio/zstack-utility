package utils

import (
	"crypto/sha1"
	"crypto/sha256"
	"encoding/hex"
	"hash"
	"io"
)

// Get the check sum of the content from reader with a given hasher
func Hashing(r io.Reader, hasher hash.Hash) (string, error) {
	if _, err := io.Copy(hasher, r); err != nil {
		return "", err
	}

	return hex.EncodeToString(hasher.Sum(nil)), nil
}

// Get the SHA256 check sum
func Sha256Sum(r io.Reader) (string, error) {
	return Hashing(r, sha256.New())
}

// Get the SHA1 check sum
func Sha1Sum(r io.Reader) (string, error) {
	return Hashing(r, sha1.New())
}

// An image digest is a SHA-256 check sum.
var GetImageDigest = Sha256Sum

// This function checks whether a string looks like a digest
func IsDigest(s string) bool {
	for _, r := range s {
		switch {
		default:
			return false
		case '0' <= r && r <= '9':
		case 'a' <= r && r <= 'f':
		case 'A' <= r && r <= 'F':
		}
	}

	n := len(s)
	return n > 0 && n <= 64
}

func IsBlobDigest(s string) bool {
	return IsDigest(s) && len(s) == 2*sha256.Size
}
