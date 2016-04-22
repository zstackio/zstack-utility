package v1

import "testing"

func TestParseManifest(t *testing.T) {
	s := `{
  "id": "3d8d92ee7c97e7381549facb11fad3939427f7e3",
  "blobsum": "d9108d65bbd95743c46bcb4437fbb39b9601a1895983629287697c1b9f720839",
  "parents": [ "d0d9367ae5aeee48d94b13f9ece4fe95de7ea84a" ],
  "created": "2016-03-28T21:19:18.674353812Z",
  "author": "Alyssa P. Hacker",
  "architecture": "amd64",
  "size": 171828,
  "name": "ubuntu",
  "desc": "A derived ubuntu image"
}`
	imf, err := ParseImageManifest([]byte(s))
	if err != nil {
		t.Fatal("parsing manifest failed")
	}

	if imf.Size != 171828 {
		t.Fatal("unexpected size")
	}
}
