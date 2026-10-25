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
#include <QStandardPaths>
#include <QStringList>
#include <QSvgRenderer>
#include <QTextStream>

#include "manifest.h"

namespace {

constexpr int kPixelTolerance = 1;
constexpr int kMinimumCoveragePercent = 2;

struct Expectation {
    QString name;
    QString kind;
    QString target;
};

QString findIn(const QString &themeDir, const QString &name)
{
    const QStringList groups = {QStringLiteral("scalable"), QStringLiteral("symbolic")};
    for (const QString &group : groups) {
        QDir groupDir(themeDir + QLatin1Char('/') + group);
        const QStringList contexts = groupDir.entryList(QDir::Dirs | QDir::NoDotAndDotDot, QDir::Name);
        for (const QString &context : contexts) {
            const QString path = groupDir.filePath(context + QLatin1Char('/') + name + QStringLiteral(".svg"));
            if (QFileInfo(path).exists())
                return path;
        }
    }
    return QString();
}

QImage reference(const QString &file, int size)
{
    QImage image(size, size, QImage::Format_ARGB32_Premultiplied);
    image.fill(Qt::transparent);
    QSvgRenderer renderer(file);
    if (!renderer.isValid())
        return QImage();
    QPainter painter(&image);
    renderer.render(&painter);
    painter.end();
    return image;
}

QString referenceFile(const QString &resolved, int size)
{
    const QFileInfo info(resolved);
    QString directory = info.absolutePath();
    for (const QString &tier : {QStringLiteral("-small"), QStringLiteral("-medium")}) {
        if (directory.endsWith(tier))
            directory.chop(tier.size());
    }
    const QString tier = size <= 24 ? QStringLiteral("-small") : (size <= 64 ? QStringLiteral("-medium") : QString());
    const QString sized = directory + tier + QLatin1Char('/') + info.fileName();
    if (!tier.isEmpty() && QFileInfo::exists(sized))
        return sized;
    return directory + QLatin1Char('/') + info.fileName();
}

int maxDifference(const QImage &a, const QImage &b)
{
    if (a.isNull() || b.isNull() || a.size() != b.size())
        return 1000;
    int worst = 0;
    for (int y = 0; y < a.height(); ++y) {
        for (int x = 0; x < a.width(); ++x) {
            const QRgb p = a.pixel(x, y);
            const QRgb q = b.pixel(x, y);
            worst = qMax(worst, qAbs(qRed(p) - qRed(q)));
            worst = qMax(worst, qAbs(qGreen(p) - qGreen(q)));
            worst = qMax(worst, qAbs(qBlue(p) - qBlue(q)));
            worst = qMax(worst, qAbs(qAlpha(p) - qAlpha(q)));
        }
    }
    return worst;
}

int opaquePixels(const QImage &image)
{
    int count = 0;
    for (int y = 0; y < image.height(); ++y)
        for (int x = 0; x < image.width(); ++x)
            if (qAlpha(image.pixel(x, y)) > 8)
                ++count;
    return count;
}

QList<Expectation> readExpectations(const QString &path)
{
    QList<Expectation> list;
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text))
        return list;
    QTextStream stream(&file);
    while (!stream.atEnd()) {
        const QString line = stream.readLine();
        if (line.isEmpty())
            continue;
        const QStringList parts = line.split(QLatin1Char('\t'));
        Expectation e;
        e.name = parts.value(0);
        e.kind = parts.value(1);
        e.target = parts.value(2);
        list.append(e);
    }
    return list;
}

}

