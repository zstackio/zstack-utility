# The Image Store for Zstack

This repository contains the source code for the disk image store for
Zstack. It is similar to Docker registry, but simplified.


## Certificate Manager

The certificate manager is based on the `libtrust` facility.
`libtrust` has the following:

The server side has the following:

- Server Private Key
- Server Public Key
- Trusted Clients (Client Public Key)

Similarly, the client side has the following:

- Client Private Key
- Client Public key
- Trusted Hosts (Server Public Key)

The client and server will authenticate each other during TLS
handshake.

The certificate manager will first generate the private and public key
for the server.  Then, for each client, generate its private and
public key, and add its public key to trusted clients.

## Test with cURL

~~~
$ go run gencert.go
$ curl -i -k --cert cert.pem --key key.pem https://localhost:8000/v1/; echo
~~~
