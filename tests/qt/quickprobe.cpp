// SPDX-License-Identifier: EUPL-1.2
#include <QCommandLineParser>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QGuiApplication>
#include <QHash>
#include <QIcon>
#include <QImage>
#include <QPainter>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickItem>
#include <QQuickStyle>
#include <QQuickWindow>
#include <QSGRendererInterface>
#include <QSvgRenderer>
#include <QTextStream>
#include <QTimer>

#include "manifest.h"

namespace {

struct Cell {
    QString id;
    QString name;
    int size = 0;
    QString tint;
    QString bg;
    bool enabled = true;
    QString check;
};

constexpr double kOriginalTolerance = 3.0;
constexpr double kDistinctMinimum = 40.0;
constexpr int kMinimumVisiblePixels = 20;

QString findIn(const QString &themeDir, const QString &name)
{
    const QStringList groups = {QStringLiteral("scalable"), QStringLiteral("symbolic")};
    for (const QString &group : groups) {
        QDir groupDir(themeDir + QLatin1Char('/') + group);
        for (const QString &context : groupDir.entryList(QDir::Dirs | QDir::NoDotAndDotDot, QDir::Name)) {
            const QString path = groupDir.filePath(context + QLatin1Char('/') + name + QStringLiteral(".svg"));
            if (QFileInfo(path).exists())
                return QFileInfo(path).canonicalFilePath();
        }
    }
    return QString();
}

QImage renderSvg(const QString &file, int size)
{
    QImage image(size, size, QImage::Format_ARGB32_Premultiplied);
    image.fill(Qt::transparent);
    QSvgRenderer renderer(file);
    QPainter painter(&image);
    renderer.render(&painter);
    painter.end();
    return image;
}

QImage compose(const QImage &icon, const QSize &cell, const QColor &bg, const QColor &tint)
{
    QImage out(cell, QImage::Format_ARGB32_Premultiplied);
    out.fill(bg);
    QImage layer = icon;
    if (tint.isValid()) {
        QPainter mask(&layer);
        mask.setCompositionMode(QPainter::CompositionMode_SourceIn);
        mask.fillRect(layer.rect(), tint);
        mask.end();
    }
    QPainter painter(&out);
    painter.drawImage((cell.width() - layer.width()) / 2, (cell.height() - layer.height()) / 2, layer);
    painter.end();
    return out;
}

int channelDistance(QRgb a, QRgb b)
{
    return qMax(qMax(qAbs(qRed(a) - qRed(b)), qAbs(qGreen(a) - qGreen(b))), qAbs(qBlue(a) - qBlue(b)));
}

double distance(const QImage &actual, const QImage &expected, const QColor &bg, int dx, int dy)
{
    const QRgb background = bg.rgb();
    long sum = 0;
    long count = 0;
    for (int y = 0; y < expected.height(); ++y) {
        for (int x = 0; x < expected.width(); ++x) {
            const int ax = x + dx;
            const int ay = y + dy;
            const QRgb e = expected.pixel(x, y);
            const QRgb a = (ax >= 0 && ay >= 0 && ax < actual.width() && ay < actual.height()) ? actual.pixel(ax, ay) : background;
            if (channelDistance(e, background) > 8 || channelDistance(a, background) > 8) {
                sum += channelDistance(a, e);
                ++count;
            }
        }
    }
    return count ? double(sum) / double(count) : 0.0;
}

int visiblePixels(const QImage &image, const QColor &bg)
{
    int count = 0;
    for (int y = 0; y < image.height(); ++y)
        for (int x = 0; x < image.width(); ++x)
            if (channelDistance(image.pixel(x, y), bg.rgb()) > 8)
                ++count;
    return count;
}

double bestDistance(const QImage &actual, const QImage &expected, const QColor &bg)
{
    double best = 1e9;
    for (int dy = -2; dy <= 2; ++dy)
        for (int dx = -2; dx <= 2; ++dx)
            best = qMin(best, distance(actual, expected, bg, dx, dy));
    return best;
}

QColor strongestColour(const QImage &actual, const QColor &bg)
{
    int best = 0;
    QRgb colour = bg.rgb();
    for (int y = 0; y < actual.height(); ++y) {
        for (int x = 0; x < actual.width(); ++x) {
            const QRgb p = actual.pixel(x, y);
            const int d = channelDistance(p, bg.rgb());
            if (d > best) {
                best = d;
                colour = p;
            }
        }
    }
    return QColor(colour | 0xff000000);
}

QList<Cell> readCells(const QString &path)
{
    QList<Cell> cells;
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text))
        return cells;
    QTextStream stream(&file);
    while (!stream.atEnd()) {
        const QString line = stream.readLine();
        if (line.isEmpty())
            continue;
        const QStringList p = line.split(QLatin1Char('\t'));
        if (p.size() < 7)
            return QList<Cell>();
        Cell c;
        c.id = p[0];
        c.name = p[1];
        c.size = p[2].toInt();
        c.tint = p[3];
        c.bg = p[4];
        c.enabled = p[5] == QLatin1String("1");
        c.check = p[6];
        cells.append(c);
    }
    return cells;
}

