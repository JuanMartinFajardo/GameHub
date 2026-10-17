// SPDX-License-Identifier: Apache-2.0
// Código de bytes de las expresiones de la IR (ADR-077).
//
// Máquina de pila: cada instrucción es un código de operación seguido de sus operandos (palabras
// de 32 bits). Los argumentos y las variables locales (`let`, variables de las comprensiones y
// de los `for`) viven en ranuras del marco, asignadas al compilar (ámbito léxico). Las
// comprensiones son bucles con su colección, su índice y su acumulador en ranuras; las listas
// que construyen (map, filter…) se acumulan en una pila de constructores de la VM.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "gamehub/value.hpp"

namespace gh {

enum Op : uint32_t {
  // Referencias y literales
  OP_CONST,     // k: constante k
  OP_VAR,       // i: variable de estado i
  OP_PARAM,     // i: parámetro i
  OP_LOAD,      // s: ranura s
  OP_STORE,     // s: saca un valor y lo guarda en la ranura s
  OP_ACTOR,     //
  OP_VIEWER,    //
  OP_OWNER,     //
  OP_FACE_UP,   //
  OP_SEATS,     //
  OP_AT,        // nodo: ¿está el nodo en la ruta activa?
  // Constructores
  OP_LIST,    // n
  OP_SET,     // n
  OP_STRUCT,  // tipo, n
  OP_CELL,    //
  // Aritmética
  OP_ADD,  // n
  OP_SUB,
  OP_MUL,  // n
  OP_DIV,
  OP_IDIV,
  OP_MOD,
  OP_NEG,
  OP_ABS,
  OP_MIN,  // n
  OP_MAX,  // n
  // Comparación
  OP_EQ,
  OP_NE,
  OP_LT,
  OP_LE,
  OP_GT,
  OP_GE,
  // Lógica y control
  OP_NOT,
  OP_AND_TEST,  // destino: falso → deja False y salta; verdadero → sigue
  OP_OR_TEST,   // destino: verdadero → deja True y salta; falso → sigue
  OP_JUMP,      // destino
  OP_JUMP_IF_FALSE,  // destino, nombre del operador (para el error si no es booleano)
  OP_POP,
  // Opcionales
  OP_IS_NONE,
  OP_UNWRAP,
  // Colecciones
  OP_LEN,
  OP_CONTAINS,
  OP_INDEX,
  OP_FIELD,  // id del nombre del campo
  OP_FIRST,
  OP_LAST,
  OP_ONLY,
  OP_APPEND,
  OP_CONCAT,
  OP_RANGE,
  OP_SLICE,
  OP_REVERSE,
  OP_DISTINCT,
  OP_UNION,
  OP_INTERSECTION,
  OP_DIFFERENCE,
  OP_SUBSETS,
  // Comprensiones
  OP_ITER_INIT,   // nombre, ranura de la colección, ranura del índice, ¿no vacía?
  OP_ITER_NEXT,   // ranura de la colección, ranura del índice, ranura de la variable, salida
  OP_ALL_STEP,    // salida si falso
  OP_ANY_STEP,    // salida si verdadero
  OP_COUNT_STEP,  // ranura del acumulador
  OP_SUM_STEP,    // ranura del acumulador
  OP_BUILD_BEGIN,
  OP_BUILD_PUSH,
  OP_BUILD_LIST,
  OP_FILTER_STEP,  // ranura de la variable
  OP_FLAT_STEP,
  OP_ARGBEST_STEP,  // signo, nombre, ranura del mejor, ranura de su clave, ranura de la variable
  OP_BEST_OF,       // signo, nombre (reduce la lista construida)
  OP_SORT_PUSH,     // ranura de la variable (apila clave y elemento)
  OP_SORT_BY,       // nombre
  // Asientos
  OP_NEXT_SEAT,
  OP_PREV_SEAT,
  OP_OTHER_SEAT,
  OP_SEATS_FROM,
  // Tableros
  OP_CELLS,
  OP_LINES,
  OP_NEIGHBORS,
  OP_IN_BOUNDS,
  // Zonas
  OP_SIZE,
  OP_ITEMS,
  OP_TOP,
  // Enumerados
  OP_ORD,
  // Funciones
  OP_CALL,  // función, nº de argumentos
  // Pagos
  OP_WIN_LOSS,
  OP_FILL,
  OP_RETURN,
};

// Nombres de los operadores de comprensión (operando de OP_ITER_INIT).
enum IterOp : uint32_t {
  IT_ALL,
  IT_ANY,
  IT_COUNT,
  IT_SUM,
  IT_MAP,
  IT_FLAT_MAP,
  IT_FILTER,
  IT_ARGMAX,
  IT_ARGMIN,
  IT_MAX_OF,
  IT_MIN_OF,
  IT_SORT_BY,
};
extern const char* const ITER_OPS[];

// Una expresión compilada. Comparte el marco (las ranuras) de su unidad de compilación.
struct Chunk {
  std::vector<uint32_t> code;
  std::vector<Value> consts;
  uint32_t max_stack = 0;
};

}  // namespace gh
