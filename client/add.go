package client

import (
	"fmt"
	"image-store/registry/api/v1"
	"image-store/utils"
	"os"
	"path"
	"regexp"
	"strings"
)

func getBlobDigestAndSize(f string) (digest string, size int64, err error) {
	var binfo *v1.BlobInfo

	// compute toptash and link to local blob store
	binfo, err = v1.GetBlobInfo(f)
	if err != nil {
		return
	}

	size = binfo.Size
	digest = binfo.GetBlobDigest()
	return
}

func buildManifest(parent string, arch string, name string) (*v1.ImageManifest, error) {
	var manifest v1.ImageManifest

	if parent != "" {
		m, err := FindImageManifest(parent)
		if err != nil {
			return nil, fmt.Errorf("failed to get image manifest for %s: %s", parent, err)
		}

		if arch == "" {
			manifest.Arch = m.Arch
		} else {
			if arch != m.Arch {
				return nil, fmt.Errorf("arch (%s) conflict with parent arch", arch)
			}

			manifest.Arch = m.Arch
		}

		if name != "" && name != m.Name {
			return nil, fmt.Errorf("name (%s) should be the same as parent (%s)", name, m.Name)
		}

		manifest.Name = m.Name
		manifest.Parent = parent
	} else {
		if arch == "" {
			return nil, fmt.Errorf("missing value for '-arch' option")
		}

		if name == "" {
			return nil, fmt.Errorf("missing value for '-name' option")
		}

		if !IsValidArch(arch) {
			fmt.Fprintf(os.Stderr, "unexpected arch: %s\n", arch)
			os.Exit(1)
		}

		if !IsValidName(name) {
			fmt.Fprintf(os.Stderr, "unexpected name: %s\n", name)
			os.Exit(1)
		}

		manifest.Arch = arch
		manifest.Name = strings.ToLower(name)
	}

	return &manifest, nil
}

func IsValidName(name string) bool {
	nameRegexp := regexp.MustCompile(`^[A-Za-z0-9]+$`)
	return nameRegexp.MatchString(name)
}

func IsValidTag(tag string) bool {
	tagRegexp := regexp.MustCompile(`^[A-Za-z0-9._-]+$`)
	return tagRegexp.MatchString(tag)
}

func IsValidArch(arch string) bool {
	switch arch {
	case "amd64":
	case "i386":
	default:
		return false
	}

	return true
}

// We first try hard link, and fail over with copy.
func importLocalImage(fname string, blobpath string) error {
	if err := os.MkdirAll(path.Dir(blobpath), 0775); err != nil {
		return err
	}

	if err := os.Link(fname, blobpath); err == nil {
		return nil
	}

	return utils.CopyFile(fname, blobpath)
}
