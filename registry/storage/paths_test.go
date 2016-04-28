package storage

import (
	"fmt"
	"testing"
)

func compareChunkPathSpec(expected, result *uploadChunkPathSpec) error {

	if expected.name != result.name {
		return fmt.Errorf("unexpected name: %s", result.name)
	}

	if expected.id != result.id {
		return fmt.Errorf("unexpected id: %s", result.id)
	}

	if expected.index != result.index {
		return fmt.Errorf("unexpected index: %s", result.index)
	}

	if expected.subhash != result.subhash {
		return fmt.Errorf("unexpected subhash: %s", result.subhash)
	}

	if expected.user != result.user {
		return fmt.Errorf("unexpected user: %s", result.user)
	}

	if expected.exist != result.exist {
		return fmt.Errorf("unexpected exist flag: %s", result.exist)
	}

	return nil
}

func TestParseChunkPathSpec(t *testing.T) {
	ucps := uploadChunkPathSpec{
		name:    "ubuntu",
		id:      "44e15381-7180-475b-89a0-6059dc7c84a1",
		index:   1,
		subhash: "d64c8e8e",
	}

	ps, err := parseChunkPathSpec(ucps.pathSpec())
	if err != nil {
		t.Fatal(err)
	}

	if err = compareChunkPathSpec(&ucps, ps); err != nil {
		t.Fatal(err)
	}

	ucps.user = "david"
	ucps.exist = true

	ps, err = parseChunkPathSpec(ucps.pathSpec())
	if err != nil {
		t.Fatal(err)
	}

	if err = compareChunkPathSpec(&ucps, ps); err != nil {
		t.Fatal(err)
	}
}
