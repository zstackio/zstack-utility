GO ?= go

.PHONY: all clean
all:
	$(GO) build zstore.go

clean:
	$(RM) zstore *~ *.bak
