"""Optional Black 2 / White 2 animated battle sprites for the pack: converted from the GIFs gen5_sources.py lists.

The pictures are not in the player's FireRed ROM and never ship with Twin
Embers. When the player picks them for the battles (the Builder's "battle
sprites" choice: FireRed's, HeartGold's or these), the HeartGold download
(gen4_sprites.Downloader) fetches the GIFs from PokeAPI/sprites at the pinned
commit, keeps each one only if its size and SHA-256 match the list, and this
module converts it. A species without its files keeps FireRed's pictures.
Black 2 and White 2 show Black and White's own sprites for national dex
1-386, so the files are those games' animations.

Pack entries, one per picture with a complete pair of colours:

    graphics/gen5/front/NNN.bin     NNN = national dex number, 001-386 (386 is Deoxys' Attack Forme)
    graphics/gen5/front/NNN_f.bin   the female's own picture, for the species that have one
    graphics/gen5/front/201_FF.bin  Unown's letters, FF = 01-27 (B to Z, !, ?), as FireRed numbers them
    graphics/gen5/front/351_FF.bin  Castform's weather forms, FF = 01-03 (sun, rain, ice)
    graphics/gen5/back/...          the same for the back pictures

Layout (little endian):

    0    b"G5A1"
    4    u8   columns, u8 rows: the picture's size in 8x8 tiles (at most MAX_TILES each)
    6    u16  images: the distinct pictures of the animation (at most MAX_IMAGES)
    8    u16 x 16  normal palette, BGR555 as the GBA's (colour 0 is transparent)
    40   u16 x 16  shiny palette, the same colour indices
    72   u16  steps: the animation's frames in order (at most MAX_STEPS)
    74   u16  anchorX2: twice the x of the middle of the first picture's opaque columns
    76   u16  feet: the first picture's lowest opaque row
    78   u16  top: its highest opaque row
    80   steps x (u16 image, u16 ticks): which picture, for how long (60 ticks a second)
    then (images + 1) x u32: where each picture's data starts, from the end of this table, and where the last ends
    then each picture: columns x rows 4bpp tiles (32 bytes each, the GBA's layout, rows of tiles top to bottom),
         PackBits-compressed (a byte n < 128: n + 1 literal bytes follow; n > 128: the next byte 257 - n times)

The GIFs keep transparency as one colour index and draw each frame over the
last (their disposal methods are followed). A picture with more than 15
colours (a few backs, where the GIF blended two palettes) has its rarest
colours folded into their nearest ones, as gen4_sprites.quantize does. The
shiny GIF gives the shiny palette: its pixels are matched to the normal
picture's, a shiny GIF being the same animation in other colours, sometimes a
pixel or two off on its canvas.
"""
from __future__ import annotations

import struct

from . import gen5_sources

MAGIC = b"G5A1"
HEADER = 80
MAX_TILES = 20          # 160 pixels: the largest picture is 153
MAX_IMAGES = 255
MAX_STEPS = 1024
FRONT_PREFIX = "graphics/gen5/front/"
BACK_PREFIX = "graphics/gen5/back/"
VARIANTS = ("normal", "shiny", "female_normal", "female_shiny")


class Gen5Error(ValueError):
    pass


# --- GIF ---------------------------------------------------------------------------------------

def _blocks(data: bytes, pos: int) -> tuple[bytes, int]:
    out = bytearray()
    while True:
        if pos >= len(data):
            raise Gen5Error("GIF data ends inside a block")
        size = data[pos]
        pos += 1
        if not size:
            return bytes(out), pos
        out += data[pos:pos + size]
        pos += size


