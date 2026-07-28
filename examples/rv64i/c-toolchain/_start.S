    .section .text
    .globl _start
_start:
    lui x2, 0x2
    addi x2, x2, 0
    jal ra, main

end:
    j end                   # 程序结束，死循环
