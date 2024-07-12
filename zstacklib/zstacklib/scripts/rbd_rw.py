import ctypes
ctypes.CDLL('/lib64/librados.so', ctypes.RTLD_GLOBAL)
import rados
import rbd
import sys

external_conf = {}
external_conf['do_lunmap'] = 'false'

def read_rbd_image(pool_name, image_name, offset=0, size=sys.maxsize):
    # Connect to the cluster
    with rados.Rados(conffile='/etc/xstor.conf', conf=external_conf) as cluster:
        # Open the pool
        with cluster.open_ioctx(pool_name) as ioctx:
            # Open the image
            with rbd.Image(ioctx, image_name) as image:

                # Read image size
                image_size = image.size()
                total_size = min(size, image_size - offset)
                read_size = 0

                # Read and output the image content
                chunk_size = 4 * 1024 * 1024  # 4MB
                while read_size < total_size:
                    chunk = min(chunk_size, total_size - read_size)
                    data = image.read(offset + read_size, chunk)
                    sys.stdout.write(data)
                    read_size += chunk

def write_rbd_image(pool_name, image_name, offset=0, content=None):
    # Connect to the cluster
    with rados.Rados(conffile='/etc/xstor.conf', conf=external_conf) as cluster:
        # Open the pool
        with cluster.open_ioctx(pool_name) as ioctx:
            # Open the image
            with rbd.Image(ioctx, image_name) as image:
                # Write the content to the image
                image.write(content, offset)


if __name__ == '__main__':
    if len(sys.argv) != 5 and len(sys.argv) != 3:
        print >> sys.stderr, "Usage: {} <operation> <pool_name>/<image_name> [offset] [size/content]".format(sys.argv[0])
        print >> sys.stderr, "system arguments: {}".format(sys.argv)
        print >> sys.stderr, "args length: {}".format(len(sys.argv))
        sys.exit(1)

    op = sys.argv[1]
    path = sys.argv[2]
    path = path.replace('rbd:', '')
    pool_name = path.split('/')[0]
    image_name = path.split('/')[1]
    if op == 'read':
        if len(sys.argv) == 5:
            offset = int(sys.argv[3])
            size = int(sys.argv[4])
            read_rbd_image(pool_name, image_name, offset, size)
        else:
            read_rbd_image(pool_name, image_name)
    elif op == 'write':
        if len(sys.argv) == 5:
            offset = int(sys.argv[3])
            content = sys.argv[4]
            write_rbd_image(pool_name, image_name, offset, content)
        else:
            write_rbd_image(pool_name, image_name)
    else:
        print >> sys.stderr, "Unknown operation: {}".format(op)
        sys.exit(1)