def _lzw(data: bytes, minimum: int, count: int) -> bytes:
    """The `count` colour indices of an image's LZW data."""
    if not 2 <= minimum <= 8:
        raise Gen5Error("bad LZW code size")
    clear, end = 1 << minimum, (1 << minimum) + 1
    base = [bytes((i,)) for i in range(clear)] + [b"", b""]
    table = list(base)
    size = minimum + 1
    out = bytearray()
    previous = None
    bits = value = 0
    for byte in data:
        value |= byte << bits
        bits += 8
        while bits >= size:
            code = value & ((1 << size) - 1)
            value >>= size
            bits -= size
            if code == clear:
                table = list(base)
                size = minimum + 1
                previous = None
                continue
            if code == end:
                return bytes(out[:count]) if len(out) >= count else bytes(out) + bytes(count - len(out))
            if previous is None:
                if code >= len(table):
                    raise Gen5Error("bad LZW code")
                entry = table[code]
            elif code < len(table):
                entry = table[code]
                if len(table) < 4096:
                    table.append(previous + entry[:1])
            elif code == len(table):
                entry = previous + previous[:1]
                if len(table) < 4096:
                    table.append(entry)
            else:
                raise Gen5Error("bad LZW code")
            out += entry
            previous = entry
            if len(table) == 1 << size and size < 12:
                size += 1
    if len(out) < count:
        out += bytes(count - len(out))
    return bytes(out[:count])


def read_gif(data: bytes) -> tuple[int, int, list[tuple[int, int, int]], list[tuple[bytes, int]]]:
    """(width, height, colours, frames) of a GIF: each frame the whole canvas as it shows, one byte a pixel (0
    transparent, n the colour colours[n - 1] as RGB), and its delay in hundredths of a second."""
    if data[:6] not in (b"GIF87a", b"GIF89a") or len(data) < 13:
        raise Gen5Error("not a GIF file")
    width, height, flags = struct.unpack_from("<HHB", data, 6)
    if not width or not height or width > MAX_TILES * 8 or height > MAX_TILES * 8:
        raise Gen5Error("GIF of %dx%d" % (width, height))
    pos = 13
    global_table = []
    if flags & 0x80:
        n = 2 << (flags & 7)
        global_table = [tuple(data[pos + i * 3:pos + i * 3 + 3]) for i in range(n)]
        pos += 3 * n
    colours: dict[tuple[int, int, int], int] = {}
    canvas = bytearray(width * height)
    frames: list[tuple[bytes, int]] = []
    delay, transparent, disposal = 0, -1, 0
    while pos < len(data):
        kind = data[pos]
        pos += 1
        if kind == 0x3B:
            break
        if kind == 0x21:
            label = data[pos]
            body, pos = _blocks(data, pos + 1)
            if label == 0xF9 and len(body) >= 4:
                packed, delay, index = struct.unpack_from("<BHB", body)
                disposal = (packed >> 2) & 7
                transparent = index if packed & 1 else -1
            continue
        if kind != 0x2C:
            raise Gen5Error("unknown GIF block")
        left, top, w, h, packed = struct.unpack_from("<HHHHB", data, pos)
        pos += 9
        table = global_table
        if packed & 0x80:
            n = 2 << (packed & 7)
            table = [tuple(data[pos + i * 3:pos + i * 3 + 3]) for i in range(n)]
            pos += 3 * n
        minimum = data[pos]
        lzw, pos = _blocks(data, pos + 1)
        pixels = _lzw(lzw, minimum, w * h)
        if packed & 0x40:       # interlaced: rows 0, 8.., 4.., 2.., 1..
            order = list(range(0, h, 8)) + list(range(4, h, 8)) + list(range(2, h, 4)) + list(range(1, h, 2))
            rows = [b""] * h
            for i, y in enumerate(order):
                rows[y] = pixels[i * w:(i + 1) * w]
            pixels = b"".join(rows)
        translate = bytearray(256)
        for index in sorted(set(pixels)):
            if index == transparent or index >= len(table):
                continue
            rgb = table[index]
            if rgb not in colours:
                if len(colours) == 255:
                    raise Gen5Error("more than 255 colours")
                colours[rgb] = len(colours) + 1
            translate[index] = colours[rgb]
        pixels = pixels.translate(bytes(translate))
        saved = bytes(canvas) if disposal == 3 else None
        right, bottom = min(left + w, width), min(top + h, height)
        if left < right and top < bottom:
            for y in range(top, bottom):
                row = pixels[(y - top) * w:(y - top) * w + right - left]
                at = y * width + left
                if 0 not in row:
                    canvas[at:at + len(row)] = row
                else:
                    for x, value in enumerate(row):
                        if value:
                            canvas[at + x] = value
        frames.append((bytes(canvas), delay))
        if disposal == 2 and left < right and top < bottom:
            for y in range(top, bottom):
                canvas[y * width + left:y * width + right] = bytes(right - left)
        elif saved is not None:
            canvas[:] = saved
        delay, transparent, disposal = 0, -1, 0
    if not frames:
        raise Gen5Error("GIF without a frame")
    order = sorted(colours, key=colours.get)
    return width, height, order, frames


