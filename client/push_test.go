package client

import (
	"fmt"
	"testing"
)

func TestParseRangeHeader(t *testing.T) {
	n := int64(9080847736628)
	hdr := fmt.Sprintf("bytes=0-%d", n)
	offset, err := parseRangeHeader(hdr)
	if err != nil {
		t.Fatal("parse range header failed:", err)
	}

	if offset != n {
		t.Fatal("unexpected offset:", offset)
	}
}
