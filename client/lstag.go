package client

import (
	"fmt"
	"image-store/registry/api/errcode"
	"image-store/registry/api/v1"
	"image-store/utils"
)

func dumpTags(tags map[string]string) {
	fmt.Printf("%-16s %s\n", "TAG NAME", "IMAGE ID")
	for k, v := range tags {
		fmt.Printf("%-16s %s\n", k, v)
	}
}

func getRemoteTags(gopt *GlobalOpt, name string) (res map[string]string, err error) {
	withClient(gopt, func(cln *ZImageClient) error {
		res, err = cln.ListTags(name)
		return err
	})
	return
}

func (cln *ZImageClient) ListTags(name string) (map[string]string, error) {
	resp, err := cln.Get(cln.GetFullUrl(v1.GetTagListRoute(name)))
	if err != nil {
		return nil, fmt.Errorf("failed to list remote tags: %s", err)
	}

	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		var e errcode.Error
		if err = utils.JsonDecode(resp.Body, &e); err != nil {
			return nil, err
		}
		return nil, e
	}

	res := make(map[string]string)
	if err = utils.JsonDecode(resp.Body, &res); err != nil {
		return nil, err
	}

	return res, nil
}
