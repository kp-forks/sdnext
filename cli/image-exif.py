#!/bin/env python

import os
import io
import re
import sys
import json
import importlib.util
from PIL import Image, ExifTags, TiffImagePlugin, PngImagePlugin
from rich import print # pylint: disable=redefined-builtin


module_file = os.path.abspath(__file__)
module_dir = os.path.dirname(module_file)
module_spec = importlib.util.spec_from_file_location('infotext', os.path.join(module_dir, '..', 'modules', 'infotext.py'))
infotext = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(infotext)



class Exif: # pylint: disable=single-string-used-for-slots
    __slots__ = ('__dict__') # pylint: disable=superfluous-parens
    def __init__(self, image = None):
        super(Exif, self).__setattr__('exif', Image.Exif()) # pylint: disable=super-with-arguments
        self.pnginfo = PngImagePlugin.PngInfo()
        self.tags = {**dict(ExifTags.TAGS.items()), **dict(ExifTags.GPSTAGS.items())}
        self.ids = {**{v: k for k, v in ExifTags.TAGS.items()}, **{v: k for k, v in ExifTags.GPSTAGS.items()}}
        if image is not None:
            self.load(image)

    def __getattr__(self, attr):
        if attr in self.__dict__:
            return self.__dict__[attr]
        return self.exif.get(attr, None)

    def load(self, img: Image):
        img.load() # exif may not be ready
        exif_dict = {}
        try:
            exif_dict = dict(img._getexif().items()) # pylint: disable=protected-access
        except Exception:
            pass
        if not exif_dict:
            exif_dict = dict(img.info.items())
        for key, val in exif_dict.items():
            if isinstance(val, bytes): # decode bytestring
                val = self.decode(val)
            if val is not None:
                if isinstance(key, str):
                    self.exif[key] = val
                    self.pnginfo.add_text(key, str(val), zip=False)
                elif isinstance(key, int) and key in ExifTags.TAGS: # add known tags
                    if self.tags[key] in ['ExifOffset']:
                        continue
                    self.exif[self.tags[key]] = val
                    self.pnginfo.add_text(self.tags[key], str(val), zip=False)
                    # if self.tags[key] == 'UserComment': # add geninfo from UserComment
                        # self.geninfo = val
                else:
                    print('metadata unknown tag:', key, val)
        for key, val in self.exif.items():
            if isinstance(val, bytes): # decode bytestring
                self.exif[key] = self.decode(val)

    def decode(self, s: bytes):
        remove_prefix = lambda text, prefix: text[len(prefix):] if text.startswith(prefix) else text # pylint: disable=unnecessary-lambda-assignment
        for encoding in ['utf-8', 'utf-16', 'ascii', 'latin_1', 'cp1252', 'cp437']: # try different encodings
            try:
                s = remove_prefix(s, b'UNICODE')
                s = remove_prefix(s, b'ASCII')
                s = remove_prefix(s, b'\x00')
                val = s.decode(encoding, errors="strict")
                val = re.sub(r'[\x00-\x09]', '', val).strip() # remove remaining special characters
                if len(val) == 0: # remove empty strings
                    val = None
                return val
            except Exception:
                pass
        return None

    def parse(self):
        x = self.exif.pop('parameters', None) or self.exif.pop('UserComment', None)
        res = infotext.parse(x)
        return res

    def get_bytes(self):
        ifd = TiffImagePlugin.ImageFileDirectory_v2()
        exif_stream = io.BytesIO()
        for key, val in self.exif.items():
            if key in self.ids:
                ifd[self.ids[key]] = val
            else:
                print('metadata unknown exif tag:', key, val)
        ifd.save(exif_stream)
        raw = b'Exif\x00\x00' + exif_stream.getvalue()
        return raw


def print_json(data):
    try:
        for k, v in data.items():
            print(f'json: k={k}', json.loads(v))
    except Exception:
        pass


def read_exif(filename: str):
    if filename.lower().endswith('.heic'):
        from pi_heif import register_heif_opener
        register_heif_opener()
    try:
        image = Image.open(filename)
        exif = Exif(image)
        print('image:', filename, 'format:', image)
        data = vars(exif.exif)['_data']
        print('exif:', data)
        print('info:', exif.parse())
        print_json(data)
    except Exception as e:
        print('metadata error reading:', filename, e)


if __name__ == '__main__':
    sys.argv.pop(0)
    if len(sys.argv) == 0:
        print('metadata:', 'no files specified')
    for fn in sys.argv:
        if os.path.isfile(fn):
            read_exif(fn)
        elif os.path.isdir(fn):
            for root, _dirs, files in os.walk(fn):
                for file in files:
                    read_exif(os.path.join(root, file))
        else:
            print('file not found: ', fn)
