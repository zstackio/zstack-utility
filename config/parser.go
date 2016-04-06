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

	return &c, nil
}
