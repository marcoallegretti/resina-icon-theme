# Resina icon theme

`Resina` is a freedesktop icon theme for the Canopia desktop and the Resina UI toolkit. It follows the freedesktop Icon Theme Specification, so toolkits that implement the specification load it without theme-specific code.

The theme has two icon languages:

- Full-colour icons on a 128-unit grid for applications, places, file types, devices and status.
- Symbolic icons on a 24-unit grid with `-symbolic` names. They are filled outlines painted with `currentColor`, so toolkits can recolour them. Each file also carries the `current-color-scheme` stylesheet that KDE rewrites, and `index.theme` sets `FollowsColorScheme=true`, so KDE applications follow the colour scheme as they do with Breeze.

## Contents

| Path | Content |
|---|---|
| `src/color`, `src/symbolic` | canonical artwork |
| `names/` | classification of every icon and the symbolic contexts |
| `aliases/` | compatibility names that point at existing drawings |
| `tools/` | build, validation, install and packaging, and the maintainer tool for badge lettering |
| `tests/` | unit tests, Qt and GTK probes, expectation tables |
| `examples/` | a Qt Quick application and a QuickShell configuration |

## Sets

| Set | Content |
|---|---|
| `core` | system, place, device, status, file-type and symbolic icons, and generic application icons |
| `thirdparty` | application illustrations, product-named folders and file types, and symbolic emblems that refer to third-party software by name; installed over `core` |
| `full` | both |

`names/color-classes.tsv` and `names/symbolic-classes.tsv` assign every icon to a set. The build stops when an icon has no class. Names that come from the freedesktop and shared-mime-info vocabularies, including programming-language and file-format names, stay in `core`; names of products, vendors and projects go to `thirdparty`. A third column `thirdparty` in `aliases/*.tsv` places a compatibility link in the overlay when its name is a product name and its target is generic.

## Requirements

Python 3.12 or newer with the packages in `requirements.txt`; install them in a virtual environment (`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`), which distributions that mark the system Python as externally managed require. Building the Qt and GTK probes needs a Qt 6 development environment (Gui, Svg, Quick, QuickControls2) and GTK 3 or GTK 4 development files. The rendering-fidelity tests use `rsvg-convert` and ImageMagick `compare` and are skipped when they are absent.

## Build, validate, package

```
python3 tools/build.py OUT --profile full
python3 tools/validate.py OUT --repo .
python3 tools/pack.py OUT resina-icon-theme.tar.xz --epoch 1700000000
```

`OUT` must not exist. The build runs offline and is deterministic: two builds from the same tree are byte-identical. It converts SVG features that renderers handle differently into plain geometry and stops with the icon name when it meets input it cannot convert. `validate.py --repo` also compares the tree with the name data and the alias tables. `pack.py` validates the tree first and writes `resina-icon-theme.tar.xz.sha256` beside the archive.

The built tree contains `index.theme`, the icons, `MANIFEST.core` and `MANIFEST.thirdparty` (digests of every installed file), `NOTICE` and the licence texts.

## Install

```
python3 tools/install.py install OUT
python3 tools/install.py uninstall
```

The default target is `$XDG_DATA_HOME/icons/Resina`, or `~/.local/share/icons/Resina` when `XDG_DATA_HOME` is unset; `--icons-dir /usr/share/icons` installs system-wide. The installer verifies every file against its manifest digest before it writes, rejects manifest entries that leave the theme directory and refuses to write through symbolic links. Without `--force` it stops when an untracked file collides with a theme file. `--force` installs into a theme directory that this tool did not create, overwriting files that collide with theme files and leaving other files in place; it also discards unreadable manifests, and `uninstall --force` does the same and reports them. An interrupted installation leaves a `PENDING.<component>` record, and running the installer again or uninstalling completes the work; an interrupted uninstall keeps edited files tracked. Uninstall also removes temporary files left by a killed installation. Manifests are flushed to disk before the installer relies on them. Edited theme files are kept on upgrade and on uninstall, and remain tracked. `uninstall --component thirdparty` removes only the overlay.

The `Makefile` wraps these steps for packagers: `make install DESTDIR="$pkgdir" PREFIX=/usr` builds, validates and installs into `$DESTDIR$PREFIX/share/icons/Resina`, `make uninstall` removes it, `make check` runs the tests and `make dist` writes the archive (the archive epoch comes from `SOURCE_DATE_EPOCH`, by default the date of the last commit). Without `DESTDIR` it also runs `gtk-update-icon-cache`. Equivalently, stage the theme with `python3 tools/install.py install OUT --icons-dir "$DESTDIR/usr/share/icons"`, or extract the archive, whose top-level directory is `Resina`, into the icon directory; an archive extraction does not remove files dropped between releases and does not remove an existing `icon-theme.cache`, so delete it or run `gtk-update-icon-cache -f` afterwards, otherwise GTK does not see new icons. Verify the archive with `sha256sum -c resina-icon-theme.tar.xz.sha256` in the directory that holds it. The installer needs a POSIX system with symbolic links and does not run on Windows. The installer removes a stale `icon-theme.cache` on install and uninstall; run `gtk-update-icon-cache` afterwards if the distribution expects a cache. `uninstall` leaves the other component installed when `--component` is given and refuses to remove `core` while the overlay remains. Concurrent installations into the same directory are serialised.

