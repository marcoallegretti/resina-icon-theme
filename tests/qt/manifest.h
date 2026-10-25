// SPDX-License-Identifier: EUPL-1.2
#pragma once

#include <QCryptographicHash>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QHash>
#include <QString>
#include <QStringList>
#include <QTextStream>

inline QHash<QString, QString> readManifest(const QString &themeDir)
{
    QHash<QString, QString> entries;
    const QStringList names = QDir(themeDir).entryList(QStringList(QStringLiteral("MANIFEST.*")), QDir::Files);
    for (const QString &name : names) {
        QFile file(themeDir + QLatin1Char('/') + name);
        if (!file.open(QIODevice::ReadOnly | QIODevice::Text))
            continue;
        QTextStream stream(&file);
        while (!stream.atEnd()) {
            const QStringList p = stream.readLine().split(QLatin1Char(' '));
            if (p.value(0) == QLatin1String("F") && p.size() >= 4)
                entries.insert(p.mid(3).join(QLatin1Char(' ')), QStringLiteral("F ") + p.value(1));
            else if (p.value(0) == QLatin1String("L") && p.size() == 3)
                entries.insert(p.value(1), QStringLiteral("L ") + p.value(2));
        }
    }
    return entries;
}

inline QString manifestProblem(const QString &themeDir, const QHash<QString, QString> &manifest, const QString &path)
{
    const QString entry = manifest.value(QDir(themeDir).relativeFilePath(path));
    if (entry.isEmpty())
        return QStringLiteral("not listed in the manifest");
    const QFileInfo info(path);
    if (info.isSymLink())
        return entry == QStringLiteral("L ") + QFileInfo(info.symLinkTarget()).fileName() ? QString() : QStringLiteral("link differs from the manifest");
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly))
        return QStringLiteral("cannot be read");
    const QString digest = QString::fromLatin1(QCryptographicHash::hash(file.readAll(), QCryptographicHash::Sha256).toHex());
    return entry == QStringLiteral("F ") + digest ? QString() : QStringLiteral("file differs from the manifest");
}
