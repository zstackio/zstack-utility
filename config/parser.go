package config

import (
	"errors"
	"fmt"
	"gopkg.in/yaml.v2"
	"strconv"
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
	if c.MaxSizeInMB == "" {
		return errors.New("missing configure for 'maxsizemb'")
	}

	n, err := strconv.Atoi(c.MaxSizeInMB)
	if err != nil {
		return err
	}

	if n <= 0 {
		return fmt.Errorf("invalid 'maxsizemb' value: %s", c.MaxSizeInMB)
	}

	return nil
}

func (c *Configuration) MaxSizeInByte() int64 {
	n, _ := strconv.Atoi(c.MaxSizeInMB)
	return int64(n) * 1024 * 1024
}
