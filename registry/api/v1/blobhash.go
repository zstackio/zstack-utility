package v1

import (
	"bytes"
	"fmt"
	"image-store/utils"
	"os"
)

type BlobInfo struct {
	Subhash []string // subhashes of the chunks
	Size    int64    // the blob file size
}

func GetBlobInfo(path string) (*BlobInfo, error) {
	reader, err := os.Open(path)
	if err != nil {
		return nil, err
	}

	defer reader.Close()

	finfo, err := reader.Stat()
	if err != nil {
		return nil, err
	}

	if !finfo.Mode().IsRegular() {
		return nil, fmt.Errorf("not a regular file: %s", path)
	}

	size := finfo.Size()

	var hashes []string
	var buffer []byte
	offset, cache := int64(0), make([]byte, BlobChunkSize)

	for index := ChunkStartIndex; offset < size; index++ {
		if offset+BlobChunkSize <= size {
			buffer = cache
		} else {
			buffer = cache[:(size % BlobChunkSize)]
		}

		_, err := reader.ReadAt(buffer, offset)
		if err != nil {
			return nil, err
		}

		subhash, err := utils.GetChunkDigest(bytes.NewReader(buffer))
		if err != nil {
			return nil, err
		}

		hashes = append(hashes, subhash)
		offset += BlobChunkSize
	}

	return &BlobInfo{Subhash: hashes, Size: size}, nil
}

func (bi *BlobInfo) GetBlobDigest() string {
	var buffer bytes.Buffer

	for _, h := range bi.Subhash {
		buffer.WriteString(h)
	}

	d, _ := utils.Sha256Sum(bytes.NewReader(buffer.Bytes()))
	return d
}
