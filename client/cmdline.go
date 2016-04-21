package client

import (
	"fmt"
	"os"
	"path"
	"strings"
)

// Global options
type GlobalOpt struct {
	serverAddr string
}

// Pull a remote image to local
type CmdPullOpt struct {
	name      string
	reference string
}

// Push local image to remote
type CmdPushOpt struct {
	imgid string
	tag   string
}

// Search remote images by name
type CmdSearchOpt struct {
	name string
}

// List local images
type CmdImagesOpt struct{}

// Dump help message
type CmdHelpOpt struct{}

// Actions upon each subcommands
type CmdRunner interface {
	OnPull(*GlobalOpt, *CmdPullOpt) error
	OnPush(*GlobalOpt, *CmdPushOpt) error
	OnSearch(*GlobalOpt, *CmdSearchOpt) error
	OnImages(*GlobalOpt, *CmdImagesOpt) error
}

// Command line options
type CmdLineOpt struct {
	g   *GlobalOpt  // global options
	opt interface{} // sub-commands
}

// Display usage message and quit.
func UsageExit(status int) {
	msg := `usage:
  %s [ options ] command

Options:
 -url=host:port  The server address
 -h,-help        Display this message

Command:
 pull   name[:reference]
 push   id[:tag]
 search name
 images

'reference' can be a tag or a digest.
`
	fmt.Printf(msg, path.Base(os.Args[0]))
	os.Exit(status)
}

// Parse global options
func parseGlobalOpt(args []string, g *GlobalOpt) (skipNext bool, err error) {
	switch {
	case args[0] == "-url":
		if len(args) < 2 {
			err = fmt.Errorf("missing argument for '%s'", "-url")
			return
		}
		g.serverAddr, skipNext = args[1], true
	case strings.HasPrefix(args[0], "-url="):
		url := args[0][5:]
		if url == "" {
			err = fmt.Errorf("missing argument for '%s'", "-url=")
			return
		}
		g.serverAddr = url
	}

	err = fmt.Errorf("unexpected option: '%s'", args[0])
	return
}

// Parse sub-command
func parseSubCommand(arglist []string) (interface{}, error) {
	cmd, args := arglist[0], arglist[1:]

	switch cmd {
	case "pull":
		if len(args) != 1 {
			return nil, fmt.Errorf("unexpected argument number for 'search'")
		}

		xs := strings.Split(args[0], ":")
		switch len(xs) {
		case 1:
			return &CmdPullOpt{name: xs[0], reference: "latest"}, nil
		case 2:
			return &CmdPullOpt{name: xs[0], reference: xs[1]}, nil
		default:
			return nil, fmt.Errorf("invalid reference value: '%s'", args[0])
		}

	case "push":
		if len(args) != 1 {
			return nil, fmt.Errorf("unexpected argument number for 'search'")
		}

		xs := strings.Split(args[0], ":")
		switch len(xs) {
		case 1:
			return &CmdPushOpt{imgid: xs[0], tag: "latest"}, nil
		case 2:
			return &CmdPushOpt{imgid: xs[0], tag: xs[1]}, nil
		default:
			return nil, fmt.Errorf("invalid tag value: '%s'", args[0])
		}

	case "search":
		if len(args) != 1 {
			return nil, fmt.Errorf("unexpected argument number for 'search'")
		}

		return &CmdSearchOpt{name: args[0]}, nil

	case "images":
		if len(args) > 0 {
			return nil, fmt.Errorf("unexpected args: '%s'", strings.Join(args, ","))
		}

		return &CmdImagesOpt{}, nil
	}

	return nil, fmt.Errorf("unexpected command: '%s'", cmd)
}

// Parse command line options or return error
func ParseCmdLine() (*CmdLineOpt, error) {
	args := os.Args[1:]
	if len(args) == 0 {
		return nil, fmt.Errorf("%s: a command argument is required.", path.Base(os.Args[0]))
	}

	// default global config
	g := GlobalOpt{serverAddr: defaultServer}
	var opt interface{}

	for idx := 0; idx < len(args); idx++ {
		arg := args[idx]

		if strings.HasPrefix(arg, "-") {
			switch arg {
			case "-h", "-help":
				return &CmdLineOpt{g: &g, opt: &CmdHelpOpt{}}, nil
			default:
				if skipNext, err := parseGlobalOpt(args[idx:], &g); err != nil {
					return nil, err
				} else {
					if skipNext {
						idx += 1
					}
				}
			}
		} else {
			var err error
			opt, err = parseSubCommand(args[idx:])
			if err != nil {
				return nil, err
			}

			break
		}
	}

	return &CmdLineOpt{g: &g, opt: opt}, nil
}

// Run command via the command runner
func (c *CmdLineOpt) RunCmd(r CmdRunner) error {
	switch c.opt.(type) {
	case *CmdPushOpt:
		opt, _ := c.opt.(*CmdPushOpt)
		return r.OnPush(c.g, opt)
	case *CmdPullOpt:
		opt, _ := c.opt.(*CmdPullOpt)
		return r.OnPull(c.g, opt)
	case *CmdImagesOpt:
		opt, _ := c.opt.(*CmdImagesOpt)
		return r.OnImages(c.g, opt)
	case *CmdSearchOpt:
		opt, _ := c.opt.(*CmdSearchOpt)
		return r.OnSearch(c.g, opt)
	case *CmdHelpOpt:
		UsageExit(0)
	}

	return fmt.Errorf("unexpected cmd: %v", c.opt)
}

type defaultRunner struct{}

func (r defaultRunner) OnPull(g *GlobalOpt, opt *CmdPullOpt) error {
	fmt.Println("pulling")
	return nil
}

func (r defaultRunner) OnPush(g *GlobalOpt, opt *CmdPushOpt) error {
	fmt.Println("pushing")
	return nil
}

func (r defaultRunner) OnSearch(g *GlobalOpt, opt *CmdSearchOpt) error {
	fmt.Println("searching")
	return nil
}

func (r defaultRunner) OnImages(g *GlobalOpt, opt *CmdImagesOpt) error {
	fmt.Println("list local images")
	return nil
}

var DefaultRunner = defaultRunner{}
