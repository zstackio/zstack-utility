package handlers

import (
	"encoding/json"
	"fmt"
	"image-store/registry/api/errcode"
	"net/http"
)

type HttpResult struct {
	res interface{}
	err error
}

func NewHttpResult(r interface{}, e error) *HttpResult {
	return &HttpResult{res: r, err: e}
}

func (r *HttpResult) WriteResponse(w http.ResponseWriter) {
	if r.err != nil {
		WriteHttpError(w, r.err, http.StatusBadRequest)
		return
	}

	w.Header().Set("Content-Type", "application/json; charset=UTF-8")
	if err := json.NewEncoder(w).Encode(r.res); err != nil {
		panic(err)
	}
}

func WriteHttpError(w http.ResponseWriter, e error, status int) {
	w.Header().Set("Content-Type", "application/json; charset=UTF-8")
	w.WriteHeader(status)
	if _, ok := e.(*errcode.Error); ok {
		fmt.Fprintf(w, e.Error())
	} else {
		e2 := errcode.Error{
			Code:    errcode.ErrorCode(status),
			Message: "request error",
			Details: e.Error(),
		}
		fmt.Fprintf(w, e2.Error())
	}
}
