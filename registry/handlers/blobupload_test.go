package handlers

import (
	"crypto/sha1"
	"image-store/utils"
	"io/ioutil"
	"strings"
	"testing"
)

func TestReadWithHasher(t *testing.T) {
	s := "hello world"
	digest, _ := utils.Sha1Sum(strings.NewReader(s))

	r, err := readWithHasher(strings.NewReader(s), sha1.New(), digest)
	if err != nil {
		t.Fatal("readWithHasher() failed:", err)
	}

	buf, err := ioutil.ReadAll(r)
	if err != nil {
		t.Fatal("ReadAll() failed:", err)
	}

	if string(buf) != s {
		t.Fatal("unexpected content:", string(buf))
	}
}
