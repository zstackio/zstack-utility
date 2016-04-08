package handlers

import (
	"golang.org/x/net/context"
	"net/http"
)

func EnforceJSON(h ContextHandlerFunc) ContextHandlerFunc {
	return ContextHandlerFunc(func(ctx context.Context, rw http.ResponseWriter, req *http.Request) {
		rw.Header().Set("Content-Type", "application/json; charset=UTF-8")
		h.ServeHTTPContext(ctx, rw, req)
	})
}

func EnforceContentLength(h ContextHandlerFunc) ContextHandlerFunc {
	return ContextHandlerFunc(func(ctx context.Context, rw http.ResponseWriter, req *http.Request) {
		if req.ContentLength == 0 {
			http.Error(rw, "missing content body", 400)
		}
	})
}