The theme inherits `hicolor` only. Icons the theme does not provide fall back to `hicolor`; whether a desktop then consults another theme is the desktop's decision.

The theme ships SVG only. GTK 3 applications need the gdk-pixbuf SVG loader (`librsvg2-common` on Debian and Ubuntu) to draw it; without it GTK 3 falls back to another theme. Snap applications do not see an icon theme in the user's home directory; they use it only through a snap that provides the `icon-themes` content interface. Flatpak applications see `~/.local/share/icons` through `/run/host/user-share/icons`. Electron draws its tray icon and window contents from its own bundled images, and follows the theme only in the GTK file dialogs and in `app.getFileIcon`.

## Use in Qt Quick

Select the theme with `QIcon::setThemeName("Resina")` or through the desktop's icon theme setting, then use ordinary controls:

```
ToolButton { icon.name: "folder"; icon.color: "transparent" }
ToolButton { icon.name: "go-next-symbolic" }
```

Qt Quick Controls tint icons with the text colour by default. Full-colour icons (applications, places, file types, devices, status) need `icon.color: "transparent"` to keep their own colours; symbolic icons keep the default tint. A complete example is in `examples/qt-quick`.

Names are case sensitive. Application identifiers keep their case, for example `org.inkscape.Inkscape`. A name with a dash that is not present falls back to its prefix, as the Icon Naming Specification describes; toolkits apply this to some contexts and not to others (Qt skips `Applications` and `MimeTypes` directories for it). Action, status, device, category and emblem icons exist in their `-symbolic` form (`edit-copy-symbolic`), and every such name that has no full-colour icon is also reachable by its plain name (`edit-copy`) through a link to the symbolic file. GTK does not recolour a file reached through a plain name (the GTK probes check this) and draws it in the stylesheet's default colour `#868686` (at least 3:1 on the flat backgrounds of Adwaita, Breeze and BlackMATE, light and dark); KDE recolours plain and `-symbolic` names alike; Qt Quick Controls tint them with `icon.color` or the default text colour.

## Use with GTK and QuickShell

The symbolic icons are filled outlines, which GTK 3 and GTK 4 recolour alike. Fifty-nine directional symbols also ship a `-symbolic-rtl` variant that GTK picks for right-to-left text: forty-nine are horizontal mirrors of the left-to-right drawing (`names/rtl-mirrors.txt`) and ten are drawn separately in `src/symbolic-rtl`, where a mirror would be wrong (the paragraph mark and arrows of `format-text-direction`, the numbers of `view-list-ordered`, the slash of `network-cellular-disabled`, the swapped start and end handles of `selection-start` and `selection-end`). `examples/quickshell/shell.qml` is a QuickShell configuration that loads icons by name; start it with `QS_ICON_THEME=Resina` after installing the theme.

The clock and calendar icons carry `data-dynamic`, `data-box` and `data-pivot` attributes and named layers (`#hour-hand`, `#minute-hand`, `#second-hand`, `#date-slot`, `#weekday-slot`) for shells that animate them. `examples/quickshell/DynamicClock.qml` and `DynamicCalendar.qml` do this in QuickShell: they read the installed SVG, rewrite the hand angles or fill the date and weekday slots, and hand the result to an `Image` as a `data:` URI once a second or once a minute.

## Tests

```
python3 -m unittest discover -s tests
```

The suite builds the real tree, validates it against the sources, exercises the installer against crafted manifests, and checks reproducibility with a recorded digest of the manifests (`tests/golden/manifests.sha256`; update it with the artwork). A missing Python package fails the suite; tests that need compiled probes, a display or external tools are listed as skipped with their reason.

Probes that need compiled helpers or a display server run when their environment is set; otherwise `unittest -v` lists them as skipped with the reason.

| Variable | Enables |
|---|---|
| `RESINA_QT_BUILD` | Qt lookup and Qt Quick Controls probes (`cmake -S tests/qt -B DIR && cmake --build DIR`) |
| `RESINA_QT_PLATFORM` | Qt platform for the installed-lookup test; default is `wayland` or `xcb` from the environment |
| `RESINA_KDE_BUILD` | KDE Frameworks 6 probe: symbolic icons follow the colour scheme, colour icons keep their colours (`cmake -S tests/kde -B DIR && cmake --build DIR`; needs `kf6-kiconthemes` development files) |
| `RESINA_GTK_BUILD` | GTK 3 and GTK 4 probes (`cmake -S tests/gtk -B DIR && cmake --build DIR`); needs `DISPLAY` or `WAYLAND_DISPLAY` |
| `RESINA_FONT` | outlining tests with the pinned font file |

The Qt and GTK probes test a sample of the icons selected in the expectation tables, not every icon.

