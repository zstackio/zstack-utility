package v1

import "encoding/json"

type BlobManifest struct {
	Size   int64    `json:"size"`   // total size
	Chunks []string `json:"chunks"` // chunks in order
}

// Encode the blob manifest to JSON string
func (b *BlobManifest) String() string {
	buf, _ := json.Marshal(b)
	return string(buf)
}
