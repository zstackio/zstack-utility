package config

import (
	"errors"
	"strings"
)

type Configuration struct {
	// the version string
	Version string `yaml:"version"`

	// Maximum size of image blob file in MB
	MaxSizeInMB string `yaml:"maxsizemb"`

	// storage driver configuration
	Storage Storage `yaml:"storage"`

	HTTP struct {
		// the bind address host:port (no proto)
		Addr string `yaml:"addr,omitempty"`
	} `yaml:"http,omitempty"`

	TLS struct {
		// libtrust trusted clients file
		TrustedClient string `yaml:"trusted"`

		// the x509 private key
		PrivateKey string `yaml:"key"`
	} `yaml:"tls,omitempty"`
}

type Parameters map[string]interface{}

type Storage map[string]Parameters

// Type returns the storage driver type, such as 'filesystem' or 's3'
func (storage Storage) Type() (string, error) {
	var storageType []string

	// Return only key in this map
	for k := range storage {
		switch k {
		case "cache":
			// allow configuration of caching
		case "redirect":
			// allow configuration of redirect
		default:
			storageType = append(storageType, k)
		}
	}

	if len(storageType) > 1 {
		msg := "multiple storage drivers specified: " + strings.Join(storageType, ", ")
		return "", errors.New(msg)
	}

	if len(storageType) == 1 {
		return storageType[0], nil
	}

	return "", errors.New("no storage drivers specified")
}

// Parameters returns the Parameters map for a Storage configuration
func (storage Storage) Parameters() (Parameters, error) {
	t, err := storage.Type()
	if err != nil {
		return nil, err
	}

	return storage[t], nil
}
