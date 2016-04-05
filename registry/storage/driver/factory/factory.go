package factory

import (
	"errors"
	"fmt"

	"image-store/registry/storage/driver"
)

// A map from storage driver name to its factory method
var driverFactories = make(map[string]StorageDriverFactory)

type StorageDriverFactory interface {
	// Create a storage driver instance with given parameters
	Create(parameters map[string]interface{}) (driver.StorageDriver, error)
}

// Register a storage driver
func Register(name string, factory StorageDriverFactory) error {
	if factory == nil {
		return errors.New("The driver factory must not be nil")
	}

	_, found := driverFactories[name]
	if found {
		var msg = fmt.Sprintf("Factory '%s' already registered", name)
		return errors.New(msg)
	}

	driverFactories[name] = factory
	return nil
}

// Create a storage driver
func Create(name string, parameters map[string]interface{}) (driver.StorageDriver, error) {
	factory, found := driverFactories[name]
	if !found {
		var msg = fmt.Sprintf("Factory '%s' not registered", name)
		return nil, errors.New(msg)
	}

	return factory.Create(parameters)
}
