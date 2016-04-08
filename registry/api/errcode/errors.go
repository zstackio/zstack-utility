package errcode

import (
	"fmt"
)

type ErrorCode int

// Error provides a wrapper around ErrorCode with extra Details provided.
type Error struct {
	Code    ErrorCode   `json:"code"`
	Message string      `json:"message"`
	Details interface{} `json:"details,omitempty"`
}

// Error returns a human readable representation of the error.
func (e Error) Error() string {
	return fmt.Sprintf("%d: %s", e.Code, e.Message)
}

// Errors provides the envelope for multiple errors and a few sugar methods
// for use within the application.
type Errors []error

var _ error = Errors{}

// So that 'Errors' can be used as type error
func (errs Errors) Error() string {
	switch len(errs) {
	case 0:
		return "<nil>"
	case 1:
		return errs[0].Error()
	default:
		msg := "errors:\n"
		for _, err := range errs {
			msg += err.Error() + "\n"
		}
		return msg
	}
}

func (errs Errors) Len() int {
	return len(errs)
}
