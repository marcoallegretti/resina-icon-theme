// SPDX-License-Identifier: EUPL-1.2
#include <QGuiApplication>
#include <QIcon>
#include <QQmlApplicationEngine>

int main(int argc, char **argv)
{
    QGuiApplication app(argc, argv);
    QIcon::setThemeName(QStringLiteral("Resina"));
    QQmlApplicationEngine engine(QUrl(QStringLiteral("qrc:/main.qml")));
    return engine.rootObjects().isEmpty() ? 1 : app.exec();
}