# --- conversion --------------------------------------------------------------------------------

def _bgr555(rgb: tuple[int, int, int]) -> int:
    r, g, b = rgb
    return (r >> 3) | (g >> 3) << 5 | (b >> 3) << 10


def _channels(c: int) -> tuple[int, int, int]:
    return c & 31, (c >> 5) & 31, (c >> 10) & 31


def _near(colour: int, choices) -> int:
    return min(choices, key=lambda c: (sum((a - b) ** 2 for a, b in zip(_channels(c), _channels(colour))), c))


def reduce_palette(colours: list[tuple[int, int, int]], frames: list[bytes], limit: int = 15) -> tuple[list[int], bytes]:
    """The frames' colours (1-based ids into `colours`) as at most `limit` BGR555 ones: (the palette, colour 0 the
    transparent one, and the 256-byte table from a colour id to its index). The rarest colour is folded into its
    nearest one until they fit."""
    counts: dict[int, int] = {}
    for frame in frames:
        for cid in range(1, len(colours) + 1):
            n = frame.count(cid)
            if n:
                key = _bgr555(colours[cid - 1])
                counts[key] = counts.get(key, 0) + n
    merged = {c: c for c in counts}
    while len(counts) > limit:
        rare = min(counts, key=lambda c: (counts[c], c))
        near = _near(rare, [c for c in counts if c != rare])
        counts[near] += counts.pop(rare)
        for c, into in merged.items():
            if into == rare:
                merged[c] = near
    order = sorted(counts, key=lambda c: (-counts[c], c))
    table = bytearray(256)
    for cid in range(1, len(colours) + 1):
        key = _bgr555(colours[cid - 1])
        if key in merged:
            table[cid] = order.index(merged[key]) + 1
    return [0] + order, bytes(table)


def _shape(frame: bytes, width: int) -> tuple[tuple[int, int, int, int], bytes] | None:
    """A frame's opaque box (left, top, right, bottom) and, inside it, which pixels are opaque; None if none is."""
    height = len(frame) // width
    rows = [y for y in range(height) if frame[y * width:(y + 1) * width].count(0) != width]
    if not rows:
        return None
    top, bottom = rows[0], rows[-1] + 1
    left, right = width, 0
    for y in range(top, bottom):
        line = frame[y * width:(y + 1) * width]
        opaque = [x for x, p in enumerate(line) if p]
        if opaque:
            left, right = min(left, opaque[0]), max(right, opaque[-1] + 1)
    opaque = bytes([0] + [1] * 255)
    mask = b"".join(frame[y * width + left:y * width + right].translate(opaque) for y in range(top, bottom))
    return (left, top, right, bottom), mask


