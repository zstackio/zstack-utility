package errcode

import "fmt"

var (
	ENoStorageDriver = Error{
		Code:    500,
		Message: "no storage driver loaded",
	}
)

func BuildENotFound(target string, detail interface{}) *Error {
	return &Error{
		Code:    404,
		Message: fmt.Sprintf("target '%s' not found", target),
		Details: detail,
	}
}
