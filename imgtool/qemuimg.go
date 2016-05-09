// A wrapper of the command line tool `qemu-img`

package imgtool

import (
	"bufio"
	"bytes"
	"errors"
	"fmt"
	"image-store/utils"
	"os"
	"strings"
)

const qemuImgCmd = "/usr/bin/qemu-img"

// The file format of the disk image
type FileFormat int

const (
	Raw FileFormat = iota + 1
	Qcow2
)

// The string representation of the file format
func (f FileFormat) String() string {
	switch f {
	case Raw:
		return "raw"
	case Qcow2:
		return "qcow2"
	default:
		return "unknown"
	}
}

// The image information
type ImageInfo struct {
	Format      FileFormat
	VirtualSize int64
	BackingFile string
}

// Check whether the image has a backing file
func (info ImageInfo) HasParent() bool {
	return info.BackingFile != ""
}

// Get the image if of its parent
func (info ImageInfo) GetParentImageId() (*utils.ImageId, error) {
	id := strings.Split(info.BackingFile, ".")
	imgid := utils.ParseImageId(id[0])
	if imgid != nil {
		return imgid, nil
	}

	return nil, fmt.Errorf("invalid parent id: '%s'", id)
}

// Get the image information from a given file name
func GetImageInfo(name string) (*ImageInfo, error) {
	_, err := os.Stat(name)
	if err != nil {
		return nil, err
	}

	stdout, stderr, err := utils.GetCmdOutput(qemuImgCmd, "info", name)
	if err != nil {
		return nil, err
	}

	if stderr.Len() > 0 {
		return nil, errors.New(string(stderr.Bytes()))
	}

	return parseImgInfo(stdout)
}

func parseImgInfo(output bytes.Buffer) (*ImageInfo, error) {
	var info ImageInfo
	scanner := bufio.NewScanner(bytes.NewReader(output.Bytes()))

	for scanner.Scan() {
		if err := parseLine(&info, scanner.Text()); err != nil {
			return nil, err
		}
	}

	return &info, nil
}

func parseLine(info *ImageInfo, line string) error {
	xs := strings.Split(line, ":")
	switch xs[0] {
	case "file format":
		return parseFileFormat(info, xs[1:])
	case "virtual size":
		return parseVirtualSize(info, xs[1:])
	case "backing file":
		return parseBackingFile(info, xs[1:])
	default:
		return nil
	}
}

func parseFileFormat(info *ImageInfo, xs []string) error {
	if len(xs) != 1 {
		return fmt.Errorf("unexpected file format: %q", xs)
	}

	switch strings.TrimSpace(xs[0]) {
	case "raw":
		info.Format = Raw
	case "qcow2":
		info.Format = Qcow2
	default:
		return fmt.Errorf("unexpected file format: %s", xs[0])
	}

	return nil
}

func parseVirtualSize(info *ImageInfo, xs []string) error {
	if len(xs) != 1 {
		return fmt.Errorf("unexpected virtual size: %q", xs)
	}

	substr := strings.TrimLeftFunc(xs[0],
		func(r rune) bool {
			return r != '('
		})

	if _, err := fmt.Sscanf(substr, "(%d bytes)", &info.VirtualSize); err != nil {
		return fmt.Errorf("unexpected virtual size: %q", xs[0])
	}

	return nil
}

func parseBackingFile(info *ImageInfo, xs []string) error {
	if len(xs) < 1 {
		return fmt.Errorf("unexpected backing file: %q", xs)
	}

	ys := strings.Fields(xs[0])
	info.BackingFile = ys[0]
	return nil
}
