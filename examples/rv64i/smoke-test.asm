; RV64I 12-opcode-group smoke test for Turing Complete spec.isa.

start:
    add a0, a1, a2
    sub a0, a1, a2
    sll a0, a1, a2
    slt a0, a1, a2
    sltu a0, a1, a2
    xor a0, a1, a2
    srl a0, a1, a2
    sra a0, a1, a2
    or a0, a1, a2
    and a0, a1, a2

    addi a0, a1, -16
    slti a0, a1, -1
    sltiu a0, a1, 1
    xori a0, a1, -1
    ori a0, a1, 127
    andi a0, a1, 255
    slli a0, a1, 63
    srli a0, a1, 63
    srai a0, a1, 63

    lb a0, -8(sp)
    lh a0, -8(sp)
    lw a0, -8(sp)
    ld a0, -8(sp)
    lbu a0, -8(sp)
    lhu a0, -8(sp)
    lwu a0, -8(sp)

    sb a0, 8(sp)
    sh a0, 8(sp)
    sw a0, 8(sp)
    sd a0, 8(sp)

    beq a0, a1, branch_target
    bne a0, a1, branch_target
    blt a0, a1, branch_target
    bge a0, a1, branch_target
    bltu a0, a1, branch_target
    bgeu a0, a1, branch_target

branch_target:
    lui a0, 0x12345
    auipc a0, 0x12345
    jal ra, jump_target
    jalr ra, 0(sp)

    ecall
    ebreak

    addiw a0, a1, -16
    slliw a0, a1, 31
    srliw a0, a1, 31
    sraiw a0, a1, 31

    addw a0, a1, a2
    subw a0, a1, a2
    sllw a0, a1, a2
    srlw a0, a1, a2
    sraw a0, a1, a2

jump_target:
    nop
    li a0, 123
    mv a0, a1
    not a0, a1
    neg a0, a1
    negw a0, a1
    sext.w a0, a1
    zext.b a0, a1
    seqz a0, a1
    snez a0, a1
    sltz a0, a1
    sgtz a0, a1
    jr ra
    ret
