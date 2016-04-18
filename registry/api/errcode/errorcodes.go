package errcode

import (
	"fmt"
	"net/http"
)

// Resource conflict error
type ConflictError struct {
	Resource string
}

func (e ConflictError) Error() string {
	return "resource conflict: " + e.Resource
}

// No storage driver loaded
type NoStorageDriverError struct{}

func (e NoStorageDriverError) Error() string {
	return "no storage driver loaded"
}

// Operation not supported
type NotSupportedError struct {
	Op string
}

func (e NotSupportedError) Error() string {
	return "operation not supported: " + e.Op
}

func BuildENotFound(target string, detail interface{}) *Error {
	return &Error{
		Code:    http.StatusNotFound,
		Message: fmt.Sprintf("target '%s' not found", target),
		Details: detail,
	}
}

func BuildEInvalidParam(name string, detail interface{}) *Error {
	return &Error{
		Code:    http.StatusBadRequest,
		Message: fmt.Sprintf("invalid parameter '%s'", name),
		Details: detail,
	}
}

func BuildBadRequest(msg string, e error) *Error {
	return &Error{
		Code:    http.StatusBadRequest,
		Message: msg,
		Details: e.Error(),
	}
}
