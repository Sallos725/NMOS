/* Spike diagnostic: how macOS libc classifies Hangul, Han and kana (glibc calls them alpha). */
#include <locale.h>
#include <stdio.h>
#include <wctype.h>

int main(void) {
    const char *locales[] = {"en_US.UTF-8", "ko_KR.UTF-8"};
    const struct { wchar_t c; const char *name; } chars[] = {
        {0xB4F1, "Hangul 등"}, {0xD55C, "Hangul 한"}, {0x6F22, "Han 漢"}, {0x304B, "Hiragana か"},
        {0x30AB, "Katakana カ"}, {0x00E9, "Latin é"}, {0x0041, "Latin A"}};
    for (int l = 0; l < 2; l++) {
        if (!setlocale(LC_CTYPE, locales[l])) { printf("%s: setlocale failed\n", locales[l]); continue; }
        for (unsigned i = 0; i < sizeof chars / sizeof chars[0]; i++) {
            wint_t c = chars[i].c;
            printf("%s %-14s alpha=%d alnum=%d ideogram=%d phonogram=%d\n", locales[l], chars[i].name,
                   iswalpha(c) != 0, iswalnum(c) != 0, iswideogram(c) != 0, iswphonogram(c) != 0);
        }
    }
    return 0;
}
