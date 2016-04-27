package storage

import (
	"image-store/utils"
	"strings"
	"testing"
)

func TestGetTopHash(t *testing.T) {
	idxMap1 := map[int]string{
		1: "hello",
		2: "world",
	}

	idxMap2 := map[int]string{
		1: "world",
		2: "hello",
	}

	h1, err := getTopHash(idxMap1)
	if err != nil {
		t.Fatal(err)
	}

	h2, err := getTopHash(idxMap2)
	if err != nil {
		t.Fatal(err)
	}

	if h1 == h2 {
		t.Fatal("h1 should not be equal to h2")
	}

	h3, err := utils.Sha256Sum(strings.NewReader("helloworld"))
	if err != nil {
		t.Fatal(err)
	}

	if h1 != h3 {
		t.Fatal("h1 should be equal to h3")
	}
}
