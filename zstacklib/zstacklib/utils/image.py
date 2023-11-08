from PIL import Image
import os

def convert_image(src_path, size=(120, 68), format='PNG'):
    with open(src_path, 'rb') as f:
        img = Image.open(f)
        img = img.resize(size, Image.ANTIALIAS)
        img = img.convert('RGB')
    dst_path = os.path.splitext(src_path)[0] + '.' + format.lower()
    with open(dst_path, 'wb') as f:
        img.save(f, format)
    return dst_path