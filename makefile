GO ?= go

.PHONY: all clean
all:
	$(GO) build zstore.go
	$(GO) build genkeys.go
	$(GO) build test-client.go

clean:
	$(RM) zstore genkeys test-client *~ *.bak