void collect(QQuickItem *item, QHash<QString, QQuickItem *> *found)
{
    if (item->objectName().startsWith(QLatin1String("cell-")))
        found->insert(item->objectName().mid(5), item);
    for (QQuickItem *child : item->childItems())
        collect(child, found);
}

}

int main(int argc, char **argv)
{
    QQuickWindow::setGraphicsApi(QSGRendererInterface::Software);
    QGuiApplication app(argc, argv);
    QCommandLineParser parser;
    parser.addOption({QStringLiteral("root"), QString(), QStringLiteral("dir")});
    parser.addOption({QStringLiteral("cells"), QString(), QStringLiteral("file")});
    parser.addOption({QStringLiteral("qml"), QString(), QStringLiteral("file")});
    parser.addOption({QStringLiteral("save"), QString(), QStringLiteral("file")});
    parser.process(app);

    QIcon::setThemeSearchPaths({parser.value(QStringLiteral("root"))});
    QIcon::setFallbackSearchPaths(QStringList());
    QIcon::setThemeName(QStringLiteral("Resina"));
    QQuickStyle::setStyle(QStringLiteral("Basic"));

    const QList<Cell> cells = readCells(parser.value(QStringLiteral("cells")));
    if (cells.isEmpty())
        return 2;

    QVariantList model;
    for (const Cell &c : cells) {
        QVariantMap m;
        m[QStringLiteral("id")] = c.id;
        m[QStringLiteral("name")] = c.name;
        m[QStringLiteral("size")] = c.size;
        m[QStringLiteral("tint")] = c.tint;
        m[QStringLiteral("bg")] = c.bg;
        m[QStringLiteral("enabled")] = c.enabled;
        model.append(m);
    }

    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty(QStringLiteral("cellModel"), model);
    engine.load(QUrl::fromLocalFile(parser.value(QStringLiteral("qml"))));
    if (engine.rootObjects().isEmpty())
        return 3;
    auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
    if (!window)
        return 3;

    QTextStream out(stdout);
    int failures = 0;
    int exitCode = 0;
    QTimer::singleShot(1500, &app, [&]() {
        QQuickItem *content = window->contentItem();
        QHash<QString, QQuickItem *> items;
        collect(content, &items);
        const QImage frame = window->grabWindow();
        const double dpr = frame.devicePixelRatio() > 0 ? window->effectiveDevicePixelRatio() : 1.0;
        out << "RENDERER\t" << int(window->rendererInterface()->graphicsApi()) << "\tplatform\t" << QGuiApplication::platformName()
            << "\tdpr\t" << dpr << "\tstyle\t" << QQuickStyle::name() << "\n";
        const QString themeDir = parser.value(QStringLiteral("root")) + QStringLiteral("/Resina");
        QHash<QString, QString> colours;
        const QHash<QString, QString> manifest = readManifest(themeDir);
        for (const Cell &c : cells) {
            QQuickItem *item = items.value(c.id);
            if (!item) {
                out << "FAIL\t" << c.id << "\tcell not created\n";
                ++failures;
                continue;
            }
            const QPointF origin = item->mapToScene(QPointF(0, 0));
            const QRect rect(qRound(origin.x() * dpr), qRound(origin.y() * dpr), qRound(item->width() * dpr), qRound(item->height() * dpr));
            const QImage actual = frame.copy(rect).convertToFormat(QImage::Format_ARGB32_Premultiplied);
            const QColor bg(c.bg);
            const int deviceSize = qRound(c.size * dpr);
            const QString file = findIn(themeDir, c.name);
            const QStringList check = c.check.split(QLatin1Char(':'));
            const QString kind = check.value(0);
            bool ok = false;
            QString detail;
            QString problem;
            if (!file.isEmpty())
                problem = manifestProblem(themeDir, manifest, file);
            if (!problem.isEmpty()) {
                detail = problem;
            } else if (kind == QLatin1String("blank")) {
                QImage plain(rect.size(), QImage::Format_ARGB32_Premultiplied);
                plain.fill(bg);
                const double blank = bestDistance(actual, plain, bg);
                ok = blank == 0.0;
                detail = QStringLiteral("blank metric %1").arg(blank);
            } else if ((kind == QLatin1String("monochrome") || kind == QLatin1String("monochrome-differs")) && !file.isEmpty()) {
                const QColor colour = strongestColour(actual, bg);
                const QImage expected = compose(renderSvg(file, deviceSize), rect.size(), bg, colour);
                const double metric = bestDistance(actual, expected, bg);
                ok = metric <= kOriginalTolerance;
                if (kind == QLatin1String("monochrome"))
                    colours[c.id] = colour.name();
                else
                    ok = ok && colours.contains(check.value(1)) && colours.value(check.value(1)) != colour.name();
                detail = QStringLiteral("single colour %1 metric %2").arg(colour.name()).arg(metric);
            } else if (file.isEmpty()) {
                detail = QStringLiteral("no theme file for reference");
            } else {
                const QImage icon = renderSvg(file, deviceSize);
                QColor tint;
                if (kind == QLatin1String("mask"))
                    tint = QColor(check.value(1));
                const QImage expected = compose(icon, rect.size(), bg, tint);
                const double metric = bestDistance(actual, expected, bg);
                if ((kind == QLatin1String("original") || kind == QLatin1String("mask")) && visiblePixels(expected, bg) < kMinimumVisiblePixels) {
                    detail = QStringLiteral("reference is invisible against the background");
                } else if (kind == QLatin1String("original") || kind == QLatin1String("mask")) {
                    ok = metric <= kOriginalTolerance;
                    detail = QStringLiteral("metric %1 (limit %2)").arg(metric).arg(kOriginalTolerance);
                } else if (kind == QLatin1String("not-original")) {
                    const QImage original = compose(icon, rect.size(), bg, QColor());
                    const double far = bestDistance(actual, original, bg);
                    ok = far >= kDistinctMinimum;
                    detail = QStringLiteral("distance from original %1 (minimum %2)").arg(far).arg(kDistinctMinimum);
                } else {
                    detail = QStringLiteral("unknown check");
                }
            }
            out << (ok ? "PASS" : "FAIL") << '\t' << c.id << '\t' << c.name << '\t' << c.size << '\t' << c.check << '\t' << detail << '\n';
            if (!ok)
                ++failures;
        }
        if (!parser.value(QStringLiteral("save")).isEmpty())
            frame.save(parser.value(QStringLiteral("save")));
        out << "SUMMARY\t" << cells.size() << '\t' << failures << '\n';
        out.flush();
        exitCode = failures ? 1 : 0;
        app.quit();
    });
    app.exec();
    return exitCode;
}