def shiny_palette(normal: list[int], indexed: list[bytes], width: int,
                  shiny: tuple[int, int, list[tuple[int, int, int]], list[tuple[bytes, int]]]) -> list[int]:
    """The shiny GIF's colour for each index of the normal palette, from the pixels of its frames that show the same
    shape as a normal one (wherever on the canvas: the shiny GIF may be cropped a few pixels otherwise, and have more or
    fewer frames). An index never matched keeps its normal colour."""
    sw, _, scolours, sframes = shiny
    # Frames of the same shape may differ in colour (a blink), so a normal frame takes the shiny frame of its shape
    # nearest its own place in the animation.
    shapes: dict[bytes, list[tuple[float, bytes, tuple]]] = {}
    for j, (frame, _) in enumerate(sframes):
        shape = _shape(frame, sw)
        if shape is not None:
            key = shape[1] + bytes(str(shape[0][2] - shape[0][0]), "ascii")
            shapes.setdefault(key, []).append((j / len(sframes), frame, shape[0]))
    votes: list[dict[int, int]] = [{} for _ in normal]
    fallback: list[dict[int, int]] = [{} for _ in normal]
    seen = set()
    for i, frame in enumerate(indexed):
        if frame in seen:
            continue
        seen.add(frame)
        shape = _shape(frame, width)
        if shape is None:
            continue
        candidates = shapes.get(shape[1] + bytes(str(shape[0][2] - shape[0][0]), "ascii"))
        if not candidates:
            continue
        place = i / len(indexed)
        _, other, (sl, st, _, _) = min(candidates, key=lambda c: abs(c[0] - place))
        (left, top, right, bottom) = shape[0]
        for y in range(top, bottom):
            for x in range(left, right):
                index = frame[y * width + x]
                if index:
                    cid = other[(st + y - top) * sw + sl + x - left]
                    c = _bgr555(scolours[cid - 1])
                    votes[index][c] = votes[index].get(c, 0) + 1
    if any(not votes[index] for index in range(1, len(normal))):
        # Shapes that never match (a shiny GIF of another cut of the animation): the first frames, their opaque
        # boxes' corners together, for the indices still without a colour.
        first, shape = indexed[0], _shape(indexed[0], width)
        other = next((frame for frame, _ in sframes if _shape(frame, sw) is not None), None)
        if shape is not None and other is not None:
            (left, top, right, bottom), (sl, st, sr, sb) = shape[0], _shape(other, sw)[0]
            for y in range(top, min(bottom, top + sb - st)):
                for x in range(left, min(right, left + sr - sl)):
                    index = first[y * width + x]
                    cid = other[(st + y - top) * sw + sl + x - left]
                    if index and cid:
                        c = _bgr555(scolours[cid - 1])
                        fallback[index][c] = fallback[index].get(c, 0) + 1
            for index in range(1, len(normal)):
                if not votes[index]:
                    votes[index] = fallback[index]
    result = list(normal)
    for index in range(1, len(normal)):
        if votes[index]:
            result[index] = max(votes[index], key=lambda c: (votes[index][c], -c))
    return result


def packbits(data: bytes) -> bytes:
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        run = 1
        while i + run < n and run < 128 and data[i + run] == data[i]:
            run += 1
        if run >= 3:
            out += bytes((257 - run, data[i]))
            i += run
            continue
        j = i
        while j < n and j - i < 128:
            if j + 2 < n and data[j] == data[j + 1] == data[j + 2]:
                break
            j += 1
        out.append(j - i - 1)
        out += data[i:j]
        i = j
    return bytes(out)


def unpackbits(data: bytes, size: int) -> bytes:
    out = bytearray()
    i = 0
    while len(out) < size and i < len(data):
        n = data[i]
        i += 1
        if n < 128:
            out += data[i:i + n + 1]
            i += n + 1
        elif n > 128:
            out += bytes((data[i],)) * (257 - n)
            i += 1
    if len(out) != size:
        raise Gen5Error("PackBits data has the wrong size")
    return bytes(out)


