/* Black 2 / White 2's animated battle pictures, part of 3ds_battle_gen4.c (see include/3ds_battle_gen4.h).
 *
 * graphics/gen5/front|back/NNN[_FF][_f].bin (builder/firered3ds_builder/gen5_sprites.py): a picture's distinct images as
 * 4bpp tiles, PackBits-compressed, its steps (which image, for how many 60ths of a second) and its normal and shiny
 * palettes, with the same colour indices. A battler's entry is read and unpacked when the game loads its picture (the
 * send-out, Transform, Castform's weather, the evolution scene), never while a frame is drawn; the compositor then
 * draws the step's image wherever it would draw HeartGold's picture. */

#define GEN5_HEADER 80
#define GEN5_IMAGES_MAX 255u
#define GEN5_STEPS_MAX 1024u
#define GEN5_TILE 32u

typedef struct {
    uint16_t image, ticks;
} Gen5Step;

typedef struct {
    bool active, erased;
    unsigned columns, rows, images, steps, step, left;
    unsigned anchorX2, feet, top;
    float pivotX, pivotY, scale;
    uint8_t *tiles;                 /* images x columns x rows tiles */
    uint8_t *shown;                 /* the image as a fainting battler shows it, rows erased (CtrGen4_EraseFrom) */
    Gen5Step *sequence;
    uint16_t palette[2][16];        /* normal, shiny */
} Anim;

static Anim sAnims[BATTLERS];

static unsigned U16(const uint8_t *p)
{
    return (unsigned)p[0] | (unsigned)p[1] << 8;
}

