package storage

import "testing"

func TestMatch(t *testing.T) {
	key := "centos"
	tbl := map[string]bool{
		"centos":       true,
		"centos-mysql": true,
		"my-centos":    true,
		"centos6":      false,
	}

	for name, res := range tbl {
		ok := match(name, key)
		if ok != res {
			t.Fatal("unexpected result for:", name)
		}
	}
}
