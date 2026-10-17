cmake_minimum_required(VERSION 3.24)
project(gamehub_core LANGUAGES CXX)

# Núcleo C++ de GameHub: la VM de la GameIR, el estado compacto y los algoritmos (F8).
# Objetivos: la biblioteca estática `gamehub_core`, el módulo de Python (nanobind), los tests
# (Catch2) y el build para el navegador (Emscripten, en wasm/).

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

option(GAMEHUB_CORE_PYTHON "Módulo de Python (nanobind)" OFF)
option(GAMEHUB_CORE_TESTS "Tests en C++ (Catch2)" OFF)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release)
endif()

file(GLOB GAMEHUB_CORE_SOURCES CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp)
add_library(gamehub_core STATIC ${GAMEHUB_CORE_SOURCES})
target_include_directories(gamehub_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
if(NOT MSVC)
  target_compile_options(gamehub_core PRIVATE -Wall -Wextra -Wno-unused-parameter)
endif()

option(GAMEHUB_CORE_TOOLS "Herramientas de línea de órdenes (benchmark)" OFF)
if(GAMEHUB_CORE_TOOLS)
  add_executable(gamehub_bench tools/bench.cpp)
  target_link_libraries(gamehub_bench PRIVATE gamehub_core)
endif()

if(GAMEHUB_CORE_PYTHON)
  find_package(Python 3.12 REQUIRED COMPONENTS Interpreter Development.Module)
  execute_process(
    COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
    OUTPUT_STRIP_TRAILING_WHITESPACE OUTPUT_VARIABLE nanobind_ROOT)
  find_package(nanobind CONFIG REQUIRED)
  nanobind_add_module(gamehub_core_py NB_STATIC python/module.cpp)
  set_target_properties(gamehub_core_py PROPERTIES OUTPUT_NAME gamehub_core)
  target_link_libraries(gamehub_core_py PRIVATE gamehub_core)
  install(TARGETS gamehub_core_py LIBRARY DESTINATION .)
endif()

if(GAMEHUB_CORE_TESTS)
  include(FetchContent)
  FetchContent_Declare(
    Catch2
    GIT_REPOSITORY https://github.com/catchorg/Catch2.git
    GIT_TAG v3.8.1)
  FetchContent_MakeAvailable(Catch2)
  file(GLOB GAMEHUB_CORE_TEST_SOURCES CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/tests/*.cpp)
  add_executable(gamehub_core_tests ${GAMEHUB_CORE_TEST_SOURCES})
  target_link_libraries(gamehub_core_tests PRIVATE gamehub_core Catch2::Catch2WithMain)
  enable_testing()
  add_test(NAME gamehub_core_tests COMMAND gamehub_core_tests)
endif()
