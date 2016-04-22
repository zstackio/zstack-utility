package client

import (
	"crypto/tls"
	"fmt"
	"github.com/docker/libtrust"
	"io/ioutil"
	"net"
	"net/http"
	"strings"
	"unicode"
)

// The Zstack image store client
type ZImageClient struct {
	c      *http.Client
	server string
}

func getHostAndPort(serverAddr string) (host string, port string, err error) {
	xs := strings.Split(serverAddr, "://")

	switch len(xs) {
	case 1:
		host, port, err = net.SplitHostPort(serverAddr)
		if err != nil {
			return
		}
	case 2:
		if xs[0] != "https" {
			err = fmt.Errorf("unexpected server protocol: %s", xs[0])
			return
		}

		return getHostAndPort(xs[1])
	default:
		err = fmt.Errorf("invalid server address")
		return
	}

	idx := strings.IndexFunc(port,
		func(r rune) bool {
			return !unicode.IsDigit(r)
		})
	if idx != -1 {
		err = fmt.Errorf("invalid port: %s", port)
		return
	}

	return
}

// Create a client instance
func New(privateKeyFile string, trustedHostsFile string, serverAddr string) (*ZImageClient, error) {
	// Load Client Key.
	clientKey, err := libtrust.LoadKeyFile(privateKeyFile)
	if err != nil {
		return nil, fmt.Errorf("load private key failed: %s", err.Error())
	}

	// Generate Client Certificate.
	selfSignedClientCert, err := libtrust.GenerateSelfSignedClientCert(clientKey)
	if err != nil {
		return nil, fmt.Errorf("generate client cert failed: %s", err.Error())
	}

	// Load trusted host keys.
	hostKeys, err := libtrust.LoadKeySetFile(trustedHostsFile)
	if err != nil {
		return nil, fmt.Errorf("load trusted host failed: %s", err.Error())
	}

	// Ensure the host we want to connect to is trusted!
	host, port, err := getHostAndPort(serverAddr)
	if err != nil {
		return nil, err
	}

	serverKeys, err := libtrust.FilterByHosts(hostKeys, host, false)
	if err != nil {
		return nil, fmt.Errorf("%q is not a known and trusted host", host)
	}

	// Generate a CA pool with the trusted host's key.
	caPool, err := libtrust.GenerateCACertPool(clientKey, serverKeys)
	if err != nil {
		return nil, fmt.Errorf("generate CAcert failed: %s", err.Error())
	}

	// Create HTTP Client.
	client := &http.Client{
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{
				Certificates: []tls.Certificate{
					tls.Certificate{
						Certificate: [][]byte{selfSignedClientCert.Raw},
						PrivateKey:  clientKey.CryptoPrivateKey(),
						Leaf:        selfSignedClientCert,
					},
				},
				RootCAs: caPool,
			},
		},
	}

	return &ZImageClient{
		c:      client,
		server: fmt.Sprintf("https://%s:%s", host, port),
	}, nil
}

func (cln *ZImageClient) getFullUrl(route string) string {
	var url string

	if strings.HasPrefix(route, "/") {
		url = cln.server + route
	} else {
		url = cln.server + "/" + route
	}

	return url
}

func (cln *ZImageClient) Get(route string) (resp *http.Response, err error) {
	return cln.c.Get(cln.getFullUrl(route))
}

func (cln *ZImageClient) Del(route string) (statusCode int, err error) {
	req, err := http.NewRequest("DELETE", cln.getFullUrl(route), nil)
	if err != nil {
		return 0, err
	}

	resp, err := cln.c.Do(req)
	if err != nil {
		return 0, err
	}

	return resp.StatusCode, nil
}

func (cln *ZImageClient) RangeGet(route string, startOffset int64) (resp *http.Response, err error) {
	req, err := http.NewRequest("GET", cln.getFullUrl(route), nil)
	if err != nil {
		return nil, err
	}

	req.Header.Add("Range", fmt.Sprintf("bytes=%d-", startOffset))
	resp, err = cln.c.Do(req)
	if err != nil {
		return
	}

	if resp.StatusCode != 200 {
		contents, _ := ioutil.ReadAll(resp.Body)
		err = fmt.Errorf("range get error: %s", strings.TrimSpace(string(contents)))
		return
	}

	return
}
