package imgtool

import (
	"fmt"
	"testing"
)

func TestGetImageInfo(t *testing.T) {
	info, err := GetImageInfo("qemuimg_test.go")
	if err != nil {
		t.Fatal(err)
	}

	fmt.Printf("format: %s\n", info.Format)
	fmt.Printf("virtual size: %d bytes\n", info.VirtualSize)
	fmt.Printf("backign file: %s\n", info.BackingFile)
}
