package utils

import (
	"testing"
)

func TestIsImageId(t *testing.T) {
	dict := make(map[string]bool)

	for i := 0; i < 100; i++ {
		id := NewImageId().String()
		_, ok := dict[id]
		if ok {
			t.Fatal("Id collision:", id)
		} else {
			dict[id] = true

			if ParseImageId(id) == nil {
				t.Fatal("failed to parse id:", id)
			}
		}
	}
}
