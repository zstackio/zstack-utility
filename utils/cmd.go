package utils

import (
	"bytes"
	"os/exec"
)

// Run a command and get its output
func GetCmdOutput(name string, arg ...string) (stdout, stderr bytes.Buffer, err error) {
	cmd := exec.Command(name, arg...)
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err = cmd.Run()
	return
}
