# This file was automatically generated for projects
# without default 'CMakeLists.txt' file.

FILE(GLOB_RECURSE app_sources ${CMAKE_SOURCE_DIR}/src/*.*)
list(APPEND app_sources "${CMAKE_SOURCE_DIR}/.pio/libdeps/esp32-s3-devkitm-1/JPEGDEC/src/JPEGDEC.cpp")

idf_component_register(SRCS ${app_sources}
                       INCLUDE_DIRS "." "${CMAKE_SOURCE_DIR}/.pio/libdeps/esp32-s3-devkitm-1/JPEGDEC/src")
