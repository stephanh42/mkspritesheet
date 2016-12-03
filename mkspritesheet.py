from PIL import Image
import numpy
import sys
import operator
import json
from collections import namedtuple
import os.path
import argparse

class Rect(namedtuple("Rect", "x1 y1 x2 y2")):
    """A 2D rectangle"""

    def overlaps(self, other):
        ax1, ay1, ax2, ay2 = self
        bx1, by1, bx2, by2 = other
        return ax2 > bx1 and bx2 > ax1 and ay2 > by1 and by2 > ay1

    def size(self):
        x1, y1, x2, y2 = self
        return (x2 - x1, y2 - y1)

    def fits(self, W, H):
        x1, y1, x2, y2 = self
        return W <= (x2 - x1) and H <= (y2 - y1)

    def split(self, other):
        if not self.overlaps(other):
            return None
        ax1, ay1, ax2, ay2 = self
        bx1, by1, bx2, by2 = other
        result = []
        if by1 > ay1:
            result.append(Rect(ax1, ay1, ax2, by1))
        if bx1 > ax1:
            result.append(Rect(ax1, ay1, bx1, ay2))
        if bx2 < ax2:
            result.append(Rect(bx2, ay1, ax2, ay2))
        if by2 < ay2:
            result.append(Rect(ax1, by2, ax2, ay2))
        return result

class Region(object):
    """A 2D rectilinear region."""

    children = None

    def __init__(self, rect):
        self.rect = rect

    def find_fit(self, W, H):
        rect = self.rect
        if not rect.fits(W, H):
            return None
        children = self.children
        if children is None:
            return Rect(rect.x1, rect.y1, rect.x1 + W, rect.y1 + H)
        for child in children:
            result = child.find_fit(W, H)
            if result is not None:
                return result
        return None

    def is_empty(self):
        children = self.children
        return children is not None and not children

    def remove_rect(self, rect):
        children = self.children
        if children is None:
            splitted = self.rect.split(rect)
            if splitted is not None:
                self.children = [Region(r) for r in splitted]
        elif self.rect.overlaps(rect):
            for child in children:
                child.remove_rect(rect)
            self.children = [child for child in children if not child.is_empty()]


def get_range(alpha, axis):
    """ Given an alpha mask and an axis, get the range of non-zero values."""
    alpha = numpy.bitwise_or.reduce(alpha, axis)
    nonzero = numpy.nonzero(alpha)[0]
    if len(nonzero) > 0:
        return (int(nonzero[0]), int(nonzero[-1] + 1))
    else:
        return (0, 0)

def compute_clip_rect(im):
    try:
        alpha_band = im.getbands().index('A')
    except ValueError:
        return (im, (0, 0, im.width, im.height))
    alpha = numpy.array(im)[:,:,alpha_band]
    x1, x2 = get_range(alpha, 0)
    y1, y2 = get_range(alpha, 1)
    box = (x1, y1, x2, y2)
    return (im.crop(box=box), box)

class ImageInfo(object):
    """All needed information for a single image."""

    rect = None
    def __init__(self, filename):
        self.filename = filename
        image = Image.open(filename)
        self.original_size = image.size
        self.image, self.box = compute_clip_rect(image)
        x1, y1, x2, y2 = self.box
        W = x2 - x1
        H = y2 - y1
        self.actual_size = (max(W, H), min(W, H))
        self.area = W * H

def main():
    parser = argparse.ArgumentParser(prog='mkspritesheet')
    parser.add_argument('filename', nargs='+')
    parser.add_argument("-o", "--output", help="base name of output files")
    parsed = parser.parse_args()
    output_basename = parsed.output
    if output_basename is None:
        output_basename = "spritesheet"

    output_filename = os.path.abspath(output_basename + ".png")
    images = [ImageInfo(filename) for filename in parsed.filename if os.path.abspath(filename) != output_filename]
    images.sort(key=operator.attrgetter('area', 'actual_size'), reverse=True)
    max_W = max(im.actual_size[0] for im in images)
    total_area = sum(im.area for im in images)

    output_W = 1; output_H = 1
    while output_W < max_W:
        output_W *= 2
    while output_W * output_H < total_area:
        if output_W <= output_H:
            output_W *= 2
        else:
            output_H *= 2

    while True:
        region = Region(Rect(0, 0, output_W, output_H))
        incomplete = False
        for im in images:
            W, H = im.actual_size
            if W == 0 and H == 0:
                rect = Rect(0, 0, 0, 0)
            else:
                rect = region.find_fit(W, H)
                if rect is None:
                    rect = region.find_fit(H, W)
            if rect is not None:
                im.rect = rect
                region.remove_rect(rect)
            else:
#                print("Cannot fit: ", im.filename, im.actual_size)
                incomplete = True
                break
        if incomplete:
            if output_W <= output_H:
                output_W *= 2
            else:
                output_H *= 2
        else:
            break

    output_im = Image.new("RGBA", (output_W, output_H), color=(0, 0, 0, 0))

    output_json = {}

    for im_info in images:
        im = im_info.image
        im_json = {}
        im_json["size"] = im_info.original_size
        im_json["xy"] = im_info.box
        rect = im_info.rect
        s1, t1, s2, t2 = rect
        im_json["st"] = [s1/output_W, t1/output_H, s2/output_W, t2/output_H]
#        im_json["st"] = [s1, t1, s2, t2]
        if rect.size() != im.size:
            im = im.transpose(Image.TRANSPOSE)
            transposed = True
        else:
            transposed = False
        assert rect.size() == im.size
        im_json["transposed"] = transposed
        output_im.paste(im, box=rect)
        output_json[im_info.filename] = im_json

    with open(output_basename + ".json", "w") as f:
        json.dump(output_json, f, sort_keys=True, indent="\t")

    print("Size: %dx%d, fill: %f%%" % (output_W, output_H, 100 * total_area / (output_W * output_H)))
    output_im.save(output_filename)

if __name__ == "__main__":
    main()
