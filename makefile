GO ?= go

.PHONY: all clean
all:
	$(GO) build zstore.go
	$(GO) build zstcli.go
	cd repoadmin/; $(GO) build

clean:
	cd repoadmin/; $(GO) clean
	$(RM) zstore zstcli error.log *~ *.bak
