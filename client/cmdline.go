package client

import (
	"flag"
	"fmt"
	"os"
	"path"
	"strings"
)

// Global command line options
type GlobalOpt struct {
	serverAddr  string
	privateKey  string
	trustedFile string
}

// Display usage message and quit.
func UsageExit(status int) {
	msg := `usage:
  %s [ global options ] command [ command options ]

Options:
 -url=host:port     The server address (default: "%s")
 -key=privkey.pem   'libtrust' private key file (default: "%s")
 -trusted=host.pem  'libtrust' trusted hosts file (default: "%s")
 -h,-help           Display this message

Commands:
 images    list local images
 search    search remote registry by name
 pull      pull an image (default to ":latest")
 add       add image to local repo (may have a parent)
 push      push an image (and update its tag)

'reference' can be a tag or a digest.
`
	fmt.Printf(msg, progname, defaultServer, privateKeyFilename, trustedHostsFilename)
	os.Exit(status)
}

var progname = path.Base(os.Args[0])

// Setup command line option for those subcommands
func EvalCommand() {
	// global options
	privkey := flag.String("key", privateKeyFilename, "'libtrust' private key file")
	trusted := flag.String("trusted", trustedHostsFilename, "'libtrust' trusted hosts")
	server := flag.String("url", defaultServer, "the server address")

	flag.Usage = func() { UsageExit(0) }
	flag.Parse()

	subCommandArgs := flag.Args()
	if len(subCommandArgs) == 0 {
		fmt.Fprintf(os.Stderr, "missing subcommand - run '%s -h' for help\n", progname)
		os.Exit(1)
	}

	gopt := GlobalOpt{
		serverAddr:  *server,
		privateKey:  *privkey,
		trustedFile: *trusted,
	}

	f, ok := cmdTable[subCommandArgs[0]]
	if !ok {
		fmt.Fprintf(os.Stderr, "'%s' is not a valid subcommand.\n", subCommandArgs[0])
		os.Exit(1)
	}

	f(&gopt, subCommandArgs[1:])
}

var cmdTable = map[string]func(*GlobalOpt, []string){
	"pull":   doPull,
	"push":   doPush,
	"add":    doAdd,
	"search": doSearch,
	"images": doImages,
}

func doAdd(gopt *GlobalOpt, args []string) {
	addCommand := flag.NewFlagSet("add", flag.ExitOnError)
	pimgid := addCommand.String("parent", "", "the parent image id")
	addCommand.Usage = func() {
		fmt.Fprintf(os.Stderr, "usage: %s %s [ flags ] <disk-image-file>\n\n", progname, "add")
		fmt.Fprintf(os.Stderr, "add an image file to  local repository\n")
		addCommand.PrintDefaults()
		os.Exit(1)
	}
	addCommand.Parse(args)

	n, restargs := addCommand.NArg(), addCommand.Args()
	switch {
	case n == 0:
		fmt.Fprintln(os.Stderr, "missing args for 'add'")
		os.Exit(1)
	case n > 1:
		fmt.Fprintf(os.Stderr, "too many args for 'add': %q\n", restargs)
		os.Exit(1)
	}

	// do with *pimgid
	fmt.Println("adding with parent image:", *pimgid)
}

func doPull(gopt *GlobalOpt, args []string) {
	pullCommand := flag.NewFlagSet("pull", flag.ExitOnError)
	pullCommand.Usage = func() {
		fmt.Fprintf(os.Stderr, "usage: %s %s name[:reference]\n\n", progname, "pull")
		fmt.Fprintf(os.Stderr, "pull a remote image to local - reference can be an image id or a tag\n")
		pullCommand.PrintDefaults()
		os.Exit(1)
	}
	pullCommand.Parse(args)

	n, restargs := pullCommand.NArg(), pullCommand.Args()
	switch {
	case n == 0:
		fmt.Fprintln(os.Stderr, "missing args for 'pull'")
		os.Exit(1)
	case n > 1:
		fmt.Fprintf(os.Stderr, "too many args for 'pull': %q\n", restargs)
		os.Exit(1)
	}

	xs := strings.Split(restargs[0], ":")
	switch len(xs) {
	case 1:
		withClient(gopt, func(cln *ZImageClient) error { return cln.Pull(xs[0], "latest") })
	case 2:
		withClient(gopt, func(cln *ZImageClient) error { return cln.Pull(xs[0], xs[1]) })
	default:
		fmt.Fprintf(os.Stderr, "invalid reference value: '%s'\n", restargs[0])
	}
}

