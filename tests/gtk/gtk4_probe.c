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

static GdkTexture *render(GtkIconPaintable *paintable, const GdkRGBA *tint, int size)
{
    GtkSnapshot *snapshot = gtk_snapshot_new();
    if (tint) {
        GdkRGBA colors[4] = {*tint, *tint, *tint, *tint};
        gtk_symbolic_paintable_snapshot_symbolic(GTK_SYMBOLIC_PAINTABLE(paintable), snapshot, size, size, colors, 4);
    } else {
        gdk_paintable_snapshot(GDK_PAINTABLE(paintable), snapshot, size, size);
    }
    GskRenderNode *node = gtk_snapshot_free_to_node(snapshot);
    if (!node)
        return NULL;
    G_GNUC_BEGIN_IGNORE_DEPRECATIONS
    GskRenderer *renderer = gsk_cairo_renderer_new();
    G_GNUC_END_IGNORE_DEPRECATIONS
    GdkTexture *texture = NULL;
    if (gsk_renderer_realize_for_display(renderer, gdk_display_get_default(), NULL)) {
        graphene_rect_t bounds = GRAPHENE_RECT_INIT(0, 0, size, size);
        texture = gsk_renderer_render_texture(renderer, node, &bounds);
    }
    gsk_render_node_unref(node);
    gsk_renderer_unrealize(renderer);
    g_object_unref(renderer);
    return texture;
}

static void measure(GdkTexture *texture, const GdkRGBA *target, int tolerance, int *opaque, int *near)
{
    int w = gdk_texture_get_width(texture);
    int h = gdk_texture_get_height(texture);
    GdkTextureDownloader *downloader = gdk_texture_downloader_new(texture);
    gdk_texture_downloader_set_format(downloader, GDK_MEMORY_R8G8B8A8);
    gsize stride = 0;
    GBytes *bytes = gdk_texture_downloader_download_bytes(downloader, &stride);
    const guchar *data = g_bytes_get_data(bytes, NULL);
    *opaque = 0;
    *near = 0;
    for (int y = 0; y < h; y++) {
        for (int x = 0; x < w; x++) {
            const guchar *p = data + y * stride + x * 4;
            if (p[3] < 250)
                continue;
            (*opaque)++;
            if (abs(p[0] - (int)(target->red * 255)) <= tolerance && abs(p[1] - (int)(target->green * 255)) <= tolerance
                && abs(p[2] - (int)(target->blue * 255)) <= tolerance)
                (*near)++;
        }
    }
    g_bytes_unref(bytes);
    gdk_texture_downloader_free(downloader);
}

