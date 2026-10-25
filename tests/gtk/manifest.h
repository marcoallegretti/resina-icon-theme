/* SPDX-License-Identifier: EUPL-1.2 */
#ifndef RESINA_PROBE_MANIFEST_H
#define RESINA_PROBE_MANIFEST_H

#include <glib.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>

static gboolean manifest_digest_for(const char *theme_dir, const char *rel, char **digest, gboolean *listed_as_link)
{
    static const char *names[] = {"MANIFEST.core", "MANIFEST.thirdparty"};
    *digest = NULL;
    *listed_as_link = FALSE;
    for (guint i = 0; i < G_N_ELEMENTS(names); i++) {
        char *path = g_build_filename(theme_dir, names[i], NULL);
        char *text = NULL;
        gboolean read = g_file_get_contents(path, &text, NULL, NULL);
        g_free(path);
        if (!read)
            continue;
        char **lines = g_strsplit(text, "\n", -1);
        g_free(text);
        for (char **line = lines; *line; line++) {
            if (g_str_has_prefix(*line, "L ")) {
                char **parts = g_strsplit(*line, " ", 3);
                if (g_strv_length(parts) == 3 && strcmp(parts[1], rel) == 0)
                    *listed_as_link = TRUE;
                g_strfreev(parts);
                continue;
            }
            if (!g_str_has_prefix(*line, "F "))
                continue;
            char **parts = g_strsplit(*line, " ", 4);
            if (g_strv_length(parts) == 4 && strcmp(parts[3], rel) == 0)
                *digest = g_strdup(parts[1]);
            g_strfreev(parts);
            if (*digest)
                break;
        }
        g_strfreev(lines);
        if (*digest)
            return TRUE;
    }
    return *listed_as_link;
}

static char *manifest_problem(const char *root, const char *file)
{
    char real_root[PATH_MAX], real_file[PATH_MAX], theme_dir[PATH_MAX];
    if (!file || !realpath(root, real_root) || !realpath(file, real_file))
        return g_strdup("file or root cannot be resolved");
    g_snprintf(theme_dir, sizeof theme_dir, "%s/Resina", real_root);
    size_t prefix = strlen(theme_dir);
    if (strncmp(real_file, theme_dir, prefix) != 0 || real_file[prefix] != '/')
        return g_strdup("resolved outside the theme under test");
    const char *rel = real_file + prefix + 1;
    char *digest = NULL;
    gboolean link = FALSE;
    if (!manifest_digest_for(theme_dir, rel, &digest, &link) || !digest) {
        g_free(digest);
        return g_strdup("not listed in the manifest");
    }
    char *content = NULL;
    gsize length = 0;
    if (!g_file_get_contents(real_file, &content, &length, NULL)) {
        g_free(digest);
        return g_strdup("file cannot be read");
    }
    char *actual = g_compute_checksum_for_data(G_CHECKSUM_SHA256, (const guchar *)content, length);
    gboolean same = strcmp(actual, digest) == 0;
    g_free(actual);
    g_free(content);
    g_free(digest);
    return same ? NULL : g_strdup("differs from the manifest");
}

#endif
