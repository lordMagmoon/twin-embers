"""Black 2 / White 2 battle sprites (gen5_sprites.py) on synthetic GIFs: no network, no game picture."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from firered3ds_builder import gen4_sprites, gen5_sources, gen5_sprites  # noqa: E402


def lzw(indices: bytes) -> bytes:
    """Indices (0-15) as GIF LZW with code size 4: a clear code every 12 codes keeps every code 5 bits wide."""
    codes = []
    for i in range(0, len(indices), 12):
        codes.append(16)
        codes.extend(indices[i:i + 12])
    codes.append(17)
    value = bits = 0
    out = bytearray()
    for code in codes:
        value |= code << bits
        bits += 5
        while bits >= 8:
            out.append(value & 0xFF)
            value >>= 8
            bits -= 8
    if bits:
        out.append(value)
    blocks = bytearray()
    for i in range(0, len(out), 255):
        chunk = out[i:i + 255]
        blocks += bytes((len(chunk),)) + chunk
    return bytes(blocks) + b"\0"


def gif(width: int, height: int, colours: list[tuple[int, int, int]],
        frames: list[tuple[tuple[int, int, int, int], bytes, int, int]], transparent: int = 0) -> bytes:
    """A GIF89a: 16 global colours, each frame (left, top, w, h), its indices, its delay and disposal."""
    table = (colours + [(0, 0, 0)] * 16)[:16]
    out = bytearray(b"GIF89a" + struct.pack("<HHBBB", width, height, 0x80 | 3, 0, 0))
    out += b"".join(bytes(c) for c in table)
    for (left, top, w, h), indices, delay, disposal in frames:
        out += b"\x21\xF9\x04" + struct.pack("<BHB", disposal << 2 | 1, delay, transparent) + b"\0"
        out += b"\x2C" + struct.pack("<HHHHB", left, top, w, h, 0) + b"\x04" + lzw(indices)
    return bytes(out + b"\x3B")


RED, GREEN, BLUE, WHITE = (248, 0, 0), (0, 248, 0), (0, 0, 248), (248, 248, 248)
SHINY_RED, SHINY_GREEN = (248, 248, 0), (0, 248, 248)


def square(colour: int, size: int = 4) -> bytes:
    return bytes([colour]) * (size * size)


def animation(red: int = 1, green: int = 2, palette=(RED, GREEN, BLUE), offset: int = 0) -> bytes:
    """10x9: a 4x4 square that turns green for one frame, then red again (the first picture, so two pictures)."""
    whole = (offset, offset, 10, 9)
    first = bytearray(90)
    for y in range(3, 7):
        first[y * 10 + 3:y * 10 + 7] = bytes([red]) * 4
    second = bytearray(first)
    for y in range(3, 7):
        second[y * 10 + 3:y * 10 + 7] = bytes([green]) * 4
    return gif(10 + offset, 9 + offset, [(0, 0, 0)] + list(palette),
               [(whole, bytes(first), 10, 1), (whole, bytes(second), 5, 1), (whole, bytes(first), 10, 1)])


class GifTest(unittest.TestCase):
    def test_frames_follow_transparency_and_disposal(self):
        base = square(1)
        over = bytes([0, 2, 2, 0])          # a row of 4 with its ends transparent
        data = gif(4, 4, [(0, 0, 0), RED, GREEN],
                   [((0, 0, 4, 4), base, 10, 1), ((0, 1, 4, 1), over, 10, 2), ((0, 0, 1, 1), b"\x02", 3, 0)])
        width, height, colours, frames = gen5_sprites.read_gif(data)
        self.assertEqual((width, height, colours), (4, 4, [RED, GREEN]))
        self.assertEqual(frames[0], (bytes([1]) * 16, 10))
        self.assertEqual(frames[1][0][4:8], bytes([1, 2, 2, 1]))     # drawn over the first, its ends showing it
        # Disposal 2 cleared the row it drew: the third frame shows it transparent, under its own pixel.
        self.assertEqual(frames[2], (bytes([2, 1, 1, 1, 0, 0, 0, 0]) + bytes([1]) * 8, 3))

    def test_wrong_files_are_refused(self):
        with self.assertRaises(gen5_sprites.Gen5Error):
            gen5_sprites.read_gif(b"\x89PNG\r\n\x1a\n")
        with self.assertRaises(gen5_sprites.Gen5Error):
            gen5_sprites.read_gif(gif(200, 8, [RED], [((0, 0, 1, 1), b"\x01", 1, 0)]))


class ConvertTest(unittest.TestCase):
    def entry(self, data: bytes) -> dict:
        self.assertEqual(data[:4], gen5_sprites.MAGIC)
        columns, rows, images = struct.unpack_from("<BBH", data, 4)
        normal = struct.unpack_from("<16H", data, 8)
        shiny = struct.unpack_from("<16H", data, 40)
        steps, anchor2, feet, top = struct.unpack_from("<4H", data, 72)
        sequence = [struct.unpack_from("<HH", data, 80 + 4 * i) for i in range(steps)]
        at = 80 + 4 * steps
        offsets = struct.unpack_from("<%dI" % (images + 1), data, at)
        start = at + 4 * (images + 1)
        self.assertEqual(start + offsets[-1], len(data))
        pictures = [gen5_sprites.unpackbits(data[start + offsets[i]:start + offsets[i + 1]], columns * rows * 32)
                    for i in range(images)]
        return dict(columns=columns, rows=rows, normal=normal, shiny=shiny, sequence=sequence,
                    anchor2=anchor2, feet=feet, top=top, pictures=pictures)

    def test_an_animation_becomes_tiles_steps_and_two_palettes(self):
        got = self.entry(gen5_sprites.convert(animation(), animation(palette=(SHINY_RED, SHINY_GREEN, BLUE), offset=2)))
        self.assertEqual((got["columns"], got["rows"]), (2, 2))
        # Red is the most used colour: index 1; green 2. The shiny GIF, two pixels off on a larger canvas, gives their shiny ones.
        self.assertEqual(got["normal"][:3], (0, 31, 31 << 5))
        self.assertEqual(got["shiny"][:3], (0, 31 | 31 << 5, 31 << 5 | 31 << 10))
        # The last frame repeats the first picture: it joins the first step (10 + 10 hundredths, 12 ticks).
        self.assertEqual(got["sequence"], [(0, 12), (1, 3)])
        self.assertEqual((got["anchor2"], got["feet"], got["top"]), (10, 6, 3))
        # Pixel (3, 3) of the first picture is red: tile 0, row 3, byte 1, high nibble.
        self.assertEqual(got["pictures"][0][3 * 4 + 1] >> 4, 1)
        self.assertEqual(got["pictures"][1][3 * 4 + 1] >> 4, 2)

    def test_more_than_15_colours_are_folded(self):
        colours = [(i * 8, 0, 0) for i in range(1, 17)]                   # 16 shades of red, two pixels each
        indices = bytes(i % 16 for i in range(32))
        data = gif(8, 4, [(0, 0, 0)] + colours[:15], [((0, 0, 8, 4), indices, 10, 1)])
        # 15 colours fit: index 0 of the GIF is transparent, so these are 15 and a hole.
        got = self.entry(gen5_sprites.convert(data, None))
        self.assertEqual(got["shiny"], got["normal"])
        many = gif(8, 4, [(0, 0, 0)] + colours[:15], [((0, 0, 8, 4), indices, 10, 1)], transparent=255)
        got = self.entry(gen5_sprites.convert(many, None))
        self.assertLessEqual(len([c for c in got["normal"][1:] if c]), 15)

    def test_packbits_round_trip(self):
        for data in (b"", b"\0" * 300, bytes(range(200)), b"ab" * 70 + b"\0" * 5 + b"xyz"):
            self.assertEqual(gen5_sprites.unpackbits(gen5_sprites.packbits(data), len(data)), data)


class PackTest(unittest.TestCase):
    def test_listed_files_come_from_the_pinned_commit(self):
        rows = gen4_sprites.all_files((gen4_sprites.GROUP_BW2,))
        self.assertEqual(rows, gen5_sources.FILES)
        self.assertNotIn(327, {row[0] for row in rows})                  # Spinda keeps FireRed's
        row = next(row for row in rows if row[:3] == (201 | 26 << 9, "shiny", "back"))
        self.assertEqual(gen4_sprites.file_url(row),
                         f"https://raw.githubusercontent.com/PokeAPI/sprites/{gen5_sources.COMMIT}/"
                         f"{gen5_sources.DIR}/back/shiny/201-exclamation.gif")
        self.assertEqual(gen5_sprites.source_path((386, "female_normal", "front")),
                         f"{gen5_sources.DIR}/female/386-attack.gif")
        self.assertNotIn(gen4_sprites.GROUP_BW2, gen4_sprites.GROUPS)    # never with HeartGold's by default

    def test_entries_for_each_picture_that_could_be_had(self):
        normal, shiny = animation(), animation(palette=(SHINY_RED, SHINY_GREEN, BLUE))
        rows = []
        with tempfile.TemporaryDirectory() as folder:
            for key, variant, side, data in ((1, "normal", "front", normal), (1, "shiny", "front", shiny),
                                             (1, "normal", "back", normal), (1, "shiny", "back", shiny),
                                             (3, "female_normal", "front", normal),
                                             (3, "normal", "front", normal),
                                             (201 | 2 << 9, "normal", "front", normal)):
                import hashlib
                row = (key, variant, side, len(data), hashlib.sha256(data).hexdigest())
                rows.append(row)
                (Path(folder) / gen4_sprites.file_name(row)).write_bytes(data)
            rows.append((2, "normal", "front", 1, "0" * 64))                 # listed, never had
            from unittest.mock import patch
            with patch.object(gen5_sources, "FILES", tuple(rows)):
                files, info = gen4_sprites.pack_files(gen4_sprites.Downloader(None, Path(folder), get=None, threads=0),
                                                      groups=(gen4_sprites.GROUP_BW2,))
        names = sorted(name for name, _ in files)
        self.assertEqual(names, ["graphics/gen5/back/001.bin", "graphics/gen5/front/001.bin",
                                 "graphics/gen5/front/003.bin", "graphics/gen5/front/003_f.bin",
                                 "graphics/gen5/front/201_02.bin"])
        self.assertEqual(info["bw2"], {"species": 1, "missing": [2, 3], "failed": []})
        front = dict(files)["graphics/gen5/front/001.bin"]
        self.assertNotEqual(front[8:40], front[40:72])                       # its shiny colours came with it
        self.assertEqual(dict(files)["graphics/gen5/front/003.bin"][8:40], dict(files)["graphics/gen5/front/003.bin"][40:72])


if __name__ == "__main__":
    unittest.main()
