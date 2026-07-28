    .section .text.start, "ax", @progbits
    .align 2
    .option push
    .option norvc
    .option norelax
    .globl _start
    .type _start, @function

_start:
    lui sp, %hi(__stack_top)
    addi sp, sp, %lo(__stack_top)
    jal ra, main

.Lhalt:
    jal zero, .Lhalt

    .size _start, . - _start
    .option pop
