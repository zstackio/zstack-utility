package storage

import (
	"image-store/registry/api/v1"
	"strings"
	"sync"
	"unicode"
)

// A simple cache of image info
type ImageStat struct {
	sync.RWMutex                              // to protect the cache below
	cache        map[string]*v1.ImageManifest // a map of name to description
}

// Create an image statistic
func NewImageStat(c map[string]*v1.ImageManifest) *ImageStat {
	s := new(ImageStat)
	s.cache = c
	return s
}

func match(name, key string) bool {
	idx := strings.Index(name, key)
	if idx < 0 {
		return false
	}

	if idx > 0 && !unicode.IsPunct(rune(name[idx-1])) {
		return false
	}

	len, ridx := len(name), idx+len(key)
	if ridx < len {
		return unicode.IsPunct(rune(name[ridx]))
	}

	return true
}

// Search for image with key word
func (s *ImageStat) Search(key string) []*v1.ImageManifest {
	s.RLock()
	defer s.RUnlock()

	var imfs []*v1.ImageManifest
	for k, v := range s.cache {
		if match(k, key) || match(k, v.Desc) {
			imfs = append(imfs, v)
		}
	}

	return imfs
}

// Update image statistics
func (s *ImageStat) Update(name string, imf *v1.ImageManifest) {
	s.Lock()
	defer s.Unlock()

	if name != "" {
		s.cache[name] = imf
	}
}
