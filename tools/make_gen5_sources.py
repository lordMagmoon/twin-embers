"""Writes builder/firered3ds_builder/gen5_sources.py: the Black 2 / White 2 battle sprites the Builder may fetch.

    python tools/make_gen5_sources.py --checkout PATH_TO_POKEAPI_SPRITES

PATH_TO_POKEAPI_SPRITES is a checkout of PokeAPI/sprites (a sparse one of
sprites/pokemon/versions/generation-v/black-white/animated is enough). The
commit it is at is pinned, and every file the Builder may fetch is listed with
its size and SHA-256, so a changed or replaced file upstream is refused, never
converted. Nothing from the checkout is copied into this repository: only
paths, sizes and hashes.

The files are the animated GIFs of Generation V's battle sprites. Black 2 and
White 2 kept Black and White's Pokemon sprites for national dex 1-386, so
these are the pictures both pairs of games show.

For national dex 1-386, each side (front, back) in its normal and shiny
colours, and the female's own where the species has one. Unown's letters B to
? (FireRed's order: 1-25 B to Z, 26 !, 27 ?), its A being the species' own;
Castform's weather forms (1 sun, 2 rain, 3 ice); 386 is Deoxys' Attack Forme,
FireRed's and LeafGreen's, not the Normal Forme of 386.gif. Spinda (327) is left
out: its spots follow each Spinda's personality, a GIF has one set of them.
"""

import argparse
import hashlib
import subprocess
from pathlib import Path

REPO = 'PokeAPI/sprites'
DIR = 'sprites/pokemon/versions/generation-v/black-white/animated'
SPECIES = 386
UNOWN = 201
UNOWN_NAMES = [chr(ord('b') + i) for i in range(25)] + ['exclamation', 'question']
CASTFORM = 351
CASTFORM_NAMES = ['sunny', 'rainy', 'snowy']
DEOXYS = 386
SPINDA = 327    # its spots follow each Spinda's personality, which a GIF cannot: FireRed's picture keeps them
OUT = Path(__file__).resolve().parents[1] / 'builder' / 'firered3ds_builder' / 'gen5_sources.py'


def name(dex: int, form: int) -> str:
    if dex == UNOWN and form:
        return '201-' + UNOWN_NAMES[form - 1]
    if dex == CASTFORM and form:
        return '351-' + CASTFORM_NAMES[form - 1]
    if dex == DEOXYS:
        return '386-attack'
    return str(dex)


def path(dex: int, form: int, side: str, shiny: bool, female: bool) -> str:
    parts = [DIR] + (['back'] if side == 'back' else []) + (['shiny'] if shiny else []) + (['female'] if female else [])
    return '/'.join(parts + [name(dex, form) + '.gif'])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkout', type=Path, required=True)
    args = parser.parse_args()
    root = args.checkout
    commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    keys = [(dex, 0) for dex in range(1, SPECIES + 1) if dex != SPINDA]
    keys += [(UNOWN, form) for form in range(1, len(UNOWN_NAMES) + 1)]
    keys += [(CASTFORM, form) for form in range(1, len(CASTFORM_NAMES) + 1)]
    rows = []
    for dex, form in keys:
        for female in (False, True):
            for side in ('front', 'back'):
                for shiny in (False, True):
                    file = root / path(dex, form, side, shiny, female)
                    if not file.is_file():
                        if not female:
                            raise SystemExit('missing ' + str(file))
                        continue
                    data = file.read_bytes()
                    variant = ('female_' if female else '') + ('shiny' if shiny else 'normal')
                    rows.append((dex | form << 9, variant, side, len(data), hashlib.sha256(data).hexdigest()))
    lines = ['"""Black 2 / White 2 battle sprites the Builder may fetch (tools/make_gen5_sources.py; do not edit).',
             '',
             'A row: (key, variant, side, size, SHA-256). The key is the port\'s: national dex | form << 9 (Unown\'s',
             'letters 1-27 B to ?, Castform\'s weather 1-3 sun, rain, ice); variant "normal", "shiny", "female_normal" or',
             '"female_shiny"; side "front" or "back". Its path in the pinned commit is gen5_sprites.source_path(row)."""',
             '',
             f'REPO = {REPO!r}',
             f'COMMIT = {commit!r}',
             f'DIR = {DIR!r}',
             f'UNOWN_NAMES = {tuple(UNOWN_NAMES)!r}',
             f'CASTFORM_NAMES = {tuple(CASTFORM_NAMES)!r}',
             'FILES = (']
    lines += [f'    {row!r},' for row in rows]
    lines += [')', '']
    OUT.write_text('\n'.join(lines), encoding='utf-8')
    print(f'{len(rows)} files at {commit} -> {OUT}')


if __name__ == '__main__':
    main()
