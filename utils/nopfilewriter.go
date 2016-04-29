package utils

import (
	storagedriver "github.com/docker/distribution/registry/storage/driver"
)

// Nop file writer
type nopFileWriter struct {
	storagedriver.FileWriter
}

func (nopFileWriter) Close() error  { return nil }
func (nopFileWriter) Commit() error { return nil }
func (nopFileWriter) Cancel() error { return nil }

func (nopFileWriter) Write(p []byte) (int, error) {
	return len(p), nil
}

var NopFileWriter = nopFileWriter{}
