package client

import (
	"bytes"
	"errors"
	"fmt"
	"image-store/registry/api/v1"
	"image-store/utils"
	"net/http"
	"strings"
)

func (cln *ZImageClient) Push(imgid string, tag string) error {
	return errors.New("not implemented")
}

func (cln *ZImageClient) PrepareUpload(name string) (loc string, err error) {
	var resp *http.Response

	resp, err = cln.Get(v1.GetUploadRoute(name))
	if err != nil {
		return
	}

	if resp.StatusCode != http.StatusAccepted {
		err = fmt.Errorf("unexpected http status code: %d", resp.StatusCode)
		return
	}

	loc = resp.Header.Get("Location")
	return
}

func (cln *ZImageClient) CancelUpload(name string, id string) error {
	route := v1.GetUploadIdRoute(name, id)
	req, err := http.NewRequest("DELETE", cln.GetFullUrl(route), nil)
	if err != nil {
		return err
	}

	resp, err := cln.Do(req)
	if err != nil {
		return err
	}

	if resp.StatusCode != http.StatusAccepted {
		return fmt.Errorf("unexpected http status code: %d", resp.StatusCode)
	}

	return nil
}

func parseRangeHeader(hdr string) (int64, error) {
	var size int64
	n, err := fmt.Sscanf(hdr, "bytes=0-%d", &size)
	if err != nil {
		return 0, err
	}

	if n != 1 {
		return 0, fmt.Errorf("unexpected range header: %s", hdr)
	}

	return size, nil
}

func (cln *ZImageClient) GetProgress(name string, id string) (int64, error) {
	resp, err := cln.Get(v1.GetUploadIdRoute(name, id))
	if err != nil {
		return 0, err
	}

	if resp.StatusCode != http.StatusOK {
		return 0, fmt.Errorf("unexpected http status code: %d", resp.StatusCode)
	}

	hdr := resp.Header.Get("Content-Range")
	return parseRangeHeader(hdr)
}

func (cln *ZImageClient) putImageManifest(name string, refernce string, imf *v1.ImageManifest) error {
	route, reader := v1.GetManifestRoute(name, refernce), strings.NewReader(imf.String())
	req, err := http.NewRequest("PUT", cln.GetFullUrl(route), reader)
	if err != nil {
		return err
	}

	resp, err := cln.Do(req)
	if err != nil {
		return err
	}

	if resp.StatusCode != http.StatusAccepted {
		return fmt.Errorf("unexpected http status code: %d", resp.StatusCode)
	}

	return nil
}

func (cln *ZImageClient) uploadImageBlob(name string, id string, startOffset int64, data []byte) error {
	chunksha1, err := utils.Sha1Sum(bytes.NewReader(data))
	if err != nil {
		return err
	}

	route := v1.GetUploadIdRoute(name, id)
	req, err := http.NewRequest("PATCH", cln.GetFullUrl(route), bytes.NewReader(data))
	if err != nil {
		return fmt.Errorf("upload request failed: '%s'", err.Error())
	}

	req.Header.Add("Range", fmt.Sprintf("bytes=%d-%d", startOffset, startOffset+int64(len(data)-1)))
	req.Header.Add(v1.HnChunkHash, chunksha1)

	resp, err := cln.Do(req)
	if err != nil {
		return err
	}

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("unexpected http status code: %d", resp.StatusCode)
	}

	return nil
}