int main(int argc, char **argv)
{
    qputenv("QT_QPA_PLATFORM", qgetenv("QT_QPA_PLATFORM").isEmpty() ? QByteArray("offscreen") : qgetenv("QT_QPA_PLATFORM"));
    QGuiApplication app(argc, argv);
    QCommandLineParser parser;
    parser.addOption({QStringLiteral("root"), QStringLiteral("Directory containing the Resina theme"), QStringLiteral("dir")});
    parser.addOption({QStringLiteral("decoy"), QStringLiteral("Directory containing a decoy hicolor theme"), QStringLiteral("dir")});
    parser.addOption({QStringLiteral("expect"), QStringLiteral("Expectation table"), QStringLiteral("file")});
    parser.addOption({QStringLiteral("default-paths"), QStringLiteral("Use the default icon search paths")});
    parser.addOption({QStringLiteral("sizes"), QStringLiteral("Comma separated sizes"), QStringLiteral("list"), QStringLiteral("16,24,32,48,64,128")});
    parser.process(app);

    const QString root = parser.value(QStringLiteral("root"));
    const QString decoy = parser.value(QStringLiteral("decoy"));
    const bool defaultPaths = parser.isSet(QStringLiteral("default-paths"));
    if (!defaultPaths) {
        QStringList paths = {root};
        if (!decoy.isEmpty())
            paths.append(decoy);
        QIcon::setThemeSearchPaths(paths);
        QIcon::setFallbackSearchPaths(QStringList());
    }
    QIcon::setThemeName(QStringLiteral("Resina"));

    QTextStream out(stdout);
    int failures = 0;
    auto report = [&](bool ok, const QString &name, const QString &kind, const QString &detail) {
        out << (ok ? "PASS" : "FAIL") << '\t' << name << '\t' << kind << '\t' << detail << '\n';
        if (!ok)
            ++failures;
    };

    if (QIcon::themeName() != QLatin1String("Resina")) {
        report(false, QStringLiteral("theme"), QStringLiteral("setup"), QStringLiteral("theme name not applied"));
        return 1;
    }

    QList<int> sizes;
    for (const QString &s : parser.value(QStringLiteral("sizes")).split(QLatin1Char(',')))
        sizes.append(s.toInt());

    QString themeDir = root + QStringLiteral("/Resina");
    if (defaultPaths) {
        themeDir = QStandardPaths::locate(QStandardPaths::GenericDataLocation, QStringLiteral("icons/Resina"), QStandardPaths::LocateDirectory);
        out << "THEMEDIR\t" << (themeDir.isEmpty() ? QStringLiteral("(not installed)") : themeDir) << '\n';
        out << "SEARCHPATHS\t" << QIcon::themeSearchPaths().join(QLatin1Char(':')) << '\n';
    }
    const QString decoyDir = decoy + QStringLiteral("/hicolor");
    const QHash<QString, QString> manifest = readManifest(themeDir);
    const QList<Expectation> expectations = readExpectations(parser.value(QStringLiteral("expect")));
    if (expectations.isEmpty()) {
        report(false, QStringLiteral("expectations"), QStringLiteral("setup"), QStringLiteral("no expectations loaded"));
        return 1;
    }

    for (const Expectation &e : expectations) {
        const QString ownFile = findIn(themeDir, e.name);
        const QString decoyFile = decoy.isEmpty() ? QString() : findIn(decoyDir, e.name);
        const QIcon icon = QIcon::fromTheme(e.name);

        if (e.kind == QLatin1String("own") || e.kind == QLatin1String("alias")) {
            if (ownFile.isEmpty()) {
                report(false, e.name, e.kind, QStringLiteral("not present in theme tree"));
                continue;
            }
            const QFileInfo info(ownFile);
            const QString resolved = info.canonicalFilePath();
            if (e.kind == QLatin1String("alias")) {
                if (!info.isSymLink() || QFileInfo(resolved).completeBaseName() != e.target) {
                    report(false, e.name, e.kind, QStringLiteral("alias does not resolve to ") + e.target);
                    continue;
                }
            } else if (info.isSymLink()) {
                report(false, e.name, e.kind, QStringLiteral("expected a real file"));
                continue;
            }
            QString problem = manifestProblem(themeDir, manifest, ownFile);
            if (problem.isEmpty() && info.isSymLink())
                problem = manifestProblem(themeDir, manifest, resolved);
            if (!problem.isEmpty()) {
                report(false, e.name, e.kind, problem);
                continue;
            }
            if (icon.isNull()) {
                report(false, e.name, e.kind, QStringLiteral("QIcon is null"));
                continue;
            }
            bool ok = true;
            QString detail;
            for (int size : sizes) {
                const QImage got = icon.pixmap(QSize(size, size)).toImage().convertToFormat(QImage::Format_ARGB32_Premultiplied);
                const QImage want = reference(referenceFile(resolved, size), size);
                const int diff = maxDifference(got, want);
                if (diff > kPixelTolerance) {
                    ok = false;
                    detail = QStringLiteral("size %1 differs from theme file (max %2)").arg(size).arg(diff);
                    break;
                }
                if (opaquePixels(got) * 100 < size * size * kMinimumCoveragePercent) {
                    ok = false;
                    detail = QStringLiteral("size %1 has too little visible content").arg(size);
                    break;
                }
            }
            report(ok, e.name, e.kind, ok ? QStringLiteral("matches %1").arg(QFileInfo(resolved).fileName()) : detail);
        } else if (e.kind == QLatin1String("generic")) {
            const QString targetFile = findIn(themeDir, e.target);
            if (!ownFile.isEmpty() || !decoyFile.isEmpty() || targetFile.isEmpty()) {
                report(false, e.name, e.kind, QStringLiteral("fixture does not isolate generic fallback"));
                continue;
            }
            const QImage got = icon.pixmap(QSize(64, 64)).toImage().convertToFormat(QImage::Format_ARGB32_Premultiplied);
            const int diff = maxDifference(got, reference(QFileInfo(targetFile).canonicalFilePath(), 64));
            const bool ok = !icon.isNull() && diff <= kPixelTolerance && opaquePixels(got) > 0;
            report(ok, e.name, e.kind, ok ? QStringLiteral("generic fallback to ") + e.target : QStringLiteral("generic fallback not resolved"));
        } else if (e.kind == QLatin1String("miss")) {
            const bool ok = ownFile.isEmpty() && decoyFile.isEmpty() && icon.isNull();
            report(ok, e.name, e.kind, ok ? QStringLiteral("no icon") : QStringLiteral("unexpected icon supplied"));
        } else if (e.kind == QLatin1String("fallback")) {
            if (!ownFile.isEmpty() || decoyFile.isEmpty()) {
                report(false, e.name, e.kind, QStringLiteral("fixture does not isolate a fallback supply"));
                continue;
            }
            const QImage got = icon.pixmap(QSize(64, 64)).toImage().convertToFormat(QImage::Format_ARGB32_Premultiplied);
            const int diff = maxDifference(got, reference(decoyFile, 64));
            const bool ok = !icon.isNull() && diff <= kPixelTolerance;
            report(ok, e.name, e.kind, ok ? QStringLiteral("supplied by fallback theme") : QStringLiteral("fallback not resolved"));
        } else {
            report(false, e.name, e.kind, QStringLiteral("unknown expectation kind"));
        }
    }

    out << "SUMMARY\t" << expectations.size() << '\t' << failures << '\n';
    return failures ? 1 : 0;
}
