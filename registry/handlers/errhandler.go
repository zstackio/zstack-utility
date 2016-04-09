package handlers

import (
	"fmt"
	"image-store/registry/api/errcode"
	"net/http"
)

func WriteHttpError(w http.ResponseWriter, e *errcode.Error) {
	w.WriteHeader(int(e.Code))
	fmt.Fprintf(w, e.Error())
}
