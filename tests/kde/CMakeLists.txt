# SPDX-License-Identifier: EUPL-1.2
cmake_minimum_required(VERSION 3.16)
project(resina-icon-kde-tests LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
find_package(Qt6 REQUIRED COMPONENTS Widgets Gui)
find_package(KF6IconThemes REQUIRED)
find_package(KF6WidgetsAddons REQUIRED)
add_executable(kde_probe kde_probe.cpp)
target_link_libraries(kde_probe PRIVATE Qt6::Widgets Qt6::Gui KF6::IconThemes KF6::IconWidgets KF6::WidgetsAddons)
