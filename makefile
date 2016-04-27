GO ?= go

.PHONY: all clean
all:
	$(GO) build zstore.go
	$(GO) build zstcli.go

clean:
	$(RM) zstore zstcli error.log *~ *.bak
