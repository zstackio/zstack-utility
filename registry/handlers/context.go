package handlers

import (
	"github.com/docker/distribution/context"
	"net/http"
)

const ContextKeyAppDriver = "app.driver"

// Here we defines the ContextHandler, so that we can passing around
// net.Context with http.Handler
//
// c.f. https://joeshaw.org/net-context-and-http-handler/
type ContextHandler interface {
	ServeHTTPContext(context.Context, http.ResponseWriter, *http.Request)
}

type ContextHandlerFunc func(context.Context, http.ResponseWriter, *http.Request)

func (h ContextHandlerFunc) ServeHTTPContext(ctx context.Context, rw http.ResponseWriter, req *http.Request) {
	h(ctx, rw, req)
}

// An adaptor that is http.Handler compatible
type ContextAdapter struct {
	ctx     context.Context
	handler ContextHandler
}

func (ca ContextAdapter) ServeHTTP(rw http.ResponseWriter, req *http.Request) {
	ca.handler.ServeHTTPContext(ca.ctx, rw, req)
}
