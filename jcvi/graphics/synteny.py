#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
%prog mcscan.txt all.bed layout.csv

Illustrate MCscan multiple collinearity alignments. Use layout.csv to indicate
the positions of tracks. For example:

#x, y, rotation, ha, va, color, ratio
0.5, 0.6, 0, left, center, g
0.25, 0.7, 45, top, center, m

With the row ordering corresponding to the column ordering in the MCscan output.
"""
from __future__ import print_function


import sys
import logging
import numpy as np

from jcvi.compara.synteny import BlockFile
from jcvi.formats.bed import Bed
from jcvi.formats.base import DictFile
from jcvi.utils.cbook import human_size
from jcvi.apps.base import OptionParser

from jcvi.graphics.glyph import Glyph, RoundLabel
from jcvi.graphics.base import mpl, plt, savefig, markup, \
            Path, PathPatch, AbstractLayout


forward, backward = 'b', 'g'  # Genes with different orientations


class LayoutLine (object):

    def __init__(self, row, delimiter=','):
        self.hidden = row[0] == '*'
        if self.hidden:
            row = row[1:]
        args = row.rstrip().split(delimiter)
        args = [x.strip() for x in args]
        self.x = float(args[0])
        self.y = float(args[1])
        self.rotation = int(args[2])
        self.ha = args[3]
        self.va = args[4]
        self.color = args[5]
        self.ratio = 1
        if len(args) > 6:
            self.ratio = float(args[6])
        if len(args) > 7:
            self.label = args[7].strip()
        else:
            self.label = None


class Layout (AbstractLayout):

    def __init__(self, filename, delimiter=','):
        super(Layout, self).__init__(filename)
        fp = open(filename)
        self.edges = []
        for row in fp:
            if row[0] == '#':
                continue
            if row[0] == 'e':
                args = row.rstrip().split(delimiter)
                args = [x.strip() for x in args]
                a, b = args[1:3]
                if len(args) == 4 and args[3]:
                    samearc = args[3]
                else:
                    samearc = None
                a, b = int(a), int(b)
                assert args[0] == 'e'
                self.edges.append((a, b, samearc))
            else:
                self.append(LayoutLine(row, delimiter=delimiter))

        if 3 <= len(self) <= 8:
            self.assign_colors()


class Shade (object):

    def __init__(self, ax, a, b, ymid, highlight=False, ec="k", fc="k",
                    alpha=.2, lw=1, zorder=1):
        a1, a2 = a
        b1, b2 = b
        ax1, ay1 = a1
        ax2, ay2 = a2
        bx1, by1 = b1
        bx2, by2 = b2
        M, C4, L, CP = Path.MOVETO, Path.CURVE4, Path.LINETO, Path.CLOSEPOLY
        pathdata = \
        [
            (M, a1),
            (C4, (ax1, ymid)),
            (C4, (bx1, ymid)),
            (C4, b1),
            (L, b2),
            (C4, (bx2, ymid)),
            (C4, (ax2, ymid)),
            (C4, a2),
            (CP, a1)
        ]
        codes, verts = zip(*pathdata)
        path = Path(verts, codes)
        if highlight:
            ec = fc = highlight

        pp = PathPatch(path, ec=ec, fc=fc, alpha=alpha,
                     lw=lw, zorder=zorder)
        ax.add_patch(pp)


class Region (object):

    def __init__(self, ax, ext, layout, bed, scale, switch=None,
                 chr_label=True, loc_label=True,
                 pad=.05, vpad=.015, extra_features=None):
        x, y = layout.x, layout.y
        ratio = layout.ratio
        scale /= ratio
        self.y = y
        lr = layout.rotation
        tr = mpl.transforms.Affine2D().\
                    rotate_deg_around(x, y, lr) + ax.transAxes
        inv = ax.transAxes.inverted()

        start, end, si, ei, chr, orientation, span = ext
        flank = span / scale / 2
        xstart, xend = x - flank, x + flank
        self.xstart, self.xend = xstart, xend

        cv = lambda t: xstart + abs(t - startbp) / scale
        hidden = layout.hidden

        # Chromosome
        if not hidden:
            ax.plot((xstart, xend), (y, y), color="gray", transform=tr, \
                    lw=2, zorder=1)

        self.genes = genes = bed[si: ei + 1]
        startbp, endbp = start.start, end.end
        if orientation == '-':
            startbp, endbp = endbp, startbp

        if switch:
            chr = switch.get(chr, chr)
        if layout.label:
            chr = layout.label

        label = "-".join((human_size(startbp, target="Mb", precision=2)[:-2],
                          human_size(endbp, target="Mb", precision=2)))

        height = .012
        self.gg = {}
        # Genes
        for g in genes:
            gstart, gend = g.start, g.end
            strand = g.strand
            if strand == '-':
                gstart, gend = gend, gstart
            if orientation == '-':
                strand = "+" if strand == "-" else "-"

            x1, x2, a, b = self.get_coordinates(gstart, gend, y, cv, tr, inv)
            self.gg[g.accn] = (a, b)

            color = forward if strand == "+" else backward
            if not hidden:
                gp = Glyph(ax, x1, x2, y, height, gradient=False, fc=color, zorder=3)
                gp.set_transform(tr)

        # Extra features (like repeats)
        if extra_features:
            for g in extra_features:
                gstart, gend = g.start, g.end
                x1, x2, a, b = self.get_coordinates(gstart, gend, y, cv, tr, inv)
                gp = Glyph(ax, x1, x2, y, height * 3 / 4, gradient=False,
                           fc='#ff7f00', zorder=2)
                gp.set_transform(tr)

        ha, va = layout.ha, layout.va

        hpad = .02
        if ha == "left":
            xx = xstart - hpad
            ha = "right"
        elif ha == "right":
            xx = xend + hpad
            ha = "left"
        else:
            xx = x
            ha = "center"

        # Tentative solution to labels stick into glyph
        magic = 40.
        cc = abs(lr) / magic if abs(lr) > magic else 1
        if va == "top":
            yy = y + cc * pad
        elif va == "bottom":
            yy = y - cc * pad
        else:
            yy = y

        l = np.array((xx, yy))
        trans_angle = ax.transAxes.transform_angles(np.array((lr, )),
                                                    l.reshape((1, 2)))[0]
        lx, ly = l
        if not hidden:
            bbox = dict(boxstyle="round", fc='w', ec='w', alpha=.5)
            kwargs = dict(ha=ha, va="center",
                          rotation=trans_angle, bbox=bbox, zorder=10)

            # TODO: I spent several hours on trying to make this work - with no
            # good solutions. To generate labels on multiple lines, each line
            # with a different style is difficult in matplotlib. The only way,
            # if you can tolerate an extra dot (.), is to use the recipe below.
            #chr_label = r"\noindent " + markup(chr) + r" \\ ." if chr_label else None
            #loc_label = r"\noindent . \\ " + label if loc_label else None

            chr_label = markup(chr) if chr_label else None
            loc_label = label if loc_label else None
            if chr_label:
                if loc_label:
                    ax.text(lx, ly + vpad, chr_label, color=layout.color, **kwargs)
                    ax.text(lx, ly - vpad, loc_label, color="lightslategrey",
                            size=10, **kwargs)
                else:
                    ax.text(lx, ly, chr_label, color=layout.color, **kwargs)

    def get_coordinates(self, gstart, gend, y, cv, tr, inv):
        x1, x2 = cv(gstart), cv(gend)
        a, b = tr.transform((x1, y)), tr.transform((x2, y))
        a, b = inv.transform(a), inv.transform(b)
        return x1, x2, a, b


class Synteny (object):

    def __init__(self, fig, root, datafile, bedfile, layoutfile,
                 switch=None, tree=None, extra_features=None,
                 chr_label=True, loc_label=True, pad=.05, vpad=.015,
                 scalebar=False):

        w, h = fig.get_figwidth(), fig.get_figheight()
        bed = Bed(bedfile)
        order = bed.order
        bf = BlockFile(datafile)
        self.layout = lo = Layout(layoutfile)
        switch = DictFile(switch, delimiter="\t") if switch else None
        if extra_features:
            extra_features = Bed(extra_features)

        exts = []
        extras = []
        for i in range(bf.ncols):
            ext = bf.get_extent(i, order)
            exts.append(ext)
            if extra_features:
                start, end, si, ei, chr, orientation, span = ext
                start, end = start.start, end.end  # start, end coordinates
                ef = list(extra_features.extract(chr, start, end))

                # Pruning removes minor features with < 0.1% of the region
                ef_pruned = [x for x in ef if x.span >= span / 1000]
                print("Extracted {0} features "\
                        "({1} after pruning)".format(len(ef), len(ef_pruned)), file=sys.stderr)
                extras.append(ef_pruned)

        maxspan = max(exts, key=lambda x: x[-1])[-1]
        scale = maxspan / .65

        self.gg = gg = {}
        self.rr = []
        ymids = []
        #vpad = .012 * w / h
        for i in range(bf.ncols):
            ext = exts[i]
            ef = extras[i] if extras else None
            r = Region(root, ext, lo[i], bed, scale, switch,
                       chr_label=chr_label, loc_label=loc_label,
                       vpad=vpad, extra_features=ef)
            self.rr.append(r)
            # Use tid and accn to store gene positions
            gg.update(dict(((i, k), v) for k, v in r.gg.items()))
            ymids.append(r.y)

        for i, j, samearc in lo.edges:
            for ga, gb, h in bf.iter_pairs(i, j):
                a, b = gg[(i, ga)], gg[(j, gb)]
                if samearc == "above":
                    ymid = ymids[i] + 2 * pad
                elif samearc == "below":
                    ymid = ymids[i] - 2 * pad
                else:
                    ymid = (ymids[i] + ymids[j]) / 2
                Shade(root, a, b, ymid, fc="gainsboro", lw=0, alpha=1)

            for ga, gb, h in bf.iter_pairs(i, j, highlight=True):
                a, b = gg[(i, ga)], gg[(j, gb)]
                if samearc == "above":
                    ymid = ymids[i] + 2 * pad
                elif samearc == "below":
                    ymid = ymids[i] - 2 * pad
                else:
                    ymid = (ymids[i] + ymids[j]) / 2
                Shade(root, a, b, ymid, alpha=1, highlight=h, zorder=2)

        if scalebar:
            print("Build scalebar (scale={})".format(scale), file=sys.stderr)
            # Find the best length of the scalebar
            ar = [1, 2, 5]
            candidates = [1000 * x for x in ar] + [10000 * x for x in ar] + \
                         [100000 * x for x in ar]
            # Find the one that's close to an optimal canvas size
            dists = [(abs(x / scale - .12), x) for x in candidates]
            dist, candidate = min(dists)
            dist = candidate / scale
            x, y, yp = .2, .96, .005
            a, b = x - dist / 2, x + dist / 2
            lsg = "lightslategrey"
            root.plot([a, a], [y - yp, y + yp], "-", lw=2, color=lsg)
            root.plot([b, b], [y - yp, y + yp], "-", lw=2, color=lsg)
            root.plot([a, b], [y, y], "-", lw=2, color=lsg)
            root.text(x, y + .02, human_size(candidate, precision=0),
                      ha="center", va="center")

        if tree:
            from jcvi.graphics.tree import draw_tree, read_trees

            trees = read_trees(tree)
            ntrees = len(trees)
            logging.debug("A total of {0} trees imported.".format(ntrees))
            xiv = 1. / ntrees
            yiv = .3
            xstart = 0
            ystart = min(ymids) - .4
            for i in range(ntrees):
                ax = fig.add_axes([xstart, ystart, xiv, yiv])
                label, outgroup, color, tx = trees[i]
                draw_tree(ax, tx, outgroup=outgroup, rmargin=.4, leaffont=11,
                          treecolor=color, supportcolor=color, leafcolor=color)
                xstart += xiv
                RoundLabel(ax, .5, .3, label, fill=True, fc="lavender",
                           color=color)


def draw_gene_legend(ax, x1, x2, ytop, d=.04, text=False, repeat=False):
    ax.plot([x1, x1 + d], [ytop, ytop], ":", color=forward, lw=2)
    ax.plot([x1 + d], [ytop], ">", color=forward, mec=forward)
    ax.plot([x2, x2 + d], [ytop, ytop], ":", color=backward, lw=2)
    ax.plot([x2], [ytop], "<", color=backward, mec="g")
    if text:
        ax.text(x1 + d / 2, ytop + d / 2, "gene (+)", ha="center")
        ax.text(x2 + d / 2, ytop + d / 2, "gene (-)", ha="center")
    if repeat:
        xr = (x1 + x2 + d) / 2
        Glyph(ax, xr - d / 2, xr + d / 2, ytop, .012 * 3 / 4, gradient=False,
              fc='#ff7f00', zorder=2)
        ax.text(xr, ytop + d / 2, "repeat", ha="center")


def main():
    p = OptionParser(__doc__)
    p.add_option("--switch",
                 help="Rename the seqid with two-column file [default: %default]")
    p.add_option("--tree",
                 help="Display trees on the bottom of the figure [default: %default]")
    p.add_option("--extra", help="Extra features in BED format")
    p.add_option("--scalebar", default=False, action="store_true",
                 help="Add scale bar to the plot")
    opts, args, iopts = p.set_image_options(figsize="8x7")

    if len(args) != 3:
        sys.exit(not p.print_help())

    datafile, bedfile, layoutfile = args
    switch = opts.switch
    tree = opts.tree

    pf = datafile.rsplit(".", 1)[0]
    fig = plt.figure(1, (iopts.w, iopts.h))
    root = fig.add_axes([0, 0, 1, 1])

    Synteny(fig, root, datafile, bedfile, layoutfile,
            switch=switch, tree=tree, extra_features=opts.extra,
            scalebar=opts.scalebar)

    root.set_xlim(0, 1)
    root.set_ylim(0, 1)
    root.set_axis_off()

    image_name = pf + "." + iopts.format
    savefig(image_name, dpi=iopts.dpi, iopts=iopts)


if __name__ == '__main__':
    main()