int main(int argc, char **argv)
{
    if (argc < 2 || !gtk_init_check()) {
        printf("BLOCKED\tsetup\tno display or no theme root\n");
        return 2;
    }
    const char *paths[] = {argv[1], NULL};
    GtkIconTheme *theme = gtk_icon_theme_new();
    gtk_icon_theme_set_search_path(theme, paths);
    gtk_icon_theme_set_theme_name(theme, "Resina");

    const char *owned[][2] = {
        {"folder", "/Resina/scalable/places-medium/folder.svg"},
        {"application-pdf", "/Resina/scalable/mimetypes/application-pdf.svg"},
        {"go-next-symbolic", "/Resina/symbolic/actions/go-next-symbolic.svg"},
        {"inode-directory", "/Resina/scalable/places-medium/inode-directory.svg"},
        {"network-wireless-symbolic", "/Resina/symbolic/devices/network-wireless-symbolic.svg"},
    };
    for (guint i = 0; i < G_N_ELEMENTS(owned); i++) {
        GtkIconPaintable *p = gtk_icon_theme_lookup_icon(theme, owned[i][0], NULL, 48, 1, GTK_TEXT_DIR_NONE, 0);
        GFile *file = gtk_icon_paintable_get_file(p);
        char *path = file ? g_file_get_path(file) : NULL;
        gboolean ok = path && g_str_has_suffix(path, owned[i][1]);
        char *problem = ok ? manifest_problem(argv[1], path) : NULL;
        report(ok && !problem, owned[i][0], !ok ? "not resolved to the expected theme file" : problem ? problem : path);
        g_free(problem);
        g_free(path);
        if (file)
            g_object_unref(file);
        g_object_unref(p);
    }

    report(!gtk_icon_theme_has_icon(theme, "resina-nonexistent-icon"), "resina-nonexistent-icon", "has_icon is false");

    int opaque = 0, near = 0;
    GtkIconPaintable *folder = gtk_icon_theme_lookup_icon(theme, "folder", NULL, 64, 1, GTK_TEXT_DIR_NONE, 0);
    GdkTexture *colour = render(folder, NULL, 64);
    GdkRGBA face;
    gdk_rgba_parse(&face, "#f5b33b");
    if (colour)
        measure(colour, &face, 24, &opaque, &near);
    report(colour && near > 300, "colour-preserved", g_strdup_printf("face-coloured pixels %d of %d", near, opaque));

    GtkIconPaintable *arrow = gtk_icon_theme_lookup_icon(theme, "go-next-symbolic", NULL, 48, 1, GTK_TEXT_DIR_NONE, 0);
    report(gtk_icon_paintable_is_symbolic(arrow), "symbolic-detected", "is_symbolic");

    GtkIconPaintable *plain_name = gtk_icon_theme_lookup_icon(theme, "go-next", NULL, 48, 1, GTK_TEXT_DIR_NONE, 0);
    GFile *plain_file = gtk_icon_paintable_get_file(plain_name);
    char *plain_path = plain_file ? g_file_get_path(plain_file) : NULL;
    report(plain_path && g_str_has_suffix(plain_path, "/Resina/symbolic/actions/go-next.svg") && !gtk_icon_paintable_is_symbolic(plain_name),
           "plain-name-reaches-the-symbolic-file-unrecoloured", plain_path ? plain_path : "not resolved");

    GtkIconPaintable *arrow_rtl = gtk_icon_theme_lookup_icon(theme, "go-next-symbolic", NULL, 48, 1, GTK_TEXT_DIR_RTL, 0);
    GFile *rtl_file = gtk_icon_paintable_get_file(arrow_rtl);
    char *rtl_path = rtl_file ? g_file_get_path(rtl_file) : NULL;
    report(rtl_path && g_str_has_suffix(rtl_path, "/Resina/symbolic/actions/go-next-symbolic-rtl.svg") && gtk_icon_paintable_is_symbolic(arrow_rtl),
           "right-to-left-variant-is-chosen", rtl_path ? rtl_path : "not resolved");

    const char *tints[] = {"#c62828", "#ffffff"};
    for (guint i = 0; i < G_N_ELEMENTS(tints); i++) {
        GdkRGBA fg;
        gdk_rgba_parse(&fg, tints[i]);
        GdkTexture *tinted = render(arrow, &fg, 48);
        if (tinted)
            measure(tinted, &fg, 40, &opaque, &near);
        double share = tinted && opaque ? (double)near / opaque : 0.0;
        report(tinted && share >= 0.9, g_strdup_printf("symbolic-recolour %s", tints[i]),
               g_strdup_printf("opaque %d, in foreground colour %.2f", opaque, share));
    }

    GdkRGBA red;
    gdk_rgba_parse(&red, "#c62828");
    GdkTexture *untinted = render(arrow, NULL, 48);
    opaque = near = 0;
    if (untinted)
        measure(untinted, &red, 40, &opaque, &near);
    report(untinted && opaque > 0 && near == 0, "untinted-control", g_strdup_printf("untinted symbolic icon: opaque %d, foreground-coloured %d", opaque, near));

    printf("SUMMARY\t%d\n", failures);
    return failures ? 1 : 0;
}
