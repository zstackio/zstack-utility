package factory

import (
	storagedriver "github.com/docker/distribution/registry/storage/driver"
	dockerfactory "github.com/docker/distribution/registry/storage/driver/factory"
	_ "github.com/docker/distribution/registry/storage/driver/filesystem"
)

// Create a storage driver
func Create(name string, parameters map[string]interface{}) (storagedriver.StorageDriver, error) {
	return dockerfactory.Create(name, parameters)
}
