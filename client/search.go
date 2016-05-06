package client

import (
	"errors"
	"fmt"
	"image-store/registry/api/errcode"
	"image-store/registry/api/v1"
	"image-store/utils"
	"io/ioutil"
	"os"
	"path"
	"path/filepath"
	"strings"
)

func (cln *ZImageClient) Search(name string) ([]*v1.ImageManifest, error) {
	resp, err := cln.Get(cln.GetFullUrl(v1.GetNameListRoute(name)))
	if err != nil {
		return nil, err
	}

	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		var e errcode.Error
		if err = utils.JsonDecode(resp.Body, &e); err != nil {
			return nil, err
		}
		return nil, e
	}

	var xms []*v1.ImageManifest
	if err = utils.JsonDecode(resp.Body, &xms); err != nil {
		return nil, err
	}

	return xms, nil
}

func dumpManifests(xms []*v1.ImageManifest) {
	fmt.Printf("%-16s %s\n", "NAME", "Description")
	for _, imf := range xms {
		fmt.Printf("%16s %s\n", imf.Name, imf.Desc)
	}
}

func ListImageManifests() ([]*v1.ImageManifest, error) {
	var result []*v1.ImageManifest

	_, err := os.Stat(ImageRepoTopDir)
	if err != nil {
		if os.IsNotExist(err) {
			return result, nil
		}
		return nil, err
	}

	e2 := filepath.Walk(ImageRepoTopDir,
		func(pathname string, fi os.FileInfo, err error) error {
			if fi.IsDir() {
				return nil
			}

			if !strings.Contains(pathname, "/manifests/revisions/") {
				return filepath.SkipDir
			}

			if !strings.HasSuffix(pathname, ".json") {
				return nil
			}

			imf, e := parseImageManifest(pathname)
			if e != nil {
				return e
			}

			result = append(result, imf)
			return nil
		})

	if e2 != nil {
		return nil, e2
	}

	return result, nil
}

// List tags for image with 'name' and returns a map of image id to tag
func ListTags(name string) (map[string]string, error) {
	m := make(map[string]string)

	_, err := os.Stat(ImageRepoTopDir)
	if err != nil {
		if os.IsNotExist(err) {
			return m, nil
		}
		return nil, err
	}

	e2 := filepath.Walk(ImageRepoTopDir,
		func(pathname string, fi os.FileInfo, err error) error {
			if fi.IsDir() {
				return nil
			}

			if !strings.Contains(pathname, "/manifests/tags/") {
				return filepath.SkipDir
			}

			buf, e := ioutil.ReadFile(pathname)
			if e != nil {
				return e
			}

			tag, id := path.Base(pathname), string(buf)
			if utils.ParseImageId(id) == nil {
				return fmt.Errorf("invalid id for tag: %s", tag)
			}

			m[id] = tag
			return nil
		})

	if e2 != nil {
		return nil, e2
	}

	return m, nil
}

func FindImageManifest(imgid string) (*v1.ImageManifest, error) {
	var result *v1.ImageManifest

	_, err := os.Stat(ImageRepoTopDir)
	if err != nil {
		if os.IsNotExist(err) {
			return result, nil
		}
		return nil, err
	}

	target := imgid + ".json"
	err2 := filepath.Walk(ImageRepoTopDir,
		func(pathname string, fi os.FileInfo, err error) (e error) {
			if fi.IsDir() {
				return nil
			}

			if !strings.Contains(pathname, "/manifests/revisions/") {
				return filepath.SkipDir
			}

			if path.Base(pathname) == target {
				result, e = parseImageManifest(pathname)
				if e != nil {
					return e
				}
			}

			return nil
		})

	if err2 != nil {
		return nil, err2
	}

	if result == nil {
		return nil, errors.New("not found")
	}

	return result, nil
}

func parseImageManifest(f string) (*v1.ImageManifest, error) {
	buf, err := ioutil.ReadFile(f)
	if err != nil {
		return nil, err
	}

	return v1.ParseImageManifest(buf)
}

func printLocalImages() {
	manifests, err := ListImageManifests()
	if err != nil {
		fmt.Println(err)
	}

	fmt.Printf("NAME             TAG                 IMAGE ID            CREATED             SIZE\n")
	for _, imf := range manifests {
		fmt.Printf("%16s %16s %16s %16s %d\n", imf.Name, "", imf.Id, imf.Created, imf.Size)
	}
}
