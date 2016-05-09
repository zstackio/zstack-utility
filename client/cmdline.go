package client

import (
	"flag"
	"fmt"
	"image-store/imgtool"
	"os"
	"path"
	"strings"
	"time"
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
 lstags    list tags of an image
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
var fverbose = false

func tracePrintf(format string, a ...interface{}) {
	if fverbose {
		fmt.Printf(format, a...)
	}
}

// Setup command line option for those subcommands
func EvalCommand() {
	// global options
	privkey := flag.String("key", privateKeyFilename, "'libtrust' private key file")
	trusted := flag.String("trusted", trustedHostsFilename, "'libtrust' trusted hosts")
	server := flag.String("url", defaultServer, "the server address")
	verbose := flag.Bool("verbose", false, "enable verbose output")

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

	fverbose = *verbose
	f(&gopt, subCommandArgs[1:])
}

var cmdTable = map[string]func(*GlobalOpt, []string){
	"pull":   doPull,
	"push":   doPush,
	"add":    doAdd,
	"search": doSearch,
	"images": doImages,
	"lstags": doListTag,
}

func doAdd(gopt *GlobalOpt, args []string) {
	addCommand := flag.NewFlagSet("add", flag.ExitOnError)
	ffile := addCommand.String("file", "", "the path to image file")
	fname := addCommand.String("name", "", "the image name ('ubuntu' etc.)")
	fauth := addCommand.String("author", "", "the author string")
	farch := addCommand.String("arch", "", "the CPU arch of the image")
	fdesc := addCommand.String("desc", "", "the image description")
	addCommand.Usage = func() {
		fmt.Fprintf(os.Stderr, "usage: %s %s [ flags ]\n\n", progname, "add")
		fmt.Fprintf(os.Stderr, "add an image file to  local repository\n")
		addCommand.PrintDefaults()
		os.Exit(1)
	}
	addCommand.Parse(args)

	mustHaveArgs := map[string]string{
		"file": *ffile,
	}

	for key, value := range mustHaveArgs {
		if value == "" {
			fmt.Fprintf(os.Stderr, "missing args for -%s\n", key)
			os.Exit(1)
		}
	}

	if n, restargs := addCommand.NArg(), addCommand.Args(); n > 0 {
		fmt.Fprintf(os.Stderr, "too many args for 'add': %q\n", restargs)
		os.Exit(1)
	}

	tracePrintf("computing blob top hash for %s\n", *ffile)

	imginfo, err := imgtool.GetImageInfo(*ffile)
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to get image info: %s\n", err)
		os.Exit(1)
	}

	if imginfo.Format != imgtool.Qcow2 {
		fmt.Fprintf(os.Stderr, "unexpected image format: %s\n", *ffile)
		os.Exit(1)
	}

	var parent string
	if imginfo.HasParent() {
		imgid, err := imginfo.GetParentImageId()
		if err != nil {
			fmt.Fprintf(os.Stderr, "unexpected parent: %s\n", imginfo.BackingFile)
			os.Exit(1)
		}

		parent = imgid.String()
	}

	// get the blob tophash and file size
	digest, size, err := getBlobDigestAndSize(*ffile)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	manifest, err := buildManifest(parent, *farch, *fname)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	manifest.Author = *fauth
	manifest.Blobsum = digest
	manifest.Created = time.Now().Format(time.RFC3339)
	manifest.Desc = *fdesc
	manifest.Size = size
	manifest.VirtualSize = imginfo.VirtualSize

	manifest.Id = manifest.GenImageId()

	tracePrintf("generated image id: %s\n", manifest.Id)

	if _, err = os.Stat(GetImageManifestPath(manifest.Name, manifest.Id)); err == nil {
		fmt.Fprintf(os.Stderr, "image already imported, id = %s\n", manifest.Id)
		os.Exit(1)
	}

	// import image to local blob registry
	blobpath := GetImageBlobPath(manifest.Name, digest)
	if err = importLocalImage(*ffile, blobpath); err != nil {
		fmt.Fprintf(os.Stderr, "failed to import local image '%s': %s\n", *ffile, err)
		os.Exit(1)
	}

	// create hard link of image file and generate local manifests
	if err = finalizeBlobAndManifest(blobpath, manifest); err != nil {
		fmt.Fprintf(os.Stderr, "failed in updating local manifest: %s", err)
		os.Exit(1)
	}

	fmt.Printf("imported image: %s\n", manifest.Id)
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

func doListTag(gopt *GlobalOpt, args []string) {
	lstagCommand := flag.NewFlagSet("lstags", flag.ExitOnError)
	lstagCommand.Usage = func() {
		fmt.Fprintf(os.Stderr, "usage: %s %s <name>\n\n", progname, "lstags")
		fmt.Fprintf(os.Stderr, "list tags of an image\n")
		lstagCommand.PrintDefaults()
		os.Exit(1)
	}
	remote := lstagCommand.Bool("remote", false, "search remote registry instead")
	lstagCommand.Parse(args)

	n, restargs := lstagCommand.NArg(), lstagCommand.Args()
	switch {
	case n == 0:
		fmt.Fprintln(os.Stderr, "missing args for 'lstags'")
		os.Exit(1)
	case n > 1:
		fmt.Fprintf(os.Stderr, "too many args for 'lstags': %q\n", restargs)
		os.Exit(1)
	}

	name := restargs[0]
	var tags map[string]string // a map from tag to image id
	var err error

	if *remote {
		tags, err = getRemoteTags(gopt, name)
	} else {
		tags, err = ListLocalTags(name)
	}

	if err != nil {
		fmt.Println(err)
		return
	}

	dumpTags(tags)
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
		fmt.Fprintf(os.Stderr, "too many args for 'images': %q\n", imagesCommand.Args())
		os.Exit(1)
	}

	printLocalImages()
}

func withClient(gopt *GlobalOpt, f func(*ZImageClient) error) {
	cln, err := New(gopt.privateKey, gopt.trustedFile, gopt.serverAddr)
	if err != nil {
		fmt.Fprintf(os.Stderr, "server connection failed: %s\n", err.Error())
		return
	}

	err = f(cln)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
	}
}
