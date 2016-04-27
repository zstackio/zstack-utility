package config

import (
	"gopkg.in/yaml.v2"
)

// Parse a yaml configuration file into a Configuration struct
func Parse(in []byte) (*Configuration, error) {
	c := Configuration{}
	err := yaml.Unmarshal(in, &c)
	if err != nil {
		return nil, err
	}

	if err = c.ok(); err != nil {
		return nil, err
	}

	return &c, nil
}

// Check whether configuration is valid
func (c *Configuration) ok() error {
	return nil
}
