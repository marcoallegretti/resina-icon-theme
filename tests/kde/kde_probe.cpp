// SPDX-License-Identifier: EUPL-1.2
#include <KIconLoader>
#include <KIconTheme>
#include <KPixmapSequenceLoader>
#include <QApplication>
#include <QColor>
#include <QImage>
#include <QPalette>
#include <QPixmap>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <QFile>
#include <QTextStream>

struct Mean {
    double red = -1, green = -1, blue = -1;
    int opaque = 0;
};

static Mean measure(const QImage &source)
{
    const QImage image = source.convertToFormat(QImage::Format_ARGB32);
    double red = 0, green = 0, blue = 0;
    int opaque = 0;
    for (int y = 0; y < image.height(); y++) {
        for (int x = 0; x < image.width(); x++) {
            const QRgb pixel = image.pixel(x, y);
            if (qAlpha(pixel) >= 128) {
                red += qRed(pixel);
                green += qGreen(pixel);
                blue += qBlue(pixel);
                opaque++;
            }
        }
    }
    Mean mean;
    mean.opaque = opaque;
    if (opaque) {
        mean.red = red / opaque;
        mean.green = green / opaque;
        mean.blue = blue / opaque;
    }
    return mean;
}

static QPalette paletteWithText(const QColor &window, const QColor &text)
{
    QPalette palette;
    for (auto group : {QPalette::Active, QPalette::Inactive, QPalette::Disabled}) {
        palette.setColor(group, QPalette::Window, window);
        palette.setColor(group, QPalette::WindowText, text);
        palette.setColor(group, QPalette::Base, window);
        palette.setColor(group, QPalette::Text, text);
        palette.setColor(group, QPalette::Button, window);
        palette.setColor(group, QPalette::ButtonText, text);
        palette.setColor(group, QPalette::Highlight, QColor("#3daee9"));
        palette.setColor(group, QPalette::HighlightedText, QColor("#ffffff"));
    }
    return palette;
}

static bool near(const Mean &mean, const QColor &colour, int tolerance)
{
    return mean.opaque > 0 && std::abs(mean.red - colour.red()) <= tolerance && std::abs(mean.green - colour.green()) <= tolerance
        && std::abs(mean.blue - colour.blue()) <= tolerance;
}

static int failures;

static void report(bool ok, const QString &name, const QString &detail)
{
    printf("%s\t%s\t%s\n", ok ? "PASS" : "FAIL", qPrintable(name), qPrintable(detail));
    if (!ok)
        failures++;
}

int main(int argc, char **argv)
{
    QApplication application(argc, argv);
    const QString theme = qEnvironmentVariable("RESINA_KDE_THEME", QStringLiteral("Resina"));
    if (KIconTheme::current() != theme) {
        printf("BLOCKED\tsetup\ttheme %s is not selected (current %s)\n", qPrintable(theme), qPrintable(KIconTheme::current()));
        return 2;
    }
    if (argc == 4 && QString::fromLocal8Bit(argv[1]) == QStringLiteral("--sequence")) {
        const KPixmapSequence sequence = KPixmapSequenceLoader::load(QString::fromLocal8Bit(argv[2]), QString::fromLocal8Bit(argv[3]).toInt());
        printf("SEQUENCE\t%s\t%s\t%d\t%d\n", argv[3], sequence.isValid() ? "valid" : "invalid", sequence.frameCount(), sequence.isValid() ? sequence.frameSize().width() : 0);
        return 0;
    }
    if (argc == 4 && QString::fromLocal8Bit(argv[1]) == QStringLiteral("--at")) {
        QString path;
        KIconLoader::global()->loadIcon(QString::fromLocal8Bit(argv[2]), KIconLoader::NoGroup, QString::fromLocal8Bit(argv[3]).toInt(), KIconLoader::DefaultState, QStringList(), &path, true);
        printf("AT\t%s\t%s\t%s\n", argv[2], argv[3], qPrintable(path));
        return 0;
    }
    if (argc == 3 && QString::fromLocal8Bit(argv[1]) == QStringLiteral("--paths")) {
        QFile list(QString::fromLocal8Bit(argv[2]));
        if (!list.open(QIODevice::ReadOnly | QIODevice::Text)) {
            printf("BLOCKED\tsetup\tcannot read %s\n", argv[2]);
            return 2;
        }
        QTextStream stream(&list);
        while (!stream.atEnd()) {
            const QString name = stream.readLine().trimmed();
            if (name.isEmpty())
                continue;
            QString path;
            KIconLoader::global()->loadIcon(name, KIconLoader::NoGroup, 22, KIconLoader::DefaultState, QStringList(), &path, true);
            printf("PATH\t%s\t%s\n", qPrintable(name), qPrintable(path));
        }
        return 0;
    }
    struct Case {
        const char *name;
        bool recoloured;
    };
    const Case cases[] = {
        {"edit-copy-symbolic", true},
        {"edit-copy", true},
        {"go-next", true},
        {"utilities-terminal-symbolic", true},
        {"folder", false},
    };
    const QColor lightText("#eff0f1"), darkText("#232629");
    const struct {
        const char *label;
        QColor window;
        QColor text;
    } schemes[] = {{"dark", QColor("#31363b"), lightText}, {"light", QColor("#eff0f1"), darkText}};
    for (const auto &scheme : schemes) {
        const QPalette palette = paletteWithText(scheme.window, scheme.text);
        application.setPalette(palette);
        KIconLoader::global()->setCustomPalette(palette);
        for (int size : {22, 48}) {
            for (const Case &c : cases) {
                QString path;
                const QPixmap pixmap = KIconLoader::global()->loadIcon(QString::fromLatin1(c.name), KIconLoader::NoGroup, size, KIconLoader::DefaultState, QStringList(), &path, true);
                const Mean mean = measure(pixmap.toImage());
                const QString label = QStringLiteral("%1 %2 %3 px").arg(QString::fromLatin1(c.name), QString::fromLatin1(scheme.label)).arg(size);
                const QString detail = QStringLiteral("mean %1,%2,%3 over %4 pixels, file %5").arg(qRound(mean.red)).arg(qRound(mean.green)).arg(qRound(mean.blue)).arg(mean.opaque).arg(path);
                if (path.isEmpty() || mean.opaque == 0) {
                    report(false, label, QStringLiteral("not resolved or blank"));
                } else if (c.recoloured) {
                    report(near(mean, scheme.text, 3), label, detail);
                } else {
                    report(!near(mean, scheme.text, 12) && !near(mean, QColor("#000000"), 12), label + QStringLiteral(" keeps its own colours"), detail);
                }
            }
        }
    }
    printf("SUMMARY\t%d\n", failures);
    return failures ? 1 : 0;
}
