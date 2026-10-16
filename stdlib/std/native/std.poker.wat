;; SPDX-License-Identifier: Apache-2.0
;; Plugin nativo std.poker (ABI gamehub-native/1, ver docs/wiki/engine.md): el valor de una mano de
;; póquer. Es el mismo algoritmo que la implementación de referencia, `hand_value` en
;; stdlib/std/poker.game, y tiene que dar lo mismo para cualquier lista de cartas (lo comprueban los
;; tests con listas al azar, también con cartas repetidas).
;;
;; Entrada, en palabras i32: el número de cartas n y, por cada carta, su palo (0 tréboles,
;; 1 diamantes, 2 corazones, 3 picas) y su rango (0 el dos … 12 el as). Salida: una palabra, el
;; valor de la mano (categoría · 16⁵ + desempates en base 16).
;;
;; Memoria: cuentas por rango en 0..51 y por palo y rango en 64..271; el búfer de intercambio con
;; el motor empieza en 4096.
(module
  (memory (export "memory") 1)
  (global $acc (mut i32) (i32.const 0))
  (global $nk (mut i32) (i32.const 0))

  (func (export "gh_buffer") (result i32) (i32.const 4096))

  ;; --- Cuentas -----------------------------------------------------------------------------------

  (func $cnt (param $r i32) (result i32)
    (i32.load (i32.shl (local.get $r) (i32.const 2))))

  (func $sc_addr (param $s i32) (param $r i32) (result i32)
    (i32.add
      (i32.const 64)
      (i32.shl (i32.add (i32.mul (local.get $s) (i32.const 13)) (local.get $r)) (i32.const 2))))

  (func $sc (param $s i32) (param $r i32) (result i32)
    (i32.load (call $sc_addr (local.get $s) (local.get $r))))

  (func $suit_count (param $s i32) (result i32)
    (local $r i32) (local $total i32)
    (block $done
      (loop $next
        (br_if $done (i32.ge_s (local.get $r) (i32.const 13)))
        (local.set $total (i32.add (local.get $total) (call $sc (local.get $s) (local.get $r))))
        (local.set $r (i32.add (local.get $r) (i32.const 1)))
        (br $next)))
    (local.get $total))

  ;; ¿Hay alguna carta del rango r? (del palo s, o de cualquiera si s < 0)
  (func $present (param $s i32) (param $r i32) (result i32)
    (if (result i32) (i32.lt_s (local.get $s) (i32.const 0))
      (then (i32.gt_s (call $cnt (local.get $r)) (i32.const 0)))
      (else (i32.gt_s (call $sc (local.get $s) (local.get $r)) (i32.const 0)))))

  ;; El rango más alto con al menos m cartas, distinto de skip (−1 si no hay).
  (func $highest (param $m i32) (param $skip i32) (result i32)
    (local $r i32)
    (local.set $r (i32.const 12))
    (block $done
      (loop $next
        (br_if $done (i32.lt_s (local.get $r) (i32.const 0)))
        (if (i32.and
              (i32.ge_s (call $cnt (local.get $r)) (local.get $m))
              (i32.ne (local.get $r) (local.get $skip)))
          (then (return (local.get $r))))
        (local.set $r (i32.sub (local.get $r) (i32.const 1)))
        (br $next)))
    (i32.const -1))

  ;; --- Escaleras ---------------------------------------------------------------------------------

  ;; La carta alta (2..14) de la mejor escalera, del palo s o de cualquiera (s < 0); 0 si no hay.
  (func $straight_high (param $s i32) (result i32)
    (local $h i32) (local $i i32) (local $ok i32)
    (local.set $h (i32.const 12))
    (block $done
      (loop $next
        (br_if $done (i32.lt_s (local.get $h) (i32.const 4)))
        (local.set $ok (i32.const 1))
        (local.set $i (i32.sub (local.get $h) (i32.const 4)))
        (block $run_done
          (loop $run
            (br_if $run_done (i32.gt_s (local.get $i) (local.get $h)))
            (if (i32.eqz (call $present (local.get $s) (local.get $i)))
              (then (local.set $ok (i32.const 0)) (br $run_done)))
            (local.set $i (i32.add (local.get $i) (i32.const 1)))
            (br $run)))
        (if (local.get $ok) (then (return (i32.add (local.get $h) (i32.const 2)))))
        (local.set $h (i32.sub (local.get $h) (i32.const 1)))
        (br $next)))
    ;; La rueda: as, dos, tres, cuatro y cinco.
    (if (i32.and
          (i32.and (call $present (local.get $s) (i32.const 12)) (call $present (local.get $s) (i32.const 0)))
          (i32.and
            (call $present (local.get $s) (i32.const 1))
            (i32.and (call $present (local.get $s) (i32.const 2)) (call $present (local.get $s) (i32.const 3)))))
      (then (return (i32.const 5))))
    (i32.const 0))

  ;; --- El valor ----------------------------------------------------------------------------------

  ;; El valor se va formando en $acc: la categoría y después hasta cinco cartas en base 16.
  (func $start (param $category i32)
    (global.set $acc (local.get $category))
    (global.set $nk (i32.const 0)))

  (func $push (param $v i32)
    (if (i32.lt_s (global.get $nk) (i32.const 5))
      (then
        (global.set $acc (i32.add (i32.mul (global.get $acc) (i32.const 16)) (local.get $v)))
        (global.set $nk (i32.add (global.get $nk) (i32.const 1))))))

  (func $finish (result i32)
    (block $done
      (loop $pad
        (br_if $done (i32.ge_s (global.get $nk) (i32.const 5)))
        (global.set $acc (i32.mul (global.get $acc) (i32.const 16)))
        (global.set $nk (i32.add (global.get $nk) (i32.const 1)))
        (br $pad)))
    (global.get $acc))

  ;; Añade las k cartas más altas de rangos distintos, sin los rangos a ni b.
  (func $top (param $a i32) (param $b i32) (param $k i32)
    (local $r i32)
    (local.set $r (i32.const 12))
    (block $done
      (loop $next
        (br_if $done
          (i32.or (i32.lt_s (local.get $r) (i32.const 0)) (i32.le_s (local.get $k) (i32.const 0))))
        (if (i32.and
              (i32.gt_s (call $cnt (local.get $r)) (i32.const 0))
              (i32.and (i32.ne (local.get $r) (local.get $a)) (i32.ne (local.get $r) (local.get $b))))
          (then
            (call $push (i32.add (local.get $r) (i32.const 2)))
            (local.set $k (i32.sub (local.get $k) (i32.const 1)))))
        (local.set $r (i32.sub (local.get $r) (i32.const 1)))
        (br $next))))

  ;; El mejor color o escalera de color del palo s: las cinco cartas más altas de ese palo, con
  ;; las repetidas tantas veces como estén.
  (func $flush_value (param $s i32) (result i32)
    (local $high i32) (local $r i32) (local $c i32)
    (local.set $high (call $straight_high (local.get $s)))
    (if (local.get $high)
      (then
        (call $start (i32.const 8))
        (call $push (local.get $high))
        (return (call $finish))))
    (call $start (i32.const 5))
    (local.set $r (i32.const 12))
    (block $done
      (loop $next
        (br_if $done (i32.lt_s (local.get $r) (i32.const 0)))
        (local.set $c (call $sc (local.get $s) (local.get $r)))
        (block $copies_done
          (loop $copies
            (br_if $copies_done (i32.le_s (local.get $c) (i32.const 0)))
            (call $push (i32.add (local.get $r) (i32.const 2)))
            (local.set $c (i32.sub (local.get $c) (i32.const 1)))
            (br $copies)))
        (local.set $r (i32.sub (local.get $r) (i32.const 1)))
        (br $next)))
    (call $finish))

  (func (export "hand_value") (param $in i32) (param $len i32) (param $out i32) (result i32)
    (local $n i32) (local $i i32) (local $s i32) (local $r i32) (local $a i32)
    (local $best i32) (local $v i32) (local $t i32) (local $p i32) (local $p2 i32)
    (memory.fill (i32.const 0) (i32.const 0) (i32.const 272))
    (if (i32.lt_s (local.get $len) (i32.const 1)) (then (return (i32.const -1))))
    (local.set $n (i32.load (local.get $in)))
    (if (i32.ne (local.get $len) (i32.add (i32.const 1) (i32.mul (local.get $n) (i32.const 2))))
      (then (return (i32.const -1))))
    ;; Cuentas por rango y por palo.
    (block $done
      (loop $next
        (br_if $done (i32.ge_s (local.get $i) (local.get $n)))
        (local.set $a
          (i32.add (local.get $in) (i32.add (i32.const 4) (i32.shl (local.get $i) (i32.const 3)))))
        (local.set $s (i32.load (local.get $a)))
        (local.set $r (i32.load offset=4 (local.get $a)))
        (if (i32.or (i32.ge_u (local.get $s) (i32.const 4)) (i32.ge_u (local.get $r) (i32.const 13)))
          (then (return (i32.const -1))))
        (i32.store
          (i32.shl (local.get $r) (i32.const 2))
          (i32.add (call $cnt (local.get $r)) (i32.const 1)))
        (i32.store
          (call $sc_addr (local.get $s) (local.get $r))
          (i32.add (call $sc (local.get $s) (local.get $r)) (i32.const 1)))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $next)))
    ;; Colores: el mejor de los palos con cinco cartas o más.
    (local.set $s (i32.const 0))
    (block $done
      (loop $next
        (br_if $done (i32.ge_s (local.get $s) (i32.const 4)))
        (if (i32.ge_s (call $suit_count (local.get $s)) (i32.const 5))
          (then
            (local.set $v (call $flush_value (local.get $s)))
            (if (i32.gt_s (local.get $v) (local.get $best)) (then (local.set $best (local.get $v))))))
        (local.set $s (i32.add (local.get $s) (i32.const 1)))
        (br $next)))
    ;; Escalera de color (categoría 8: 8 · 16⁵ = 8388608).
    (if (i32.ge_s (local.get $best) (i32.const 8388608))
      (then (i32.store (local.get $out) (local.get $best)) (return (i32.const 1))))
    ;; Póquer.
    (local.set $v (call $highest (i32.const 4) (i32.const -1)))
    (if (i32.ge_s (local.get $v) (i32.const 0))
      (then
        (call $start (i32.const 7))
        (call $push (i32.add (local.get $v) (i32.const 2)))
        (call $top (local.get $v) (i32.const -1) (i32.const 1))
        (i32.store (local.get $out) (call $finish))
        (return (i32.const 1))))
    ;; Full.
    (local.set $t (call $highest (i32.const 3) (i32.const -1)))
    (if (i32.ge_s (local.get $t) (i32.const 0))
      (then
        (local.set $p (call $highest (i32.const 2) (local.get $t)))
        (if (i32.ge_s (local.get $p) (i32.const 0))
          (then
            (call $start (i32.const 6))
            (call $push (i32.add (local.get $t) (i32.const 2)))
            (call $push (i32.add (local.get $p) (i32.const 2)))
            (i32.store (local.get $out) (call $finish))
            (return (i32.const 1))))))
    ;; Color.
    (if (i32.gt_s (local.get $best) (i32.const 0))
      (then (i32.store (local.get $out) (local.get $best)) (return (i32.const 1))))
    ;; Escalera.
    (local.set $v (call $straight_high (i32.const -1)))
    (if (local.get $v)
      (then
        (call $start (i32.const 4))
        (call $push (local.get $v))
        (i32.store (local.get $out) (call $finish))
        (return (i32.const 1))))
    ;; Trío.
    (if (i32.ge_s (local.get $t) (i32.const 0))
      (then
        (call $start (i32.const 3))
        (call $push (i32.add (local.get $t) (i32.const 2)))
        (call $top (local.get $t) (i32.const -1) (i32.const 2))
        (i32.store (local.get $out) (call $finish))
        (return (i32.const 1))))
    ;; Dobles parejas o pareja.
    (local.set $p (call $highest (i32.const 2) (i32.const -1)))
    (if (i32.ge_s (local.get $p) (i32.const 0))
      (then
        (local.set $p2 (call $highest (i32.const 2) (local.get $p)))
        (if (i32.ge_s (local.get $p2) (i32.const 0))
          (then
            (call $start (i32.const 2))
            (call $push (i32.add (local.get $p) (i32.const 2)))
            (call $push (i32.add (local.get $p2) (i32.const 2)))
            (call $top (local.get $p) (local.get $p2) (i32.const 1)))
          (else
            (call $start (i32.const 1))
            (call $push (i32.add (local.get $p) (i32.const 2)))
            (call $top (local.get $p) (i32.const -1) (i32.const 3))))
        (i32.store (local.get $out) (call $finish))
        (return (i32.const 1))))
    ;; Carta alta.
    (call $start (i32.const 0))
    (call $top (i32.const -1) (i32.const -1) (i32.const 5))
    (i32.store (local.get $out) (call $finish))
    (i32.const 1)))
