package handlers

import (
	"bytes"
	"errors"
	"github.com/docker/distribution/context"
	"net/http"
)

// This handler enforces that the request body is in JSON.
func EnforceJSON(h ContextHandlerFunc) ContextHandlerFunc {
	return ContextHandlerFunc(func(ctx context.Context, w http.ResponseWriter, r *http.Request) {
		// Check for a request body
		if r.ContentLength == 0 {
			WriteHttpError(w, errors.New("missing content body"), http.StatusBadRequest)
			return
		}

		// Check its MIME type
		buf := new(bytes.Buffer)
		buf.ReadFrom(r.Body)
		if http.DetectContentType(buf.Bytes()) != "application/json; charset=UTF-8" {
			http.Error(w, http.StatusText(http.StatusUnsupportedMediaType), http.StatusUnsupportedMediaType)
			return
		}

		h.ServeHTTPContext(ctx, w, r)
	})
}