The Qt probes check lookup, aliases, generic fallback, original colours of full-colour icons, tinting of symbolic icons, light and dark backgrounds, sizes 16 to 128 and scale factors 1, 1.5 and 2. An icon counts as provided by this theme only when the installed file matches its manifest digest and its rendering matches the file, so an icon supplied by `hicolor` is reported separately. Each probe has negative controls that must fail for the stated reason. The GTK probes check the resolved file, original colours, symbolic detection and recolouring with two foreground colours.

## Rendering notes

The sources use SVG features that renderers handle differently. The build converts them so the installed files render alike:

- the rim filter and clip paths of full-colour icons become plain shapes, and the blurred contact shadow becomes twelve stacked ellipses of falling opacity, so that it looks the same in every renderer: QtSvg implements `feGaussianBlur` only from Qt 6.7, and Qt 6.4, which current Debian and Ubuntu releases ship, draws a hard-edged ellipse
- symbolic strokes become filled outlines
- badge lettering is outlined from Atkinson Hyperlegible Next

Differences from the source rendering: the rim around thin shapes uses rounded joins where the source filter dilates with a square, so thin tips and sharp corners end slightly rounder; the contact shadow and the rim halo under it are approximations of the blur by stacked ellipses. Measured as RMSE between the built icon and its source, both rendered with rsvg-convert at 128 pixels on a flat background, over the 875 full-colour icons, the mean is about 0.029 and the largest is below 0.07. The symbolic icons, compared on the alpha channel at 96 pixels, differ from their sources by a mean RMSE of 0.003 and at most 0.012.

## Maintainer tools

`tools/textoutline.py` is run by maintainers when badge artwork changes; it is not part of the build. It replaces badge `<text>` with outlines and needs the packages in `requirements-sources.txt` and the pinned font file (`AtkinsonHyperlegibleNext[wght].ttf` from https://github.com/googlefonts/atkinson-hyperlegible-next at commit `7925f50f649b3813257faf2f4c0b381011f434f1`; the digest is recorded in the tool). It fails on any glyph the font lacks.

## Application coverage

The desktop applications of GNOME, KDE Plasma, XFCE, LXQt, MATE and Cinnamon request their launcher icons by names such as `org.gnome.Nautilus`, `org.kde.dolphin` or `org.xfce.thunar`. The theme provides these as aliases of its own drawings (`files`, `terminal`, `settings`, `text-editor`, and so on) and keeps the list in `tests/data/launcher-icons.txt`, which a test checks against the built tree. The list holds the 63 distinct names that launchers of the file managers, terminals, editors, settings panels and system tools of those desktops request and that the theme provides. Launchers of other applications, and a few desktop-specific panels, fall back to `hicolor` or to the application's own icon.

Plasma and KDE applications also request names the freedesktop vocabulary does not have, such as `application-menu`, `configure`, `battery-050`, `network-wireless-80` or `preferences-desktop-mouse`. KIconLoader tries every shorter name inside the selected theme before it reaches Breeze, so a missing name lands on a generic Resina icon rather than the specific one; the theme therefore aliases the names seen in System Settings, Dolphin, Kate and the Plasma tray to its own drawings, and a KDE Frameworks probe resolves a sample of them (`tests/test_kde.py`). Wi-Fi names with a lock (`network-wireless-80-locked`) and names for which Resina has no drawing are not aliased and fall back to the generic icon.

KDE draws its busy indicator from a frame sheet instead of rotating the icon. The theme ships `process-working` as a sheet of 12 frames in 4 columns and 3 rows at `animations/16`, `animations/22`, `animations/24` and `animations/32`, declared as Fixed sizes in `index.theme`, which is the layout `KPixmapSequenceLoader` expects. The sheets use the fixed colour `#868686`, because KDE does not recolour them; a test loads them through the KDE Frameworks loader at each size.

Folders carry a symbol that is under one pixel thick at 16 to 24 px, with a contrast of 2.3 to 1 on the folder. The theme therefore draws it in three steps. From 65 px up, `scalable/places` keeps the original relief. For 25 to 64 px, `scalable/places-medium` enlarges the symbol, thickens its stroke and darkens it to at least 3.5 to 1 while keeping the light copy under it that gives the relief. For 16 to 24 px, `scalable/places-small` drops the relief and darkens the symbol to at least 4.5 to 1; `src/color/places-small` holds the drawings made by hand for that size. The other folders get both treatments from their regular drawing when the theme is built, and the index keeps the three ranges apart. A folder without the standard symbol keeps its single drawing.

## Requesting an icon

A missing application icon is requested by the `Icon=` value of its desktop file (`grep ^Icon= /usr/share/applications/NAME.desktop`) and, where a drawing for the same application already exists under another name, the name it should alias. Product names go to `thirdparty`, names from the freedesktop vocabulary go to `core`; see Sets.

## Licence

EUPL-1.2, see `LICENSES/` and `NOTICE`. The badge lettering derives from a font under the SIL Open Font License 1.1. Product names in the third-party set belong to their owners.
