/* SPDX-License-Identifier: EUPL-1.2 */
#include <gtk/gtk.h>
#include "manifest.h"
#include <stdio.h>
#include <string.h>

static int failures;

static void report(gboolean ok, const char *name, const char *detail)
{
    printf("%s\t%s\t%s\n", ok ? "PASS" : "FAIL", name, detail);
    if (!ok)
        failures++;
}

static void measure(GdkPixbuf *pixbuf, const GdkRGBA *target, int tolerance, int *opaque, int *near)
{
    int w = gdk_pixbuf_get_width(pixbuf);
    int h = gdk_pixbuf_get_height(pixbuf);
    int stride = gdk_pixbuf_get_rowstride(pixbuf);
    int channels = gdk_pixbuf_get_n_channels(pixbuf);
    const guchar *data = gdk_pixbuf_read_pixels(pixbuf);
    *opaque = 0;
    *near = 0;
    for (int y = 0; y < h; y++) {
        for (int x = 0; x < w; x++) {
            const guchar *p = data + y * stride + x * channels;
            if (channels == 4 && p[3] < 250)
                continue;
            (*opaque)++;
            if (abs(p[0] - (int)(target->red * 255)) <= tolerance && abs(p[1] - (int)(target->green * 255)) <= tolerance
                && abs(p[2] - (int)(target->blue * 255)) <= tolerance)
                (*near)++;
        }
    }
}

int main(int argc, char **argv)
{
    if (argc < 2 || !gtk_init_check(&argc, &argv)) {
        printf("BLOCKED\tsetup\tno display or no theme root\n");
        return 2;
    }
    const gchar *paths[] = {argv[1]};
    GtkIconTheme *theme = gtk_icon_theme_new();
    gtk_icon_theme_set_search_path(theme, paths, 1);
    gtk_icon_theme_set_custom_theme(theme, "Resina");

    const char *owned[][2] = {
        {"folder", "/Resina/scalable/places-medium/folder.svg"},
        {"application-pdf", "/Resina/scalable/mimetypes/application-pdf.svg"},
        {"go-next-symbolic", "/Resina/symbolic/actions/go-next-symbolic.svg"},
        {"inode-directory", "/Resina/scalable/places-medium/inode-directory.svg"},
        {"network-wireless-symbolic", "/Resina/symbolic/devices/network-wireless-symbolic.svg"},
    };
    for (guint i = 0; i < G_N_ELEMENTS(owned); i++) {
        GtkIconInfo *info = gtk_icon_theme_lookup_icon(theme, owned[i][0], 48, 0);
        const char *file = info ? gtk_icon_info_get_filename(info) : NULL;
        gboolean ok = file && g_str_has_suffix(file, owned[i][1]);
        char *problem = ok ? manifest_problem(argv[1], file) : NULL;
        report(ok && !problem, owned[i][0], !ok ? "not resolved to the expected theme file" : problem ? problem : file);
        g_free(problem);
        if (info)
            g_object_unref(info);
    }

    GtkIconInfo *missing = gtk_icon_theme_lookup_icon(theme, "resina-nonexistent-icon", 48, 0);
    report(missing == NULL, "resina-nonexistent-icon", missing ? "unexpectedly resolved" : "no icon");

    GtkIconInfo *folder = gtk_icon_theme_lookup_icon(theme, "folder", 64, GTK_ICON_LOOKUP_FORCE_SIZE);
    GdkPixbuf *colour = folder ? gtk_icon_info_load_icon(folder, NULL) : NULL;
    GdkRGBA face;
    gdk_rgba_parse(&face, "#f5b33b");
    int opaque = 0, near = 0;
    if (colour)
        measure(colour, &face, 24, &opaque, &near);
    report(colour && near > 300, "colour-preserved", g_strdup_printf("face-coloured pixels %d of %d", near, opaque));

    GtkIconInfo *arrow = gtk_icon_theme_lookup_icon(theme, "go-next-symbolic", 48, GTK_ICON_LOOKUP_FORCE_SIZE);
    report(arrow && gtk_icon_info_is_symbolic(arrow), "symbolic-detected", "is_symbolic");

    GtkIconInfo *plain_name = gtk_icon_theme_lookup_icon(theme, "go-next", 48, GTK_ICON_LOOKUP_FORCE_SIZE);
    const char *plain_file = plain_name ? gtk_icon_info_get_filename(plain_name) : NULL;
    report(plain_file && g_str_has_suffix(plain_file, "/Resina/symbolic/actions/go-next.svg") && !gtk_icon_info_is_symbolic(plain_name),
           "plain-name-reaches-the-symbolic-file-unrecoloured", plain_file ? plain_file : "not resolved");

    GtkIconInfo *arrow_rtl = gtk_icon_theme_lookup_icon(theme, "go-next-symbolic", 48, GTK_ICON_LOOKUP_FORCE_SIZE | GTK_ICON_LOOKUP_DIR_RTL);
    const char *rtl_file = arrow_rtl ? gtk_icon_info_get_filename(arrow_rtl) : NULL;
    report(rtl_file && g_str_has_suffix(rtl_file, "/Resina/symbolic/actions/go-next-symbolic-rtl.svg") && gtk_icon_info_is_symbolic(arrow_rtl),
           "right-to-left-variant-is-chosen", rtl_file ? rtl_file : "not resolved");

    const char *tints[] = {"#c62828", "#ffffff"};
    for (guint i = 0; i < G_N_ELEMENTS(tints); i++) {
        GdkRGBA fg;
        gdk_rgba_parse(&fg, tints[i]);
        gboolean was_symbolic = FALSE;
        GdkPixbuf *tinted = arrow ? gtk_icon_info_load_symbolic(arrow, &fg, NULL, NULL, NULL, &was_symbolic, NULL) : NULL;
        opaque = near = 0;
        if (tinted)
            measure(tinted, &fg, 40, &opaque, &near);
        double share = opaque ? (double)near / opaque : 0.0;
        report(tinted && was_symbolic && share >= 0.9, g_strdup_printf("symbolic-recolour %s", tints[i]),
               g_strdup_printf("opaque %d, in foreground colour %.2f", opaque, share));
    }

    GdkPixbuf *plain = arrow ? gtk_icon_info_load_icon(arrow, NULL) : NULL;
    GdkRGBA red;
    gdk_rgba_parse(&red, "#c62828");
    opaque = near = 0;
    if (plain)
        measure(plain, &red, 40, &opaque, &near);
    report(plain && opaque > 0 && near == 0, "untinted-control", g_strdup_printf("untinted symbolic icon: opaque %d, foreground-coloured %d", opaque, near));

    printf("SUMMARY\t%d\n", failures);
    return failures ? 1 : 0;
}