func doPush(gopt *GlobalOpt, args []string) {
	pushCommand := flag.NewFlagSet("push", flag.ExitOnError)
	pushCommand.Usage = func() {
		fmt.Fprintf(os.Stderr, "usage: %s %s imgid[:tag]\n\n", progname, "push")
		fmt.Fprintf(os.Stderr, "push a local image to remote server\n")
		pushCommand.PrintDefaults()
		os.Exit(1)
	}
	pushCommand.Parse(args)

	n, restargs := pushCommand.NArg(), pushCommand.Args()
	switch {
	case n == 0:
		fmt.Fprintln(os.Stderr, "missing args for 'push'")
		os.Exit(1)
	case n > 1:
		fmt.Fprintf(os.Stderr, "too many args for 'push': %q\n", restargs)
		os.Exit(1)
	}

	xs := strings.Split(restargs[0], ":")
	switch len(xs) {
	case 1:
		withClient(gopt, func(cln *ZImageClient) error { return cln.Push(xs[0], "latest") })
	case 2:
		withClient(gopt, func(cln *ZImageClient) error { return cln.Push(xs[0], xs[1]) })
	default:
		fmt.Fprintf(os.Stderr, "invalid tag value: '%s'\n", restargs[0])
	}
}

func doSearch(gopt *GlobalOpt, args []string) {
	searchCommand := flag.NewFlagSet("search", flag.ExitOnError)
	searchCommand.Usage = func() {
		fmt.Fprintf(os.Stderr, "usage: %s %s <name>\n\n", progname, "search")
		fmt.Fprintf(os.Stderr, "search for remote images\n")
		searchCommand.PrintDefaults()
		os.Exit(1)
	}
	searchCommand.Parse(args)

	n, restargs := searchCommand.NArg(), searchCommand.Args()
	switch {
	case n == 0:
		fmt.Fprintln(os.Stderr, "missing args for 'search'")
		os.Exit(1)
	case n > 1:
		fmt.Fprintf(os.Stderr, "too many args for 'search': %q\n", restargs)
		os.Exit(1)
	}

	withClient(gopt, func(cln *ZImageClient) error {
		xms, err := cln.Search(restargs[0])
		if err != nil {
			return err
		}

		dumpManifests(xms)
		return nil
	})
}

func doImages(gopt *GlobalOpt, args []string) {
	imagesCommand := flag.NewFlagSet("images", flag.ExitOnError)
	imagesCommand.Usage = func() {
		fmt.Fprintf(os.Stderr, "usage: %s %s\n\n", progname, "images")
		fmt.Fprintf(os.Stderr, "list local images\n")
		imagesCommand.PrintDefaults()
		os.Exit(1)
	}
	imagesCommand.Parse(args)

	if imagesCommand.NArg() != 0 {
		fmt.Fprintln(os.Stderr, "too many args for 'images': %q", imagesCommand.Args())
		os.Exit(1)
	}

	fmt.Println("list local images")
}

func withClient(gopt *GlobalOpt, f func(*ZImageClient) error) {
	cln, err := New(gopt.privateKey, gopt.trustedFile, gopt.serverAddr)
	if err != nil {
		fmt.Fprintf(os.Stderr, "server connection failed: %s\n", err.Error())
		return
	}

	err = f(cln)
	if err != nil {
		fmt.Fprintln(os.Stderr, err.Error())
	}
}
