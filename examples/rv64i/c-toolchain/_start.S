.section .text
.globl _start

_start:
    lui sp, 0x80004       # RV64 中暂时得到 0xffffffff80004000
    slli sp, sp, 32
    srli sp, sp, 32        # sp = 0x0000000080004000

    jal  ra, main          # 调用 GCC 编译的 C main

end:
    # main 的退出码位于 x10/a0
    addi s0, x10, 0        # s0 = 退出码

    # s1 = 屏幕内存写指针 0x10000000
    lui  s1, 0x10000

    # ============================================================
    # 输出固定字符串：
    #
    # Program exited. exit code:
    #
    # 不使用 .asciz 或任何数据段。
    # 每个字符都由 ADDI 产生，然后通过 SB 写入屏幕内存。
    # ============================================================

    addi t0, x0, 80        # 'P'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 114       # 'r'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 111       # 'o'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 103       # 'g'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 114       # 'r'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 97        # 'a'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 109       # 'm'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 32        # ' '
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 101       # 'e'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 120       # 'x'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 105       # 'i'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 116       # 't'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 101       # 'e'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 100       # 'd'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 46        # '.'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 32        # '
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 101       # 'e'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 120       # 'x'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 105       # 'i'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 116       # 't'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 32        # ' '
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 99        # 'c'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 111       # 'o'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 100       # 'd'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 101       # 'e'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 58        # ':'
    sb   t0, 0(s1)
    addi s1, s1, 1

    addi t0, x0, 32        # ' '
    sb   t0, 0(s1)
    addi s1, s1, 1

    # ============================================================
    # 处理有符号退出码
    #
    # s0 = main 返回的原始退出码
    # s2 = 退出码的无符号绝对值
    # s3 = 负数标志
    #
    # 也可以正确处理：
    # -9223372036854775808
    # ============================================================

    addi s2, s0, 0         # 默认绝对值位模式等于原值
    addi s3, x0, 0         # 默认不是负数

    bge  s0, x0, magnitude_ready

    addi s3, x0, 1         # 设置负数标志
    sub  s2, x0, s0        # s2 = 0 - s0

magnitude_ready:
    # 如果是负数，先输出 '-'
    beq  s3, x0, sign_done

    addi t0, x0, 45        # ASCII '-'
    sb   t0, 0(s1)
    addi s1, s1, 1

sign_done:
    # s2 = 退出码的无符号绝对值
    #
    # 如果 s2 != 0，进入普通十进制转换。
    # 如果 s2 == 0，直接输出 "0." 并进入独立死循环。
    bne  s2, x0, convert_nonzero

write_zero_exit_code:
    # 当前 s1 应当等于 0x1000001b

    addi t0, x0, 48        # ASCII '0' = 0x30
    sb   t0, 0(s1)         # [0x1000001b] = 0x30
    addi s1, s1, 1

    addi t0, x0, 46        # ASCII '.' = 0x2e
    sb   t0, 0(s1)         # [0x1000001c] = 0x2e

zero_infinite_loop:
    jal x0, zero_infinite_loop


convert_nonzero:
    # ============================================================
    # 非零退出码转换
    # ============================================================
    addi s4, x0, 0         # 已压栈的数字数量

decimal_convert_loop:
    addi a0, s2, 0
    jal  ra, unsigned_divmod_10

    # a0 = 商
    # a1 = 余数 0..9
    addi s2, a0, 0
    addi a1, a1, 48        # 余数转换为 ASCII

    addi sp, sp, -1
    sb   a1, 0(sp)
    addi s4, s4, 1

    bne  s2, x0, decimal_convert_loop

write_decimal_loop:
    beq  s4, x0, decimal_done

    lbu  t0, 0(sp)
    addi sp, sp, 1
    addi s4, s4, -1

    sb   t0, 0(s1)
    addi s1, s1, 1

    jal  x0, write_decimal_loop

decimal_done:
    addi t0, x0, 46        # ASCII '.'
    sb   t0, 0(s1)

nonzero_infinite_loop:
    jal x0, nonzero_infinite_loop


# ================================================================
# unsigned_divmod_10
#
# 仅使用 RV64I 指令完成 64 位无符号数除以 10。
# 不使用：
#   div / divu / rem / remu / mul
#
# 输入：
#   a0 = 64 位无符号被除数
#
# 输出：
#   a0 = 商
#   a1 = 余数，范围 0..9
#
# 破坏：
#   t0、t1、t2、t3、t4、t5、t6
# ================================================================

unsigned_divmod_10:
    addi t0, a0, 0         # t0 = 被除数
    addi t1, x0, 0         # t1 = 商
    addi t2, x0, 0         # t2 = 当前余数

    addi t3, x0, 1
    slli t3, t3, 63        # t3 = 最高位掩码

    addi t4, x0, 64        # 总共处理 64 位
    addi t6, x0, 10        # 除数 10

unsigned_divmod_10_loop:
    # remainder <<= 1
    slli t2, t2, 1

    # 将被除数当前位放入余数最低位
    and  t5, t0, t3
    beq  t5, x0, current_bit_zero
    addi t2, t2, 1

current_bit_zero:
    # quotient <<= 1
    slli t1, t1, 1

    # 如果 remainder >= 10：
    #     remainder -= 10
    #     quotient |= 1
    bltu t2, t6, remainder_less_than_10

    sub  t2, t2, t6
    addi t1, t1, 1

remainder_less_than_10:
    srli t3, t3, 1         # 移到下一位

    addi t4, t4, -1
    bne  t4, x0, unsigned_divmod_10_loop

    addi a0, t1, 0         # a0 = 商
    addi a1, t2, 0         # a1 = 余数

    jalr x0, 0(ra)
