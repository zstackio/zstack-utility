package errcode

import (
	"fmt"
	"net/http"
)

var (
	ENoStorageDriver = Error{
		Code:    http.StatusInternalServerError,
		Message: "no storage driver loaded",
	}
)

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
