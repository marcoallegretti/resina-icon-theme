# SPDX-License-Identifier: EUPL-1.2
cmake_minimum_required(VERSION 3.16)
project(resina-icon-example LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_AUTORCC ON)
find_package(Qt6 REQUIRED COMPONENTS Gui Qml Quick QuickControls2 Svg)
qt_add_executable(example main.cpp)
qt_add_resources(example resources PREFIX "/" FILES main.qml)
target_link_libraries(example PRIVATE Qt6::Gui Qt6::Qml Qt6::Quick Qt6::QuickControls2 Qt6::Svg)
