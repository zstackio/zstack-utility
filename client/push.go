package client

import (
	"errors"
	"fmt"
	"image-store/registry/api/v1"
	"net/http"
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
	code, err := cln.Del(v1.GetUploadIdRoute(name, id))
	if err != nil {
		return err
	}

	if code != http.StatusAccepted {
		return fmt.Errorf("unexpected http status code: %d", code)
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