def tiles(indices: bytes, width: int, height: int, columns: int, rows: int) -> bytes:
    """One byte a pixel (indices 0-15) to columns x rows 4bpp GBA tiles."""
    out = bytearray(columns * rows * 32)
    for y in range(height):
        line = indices[y * width:(y + 1) * width]
        if line.count(0) == len(line):
            continue
        base = (y // 8) * columns * 32 + (y % 8) * 4
        for x in range(0, width, 2):
            low = line[x]
            high = line[x + 1] if x + 1 < width else 0
            if low or high:
                out[base + (x // 8) * 32 + (x % 8) // 2] = low | high << 4
    return bytes(out)


def convert(normal: bytes, shiny: bytes | None) -> bytes:
    """The G5A1 entry of an animation: its normal GIF and its shiny one (None: the shiny colours are the normal)."""
    width, height, colours, frames = read_gif(normal)
    palette, table = reduce_palette(colours, [frame for frame, _ in frames])
    indexed = [frame.translate(table) for frame, _ in frames]
    shiny_colours = palette
    if shiny is not None:
        shiny_colours = shiny_palette(palette, indexed, width, read_gif(shiny))
    columns, rows = (width + 7) // 8, (height + 7) // 8
    images: dict[bytes, int] = {}
    steps: list[list[int]] = []
    for picture, (_, delay) in zip(indexed, frames):
        ticks = max(1, round((delay if delay > 1 else 10) * 60 / 100))
        image = images.setdefault(picture, len(images))
        if steps and steps[-1][0] == image:
            steps[-1][1] = min(65535, steps[-1][1] + ticks)
        else:
            steps.append([image, ticks])
    if len(steps) > 1 and steps[0][0] == steps[-1][0]:
        steps[0][1] = min(65535, steps[0][1] + steps.pop()[1])
    if len(images) > MAX_IMAGES or len(steps) > MAX_STEPS:
        raise Gen5Error("animation too long: %d pictures, %d frames" % (len(images), len(steps)))
    first = indexed[0]
    xs = [i % width for i, p in enumerate(first) if p]
    ys = [i // width for i, p in enumerate(first) if p]
    anchor2, feet, top = (min(xs) + max(xs) + 1, max(ys), min(ys)) if xs else (width, height - 1, 0)
    blobs = [packbits(tiles(picture, width, height, columns, rows)) for picture in images]
    out = bytearray(MAGIC)
    out += struct.pack("<BBH", columns, rows, len(images))
    out += struct.pack("<16H", *(palette + [0] * 16)[:16])
    out += struct.pack("<16H", *(shiny_colours + [0] * 16)[:16])
    out += struct.pack("<4H", len(steps), anchor2, feet, top)
    out += b"".join(struct.pack("<HH", image, ticks) for image, ticks in steps)
    at = 0
    for blob in blobs:
        out += struct.pack("<I", at)
        at += len(blob)
    out += struct.pack("<I", at)
    out += b"".join(blobs)
    return bytes(out)


def source_path(row: tuple) -> str:
    key, variant, side = row[:3]
    dex, form = key & 511, key >> 9
    if dex == 201 and form:
        name = "201-" + gen5_sources.UNOWN_NAMES[form - 1]
    elif dex == 351 and form:
        name = "351-" + gen5_sources.CASTFORM_NAMES[form - 1]
    elif dex == 386:
        name = "386-attack"
    else:
        name = str(dex)
    parts = [gen5_sources.DIR] + (["back"] if side == "back" else []) + (["shiny"] if variant.endswith("shiny") else [])
    parts += ["female"] if variant.startswith("female") else []
    return "/".join(parts + [name + ".gif"])


def file_name(row: tuple) -> str:
    key, variant, side = row[:3]
    return "gen5_{}_{:03d}_{:02d}_{}.gif".format(side, key & 511, key >> 9, variant)


def entry_name(key: int, side: str, female: bool) -> str:
    dex, form = key & 511, key >> 9
    return "%s%03d%s%s.bin" % (FRONT_PREFIX if side == "front" else BACK_PREFIX, dex,
                               "_%02d" % form if form else "", "_f" if female else "")


def pack_files(rows: list[tuple], got: dict[tuple, bytes]) -> tuple[list[tuple[str, bytes]], dict]:
    """The entries of every picture whose normal GIF could be had (`got` is keyed by row[:3]), and a summary: the
    species with both sides, and those without."""
    files, failed = [], []
    for key, side, female in sorted({(row[0], row[2], row[1].startswith("female")) for row in rows}):
        prefix = "female_" if female else ""
        normal = got.get((key, prefix + "normal", side))
        if normal is None:
            continue
        try:
            files.append((entry_name(key, side, female), convert(normal, got.get((key, prefix + "shiny", side)))))
        except (Gen5Error, struct.error, IndexError) as exc:
            failed.append("%s: %s" % (entry_name(key, side, female), exc))
    names = {name for name, _ in files}
    dexes = {row[0] for row in rows if not row[0] >> 9}
    species = [dex for dex in dexes if entry_name(dex, "front", False) in names and entry_name(dex, "back", False) in names]
    missing = sorted(dexes - set(species))
    return files, {"species": len(species), "missing": missing, "failed": failed}
