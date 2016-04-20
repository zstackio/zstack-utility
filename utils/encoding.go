package utils

import (
	"encoding/json"
	"io"
)

func JsonDecode(r io.Reader, req interface{}) error {
	decoder := json.NewDecoder(r)
	return decoder.Decode(req)
}
