# Black 2 / White 2 animated battle sprites

Optional, the other choice of battle sprites in every Builder: FireRed's own, HeartGold's, or Generation V's animated
ones. With these, the Pokémon in battle and in the evolution scene move with Black and White's animations, the
pictures Black 2 and White 2 show for national dex 1-386: front, back, shiny, a female's own picture, Unown's letters
and Castform's weather forms. Outside battle (Summary, Pokédex, party, PC) the animation's first picture is shown.
Spinda keeps FireRed's picture: its spots follow each Spinda's personality, and an animation has one set of them.

Nothing of the art is in this repository, a release or CI: the Builder downloads the GIFs on the player's computer.

## Choosing them

- Desktop Builder: choose **Black 2 / White 2 animated Pokémon** in **Battle sprites** (the same row offers FireRed's own
  and HeartGold's, so the window keeps its height).
- Command line: `firered3ds-builder build --rom ROM --bw2-sprites` (it cannot be given with `--gen4-sprites`).
- Web Builder: the **Black 2 / White 2 animated Pokémon** switch.

The download is about 1,900 files, 68 MB, from [PokeAPI/sprites](https://github.com/PokeAPI/sprites) at the commit
pinned in `builder/firered3ds_builder/gen5_sources.py`, each file checked by size and SHA-256 as the HeartGold ones
are (`tools/make_gen5_sources.py` writes the list from a checkout). A file that does not match is not used, and its
species keeps FireRed's pictures. Converting takes a minute or two on a PC (a few minutes in the web Builder); the
pictures add about 23 MB to the pack.

## The pack entries

`graphics/gen5/front/NNN.bin` and `graphics/gen5/back/NNN.bin` (`NNN_FF` for Unown's letters and Castform's forms,
`_f` for a female's own picture), in the layout `gen5_sprites.py` describes: the animation's distinct images as 4bpp
tiles, PackBits-compressed, the order and length of its frames, and its normal and shiny palettes on the same colour
indices. The GIFs keep their animation's canvas (at most 160x160), so a picture is columns x rows tiles, not square.

The shiny palette comes from the shiny GIF: its frames are matched to the normal ones by shape (the shiny GIF can be
cropped a pixel or two otherwise, or have more or fewer frames) and each colour index takes the colour the shiny one
shows there. A picture with more than 15 colours (a few backs) has its rarest colours folded into their nearest ones.

## In the game

`3ds_battle_gen4.c` (`src/3ds_battle_gen5_impl.h`) reads a battler's entry when the game loads its picture (the
send-out, Transform, Castform's weather, the evolution scene), before the ball opens, never while a frame is drawn.
`CtrGen4_Load` takes Black 2 / White 2's entry first, then HeartGold's; the compositor draws it exactly as it draws
HeartGold's picture (the sprite's position, affine matrix, palette slot, blending and fades), the frame chosen by
`CtrGen4_Tick`, once a game frame. A front picture is 1:1 on the screen, as HeartGold's; a back one at the height of
FireRed's back picture, one or two screen pixels a picture pixel, never a scale in between that would draw
some picture pixels wider than others (Black and White show their backs larger).
The picture stands on FireRed's picture's feet and middle.

- The animation stands still while the Pokémon sleeps or is frozen, and stops as it faints (the rows FireRed erases
  are erased from the frame shown).
- Moves that copy the battler onto a background (`CopyBattlerSpriteToBg`) get the frame shown, at the battle's scale.
- A battler is drawn only while its sprite is still the one made from its position's template (recipe 0262), so a
  sprite id that another screen reuses (the nickname screen after a catch, the screens after the evolution scene) is
  never taken for it. The evolution scene's two sprites are checked the same way.
- Outside battle, the first picture is kept with the path it was read from: the palette asked for next is that
  picture's (a female's own has its own colour order), and the same picture is not read twice.

## Limits

- The Summary, Pokédex and PC show the first picture, not the animation.
- Large Pokémon (Wailord, Kyogre, Groudon, Rayquaza) go past FireRed's 64x64 box, as in Black and White.
- Spinda keeps FireRed's picture (above).
