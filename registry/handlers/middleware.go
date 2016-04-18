package handlers

import (
	"errors"
	"github.com/docker/distribution/context"
	"net/http"
)

// This handler enforces that the request body is in JSON.
func EnforceContentLength(h ContextHandlerFunc) ContextHandlerFunc {
	return ContextHandlerFunc(func(ctx context.Context, w http.ResponseWriter, r *http.Request) {
		if r.ContentLength == 0 {
			WriteHttpError(w, errors.New("missing content body"), http.StatusBadRequest)
			return
		}

		h.ServeHTTPContext(ctx, w, r)
		return
	})
}
