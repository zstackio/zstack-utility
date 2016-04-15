package utils

import (
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