static uint32_t U32(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static void AnimFree(Anim *anim)
{
    free(anim->tiles);
    free(anim->shown);
    free(anim->sequence);
    *anim = (Anim){0};
}

/* A key's entry: national dex 1-386, Unown's letters (201, form 1-27) and Castform's weather (351, form 1-3) with their
 * own, a female's own picture when it has one. False when the pack has none. */
static bool Gen5Path(unsigned key, bool back, bool female, char *path, size_t size)
{
    unsigned dex = key & 511, form = key >> 9;
    uint32_t bytes;
    char formPart[4] = "";

    if (dex < 1 || dex > 386 || (form && !(dex == 201 && form <= 27) && !(dex == 351 && form <= 3)))
        return false;
    if (form)
        snprintf(formPart, sizeof(formPart), "_%02u", form);
    if (female)
    {
        snprintf(path, size, "graphics/gen5/%s/%03u%s_f.bin", back ? "back" : "front", dex, formPart);
        if (CtrData_Size(path, &bytes))
            return true;
    }
    snprintf(path, size, "graphics/gen5/%s/%03u%s.bin", back ? "back" : "front", dex, formPart);
    return CtrData_Size(path, &bytes);
}

/* PackBits into exactly `size` bytes. */
static bool Unpack(const uint8_t *in, uint32_t length, uint8_t *out, uint32_t size)
{
    uint32_t i = 0, at = 0;

    while (at < size && i < length)
    {
        unsigned n = in[i++];
        if (n < 128)
        {
            if (i + n + 1 > length || at + n + 1 > size)
                return false;
            memcpy(out + at, in + i, n + 1);
            i += n + 1;
            at += n + 1;
        }
        else if (n > 128)
        {
            if (i >= length || at + 257 - n > size)
                return false;
            memset(out + at, in[i++], 257 - n);
            at += 257 - n;
        }
    }
    return at == size;
}

/* An entry read whole into `anim` (its images unpacked): false, `anim` empty, for one that is not a G5A1 entry with every
 * size in range. */
static bool AnimRead(Anim *anim, const char *path)
{
    uint32_t size = 0;
    uint8_t *entry = CtrData_Load(path, &size);
    bool ok = false;

    *anim = (Anim){0};
    if (!entry)
        return false;
    if (size >= GEN5_HEADER && !memcmp(entry, "G5A1", 4))
    {
        unsigned columns = entry[4], rows = entry[5], images = U16(entry + 6), steps = U16(entry + 72);
        uint32_t table = GEN5_HEADER + steps * 4u, start = table + (images + 1) * 4u;
        uint32_t imageBytes = columns * rows * GEN5_TILE;

        ok = columns && rows && columns <= CTR_GEN5_TILES_MAX && rows <= CTR_GEN5_TILES_MAX && images
          && images <= GEN5_IMAGES_MAX && steps && steps <= GEN5_STEPS_MAX && start <= size
          && start + U32(entry + start - 4) == size;
        if (ok)
        {
            anim->tiles = malloc(images * imageBytes);
            anim->sequence = malloc(steps * sizeof(*anim->sequence));
            ok = anim->tiles && anim->sequence;
        }
        for (unsigned i = 0; ok && i < steps; ++i)
        {
            anim->sequence[i].image = (uint16_t)U16(entry + GEN5_HEADER + i * 4);
            anim->sequence[i].ticks = (uint16_t)U16(entry + GEN5_HEADER + i * 4 + 2);
            ok = anim->sequence[i].image < images && anim->sequence[i].ticks;
        }
        for (unsigned i = 0; ok && i < images; ++i)
        {
            uint32_t from = U32(entry + table + i * 4), to = U32(entry + table + i * 4 + 4);
            ok = from <= to && start + to <= size
              && Unpack(entry + start + from, to - from, anim->tiles + i * imageBytes, imageBytes);
        }
        if (ok)
        {
            anim->columns = columns;
            anim->rows = rows;
            anim->images = images;
            anim->steps = steps;
            anim->anchorX2 = U16(entry + 74);
            anim->feet = U16(entry + 76);
            anim->top = U16(entry + 78);
            for (unsigned i = 0; i < 16; ++i)
            {
                anim->palette[0][i] = (uint16_t)U16(entry + 8 + i * 2);
                anim->palette[1][i] = (uint16_t)U16(entry + 40 + i * 2);
            }
            anim->left = anim->sequence[0].ticks;
        }
    }
    if (!ok)
    {
        CtrLog_Write(CTR_LOG_GAME, "GEN5 %s: wrong size or kind", path);
        AnimFree(anim);
    }
    free(entry);
    return ok;
}

/* The highest and lowest rows and the middle (twice its x) of a 64x64 FireRed picture's pixels; false if it has none. */
static bool FireBox(const uint8_t *pic, int *top, int *bottom, int *centreX2)
{
    int left = 64, right = -1;

    *top = 64;
    *bottom = -1;
    for (int y = 0; y < 64; ++y)
        for (int x = 0; x < 64; ++x)
        {
            uint8_t pair = pic[((y / 8) * 8 + x / 8) * 32 + (y % 8) * 4 + (x % 8) / 2];
            if (!((x & 1) ? pair >> 4 : pair & 15))
                continue;
            if (y < *top) *top = y;
            if (y > *bottom) *bottom = y;
            if (x < left) left = x;
            if (x > right) right = x;
        }
    *centreX2 = left + right + 1;
    return *bottom >= 0;
}

/* Standing where FireRed's picture stood: the first image's lowest row on FireRed's lowest, its middle on FireRed's
 * middle. A back is as tall as FireRed's back, between one and two screen pixels a picture pixel. */
static void AnimPlace(Anim *anim, const void *firePic, bool back)
{
    int top, bottom, centreX2;
    bool fire = firePic && FireBox(firePic, &top, &bottom, &centreX2);

    anim->scale = CTR_GEN4_SCALE;
    if (back && fire && anim->feet >= anim->top)
    {
        float k = (float)(bottom - top + 1) / (float)(anim->feet - anim->top + 1);
        anim->scale = k < CTR_GEN4_SCALE ? CTR_GEN4_SCALE : k > 2 * CTR_GEN4_SCALE ? 2 * CTR_GEN4_SCALE : k;
    }
    if (!fire)
    {
        bottom = 56;
        centreX2 = 64;
    }
    anim->pivotX = anim->anchorX2 / 2.0f - (centreX2 / 2.0f - 32) / anim->scale;
    anim->pivotY = (anim->feet + 1) - (bottom + 1 - 32) / anim->scale;
}

static bool Gen5Load(unsigned battler, unsigned key, bool back, bool female, bool shiny, const void *firePic,
                     uint16_t palette[16])
{
    char path[48];
    Anim *anim = &sAnims[battler];

    AnimFree(anim);
    if (!Gen5Path(key, back, female, path, sizeof(path)) || !AnimRead(anim, path))
        return false;
    AnimPlace(anim, firePic, back);
    memcpy(palette, anim->palette[shiny ? 1 : 0], 32);
    anim->active = true;
    return true;
}

static const uint8_t *AnimImage(const Anim *anim)
{
    if (anim->erased)
        return anim->shown;
    return anim->tiles + anim->sequence[anim->step].image * anim->columns * anim->rows * GEN5_TILE;
}

static bool AnimMatch(unsigned battler, CtrGen4Obj *out)
{
    const Anim *anim = &sAnims[battler];

    out->slot = battler;
    out->tiles = AnimImage(anim);
    out->side = anim->columns;
    out->rows = anim->rows;
    out->pivotX = anim->pivotX;
    out->pivotY = anim->pivotY;
    out->scale = anim->scale;
    return true;
}

__attribute__((weak)) bool CtrGen4_Paused(unsigned battler)
{
    (void)battler;
    return false;
}

void CtrGen4_Tick(void)
{
    for (unsigned b = 0; b < BATTLERS; ++b)
    {
        Anim *anim = &sAnims[b];
        if (!anim->active || anim->erased || anim->steps < 2 || CtrGen4_Paused(b))
            continue;
        if (anim->left > 1)
        {
            --anim->left;
            continue;
        }
        anim->step = (anim->step + 1) % anim->steps;
        anim->left = anim->sequence[anim->step].ticks;
    }
}

/* The picture's pixel at (x, y), or 0 outside it. */
static unsigned AnimPixel(const Anim *anim, const uint8_t *tiles, int x, int y)
{
    if (x < 0 || y < 0 || x >= (int)anim->columns * 8 || y >= (int)anim->rows * 8)
        return 0;
    uint8_t pair = tiles[((unsigned)y / 8 * anim->columns + (unsigned)x / 8) * GEN5_TILE + (unsigned)y % 8 * 4
                         + (unsigned)x % 8 / 2];
    return (x & 1) ? pair >> 4 : pair & 15;
}

static bool AnimGbaPicture(unsigned battler, uint8_t out[0x800])
{
    const Anim *anim = &sAnims[battler];
    const uint8_t *tiles = AnimImage(anim);

    memset(out, 0, 0x800);
    for (int by = 0; by < 64; ++by)
        for (int bx = 0; bx < 64; ++bx)
        {
            float px = anim->pivotX + (bx + 0.5f - 32) / anim->scale, py = anim->pivotY + (by + 0.5f - 32) / anim->scale;
            if (px < 0 || py < 0)
                continue;
            unsigned index = AnimPixel(anim, tiles, (int)px, (int)py);
            out[((by / 8) * 8 + bx / 8) * 32 + (by % 8) * 4 + (bx % 8) / 2] |= (uint8_t)(index << ((bx & 1) * 4));
        }
    return true;
}

static void AnimEraseFrom(unsigned battler, unsigned boxRow)
{
    Anim *anim = &sAnims[battler];
    unsigned bytes = anim->columns * anim->rows * GEN5_TILE;

    if (!anim->erased)
    {
        uint8_t *shown = malloc(bytes);
        if (!shown)
            return;
        memcpy(shown, AnimImage(anim), bytes);
        free(anim->shown);
        anim->shown = shown;
        anim->erased = true;    /* the animation stops as the Pokemon sinks */
    }
    float row = anim->pivotY + ((float)boxRow - 32) / anim->scale;
    unsigned from = row < 0 ? 0 : (unsigned)(row + 0.5f);
    for (unsigned y = from; y < anim->rows * 8; ++y)
        for (unsigned tx = 0; tx < anim->columns; ++tx)
            memset(anim->shown + ((y / 8 * anim->columns + tx) * 8 + y % 8) * 4, 0, 4);
}

/* Outside battle: a species' first image, whole, in an 80x80 picture (rows of 40 bytes), its box's middle on the
 * picture's and its lowest row at the bottom; one larger than 80 shrunk to fit. Read once for a key, side and body, and
 * kept with its path, so asking for its palette next (CtrGen4_Palette) gives that picture's colours. */
static struct {
    char path[48];
    unsigned key;
    uint8_t linear[CTR_GEN4_PICTURE];
    uint16_t palette[2][16];
} sStill;

static bool Gen5Still(unsigned key, bool back, bool female)
{
    char path[48];
    Anim anim;

    if (!Gen5Path(key, back, female, path, sizeof(path)))
        return false;
    if (!strcmp(path, sStill.path))
        return true;
    sStill.path[0] = 0;
    if (!AnimRead(&anim, path))
        return false;
    const uint8_t *tiles = anim.tiles + anim.sequence[0].image * anim.columns * anim.rows * GEN5_TILE;
    int width = (int)anim.columns * 8, height = (int)anim.rows * 8;
    int boxH = (int)anim.feet - (int)anim.top + 1;
    float k = 1.0f;                                     /* picture pixels per still pixel */
    if (width > CTR_GEN4_SIZE || boxH > CTR_GEN4_SIZE)
        k = (float)(width > boxH ? width : boxH) / CTR_GEN4_SIZE;
    memset(sStill.linear, 0, sizeof(sStill.linear));
    for (int y = 0; y < CTR_GEN4_SIZE; ++y)
        for (int x = 0; x < CTR_GEN4_SIZE; ++x)
        {
            int sx = (int)(anim.anchorX2 / 2.0f + (x + 0.5f - CTR_GEN4_SIZE / 2.0f) * k);
            int sy = (int)(anim.feet + 1 + (y + 0.5f - CTR_GEN4_SIZE) * k);
            unsigned index = sx < width && sy < height ? AnimPixel(&anim, tiles, sx, sy) : 0;
            sStill.linear[y * (CTR_GEN4_SIZE / 2) + x / 2] |= (uint8_t)(index << ((x & 1) * 4));
        }
    memcpy(sStill.palette, anim.palette, sizeof(sStill.palette));
    sStill.key = key;
    snprintf(sStill.path, sizeof(sStill.path), "%s", path);
    AnimFree(&anim);
    return true;
}
