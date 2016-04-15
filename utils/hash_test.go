package utils

import (
	"crypto/sha256"
	"os"
	"testing"
)

func TestHashFile(t *testing.T) {
	r, err := os.Open("hash.go")
	if err != nil {
		t.Fatal("open file failed:", err)
	}

	defer r.Close()

	h, err := Hashing(r, sha256.New())
	if err != nil {
		t.Fatal("calc sha256 failed:", err)
	}

	t.Log("sha256(hash.go) =", string(h))
}

func TestIsDigest(t *testing.T) {
	dict := map[string]bool{
		"e93db22": true,
		"g34a":    false,
		"":        false,
		"e93Db22": true,
	}

	for k, v := range dict {
		if IsDigest(k) != v {
			t.Fatal("IsDigest failed on:", k)
		}
	}
}
