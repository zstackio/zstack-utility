// A command line utility to operate on image repository.
package main

import (
	"bytes"
	"flag"
	"fmt"
	"github.com/docker/distribution/context"
	"image-store/config"
	"image-store/registry/api/v1"
	"image-store/registry/storage"
	"image-store/registry/storage/driver/factory"
	"image-store/utils"
	"io/ioutil"
	"os"
	"path"
	"strings"
	"time"
)

var (
	// global command line options
	fconf = flag.String("conf", "zstore.yaml", "zstore configure file")

	// others
	progname = path.Base(os.Args[0])
	bgctx    = context.Background()
)

func createStorageFrontend(config *config.Configuration) (storage.IStorageFE, error) {
	// Get storage parameters.
	storageParams, err := config.Storage.Parameters()
	if err != nil {
		return nil, err
	}

	typ, _ := config.Storage.Type()
	driver, err := factory.Create(typ, storageParams)
	if err != nil {
		return nil, err
	}

	return storage.NewStorageFrontend(driver), nil
}

func newFlagSet(id string) *flag.FlagSet {
	fs := flag.NewFlagSet(id, flag.ExitOnError)
	fs.Usage = func() {
		fmt.Fprintf(os.Stderr, "usage: %s [OPTION]\n", id)
		fs.PrintDefaults()
		os.Exit(1)
	}

	return fs
}

func uploadFile(sfe storage.IStorageFE, fh *os.File, size int64, name string, id string) (string, error) {
	var buffer []byte
	offset, cache := int64(0), make([]byte, v1.BlobChunkSize)

	for index := v1.ChunkStartIndex; offset < size; index++ {
		if offset+v1.BlobChunkSize <= size {
			buffer = cache
		} else {
			buffer = cache[:(size % v1.BlobChunkSize)]
		}

		_, err := fh.ReadAt(buffer, offset)
		if err != nil {
			return "", err
		}

		subhash, err := utils.Sha256Sum(bytes.NewReader(buffer))
		if err != nil {
			return "", fmt.Errorf("failed to compute hash for chunk #%d: %s", index, err)
		}

		chwr, err := sfe.GetChunkWriter(bgctx, name, id, index, subhash)
		if err != nil {
			return "", fmt.Errorf("failed to get writer for chunk #%d: %s", index, err)
		}

		defer chwr.Close()

		_, err = chwr.Write(buffer)
		if err != nil {
			return "", fmt.Errorf("failed to upload chunk #%d: %s", index, err)
		}

		if err = chwr.Commit(); err != nil {
			return "", fmt.Errorf("failed to commit chunk #%d: %s", index, err)
		}

		offset += v1.BlobChunkSize
	}

	tophash, err := sfe.CompleteUpload(bgctx, name, id)
	if err != nil {
		return "", fmt.Errorf("failed to complete upload task %s: %s", id, err)
	}

	return tophash, nil
}

func doAdd(sfe storage.IStorageFE, args []string) error {
	addcmd := newFlagSet("add")

	ffile := addcmd.String("file", "", "the path to image file")
	fname := addcmd.String("name", "", "the image name ('ubuntu' etc.)")
	fauth := addcmd.String("author", "", "the author of the image")
	farch := addcmd.String("arch", "", "the CPU arch of the image")
	fdesc := addcmd.String("desc", "", "description of the image")
	ftag := addcmd.String("tag", "latest", "tag of the image")

	addcmd.Parse(args)

	mustHaveArgs := map[string]string{
		"name": *fname,
		"file": *ffile,
		"arch": *farch,
		"tag":  *ftag,
	}

	for key, value := range mustHaveArgs {
		if value == "" {
			return fmt.Errorf("missing args for -%s", key)
		}
	}

	fh, err := os.Open(*ffile)
	if err != nil {
		return fmt.Errorf("failed to open %s: %s", *ffile, err)
	}

	defer fh.Close()

	info, err := fh.Stat()
	if err != nil {
		return fmt.Errorf("failed to stat %s: %s", *ffile, err)
	}

	uploadinfo := v1.UploadInfo{Size: info.Size()}
	uups, err := sfe.PrepareBlobUpload(bgctx, *fname, &uploadinfo)
	if err != nil {
		return fmt.Errorf("prepare upload failed: %s", err)
	}

	tophash, err := uploadFile(sfe, fh, info.Size(), *fname, path.Base(uups))
	if err != nil {
		return err
	}

	// update image manifest
	manifest := v1.ImageManifest{
		Blobsum: tophash,
		Author:  *fauth,
		Arch:    *farch,
		Desc:    *fdesc,
		Size:    info.Size(),
		Name:    *fname,
	}

	imageid, err := utils.Sha1Sum(strings.NewReader(manifest.String()))
	if err != nil {
		return fmt.Errorf("failed to generate image id: %s", err)
	}

	manifest.Id = imageid
	manifest.Created = time.Now().Format(time.RFC3339)
	err = sfe.PutManifest(bgctx, *fname, *ftag, &manifest)
	if err != nil {
		return fmt.Errorf("image id: %s: %s", imageid, err)
	}

	fmt.Printf("ImageId: %s Tag: %s\n", imageid, *ftag)
	return nil
}

func withStorageFrontend(sfe storage.IStorageFE, cmd string, args []string) error {
	switch cmd {
	default:
		return fmt.Errorf("unexpected command: '%s'", cmd)
	case "add":
		return doAdd(sfe, args)
	}
}

func main() {
	flag.Usage = func() {
		fmt.Printf("usage: %s [OPTION] subcommand\n", progname)
		flag.PrintDefaults()
		os.Exit(1)
	}

	flag.Parse()

	buf, err := ioutil.ReadFile(*fconf)
	if err != nil {
		fmt.Println("failed to read configure file:", err)
		os.Exit(1)
	}

	cfg, err := config.Parse(buf)
	if err != nil {
		fmt.Println("failed to parse configure file:", err)
		os.Exit(1)
	}

	args := flag.Args()
	if len(args) == 0 {
		fmt.Println("missing subcommand")
		os.Exit(1)
	}

	sfe, err := createStorageFrontend(cfg)
	if err != nil {
		fmt.Println("failed to create storage frontend:", err)
		os.Exit(1)
	}

	if err = withStorageFrontend(sfe, args[0], args[1:]); err != nil {
		fmt.Println(err)
		os.Exit(1)
	}
}
