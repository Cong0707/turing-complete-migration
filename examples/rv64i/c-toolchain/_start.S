    .section .text
    .globl _start
_start:
    addi sp, x0, 2047        # 栈顶

    addi x1, x0, 128         # x1 = 128

    jal ra, main

end:
    j end                    # 程序结束，死循环
