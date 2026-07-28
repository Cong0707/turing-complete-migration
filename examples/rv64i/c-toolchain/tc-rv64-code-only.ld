OUTPUT_ARCH(riscv)
ENTRY(_start)

SECTIONS
{
    . = 0;

    .text : ALIGN(4)
    {
        KEEP(*(.text.start))
        *(.text .text.*)
    }

    .rodata : ALIGN(8)
    {
        *(.rodata .rodata.*)
        *(.srodata .srodata.*)
    }

    .data : ALIGN(8)
    {
        *(.data .data.*)
        *(.sdata .sdata.*)
        *(.got .got.*)
        *(.init_array .init_array.*)
        *(.fini_array .fini_array.*)
        *(.tdata .tdata.*)
    }

    .bss (NOLOAD) : ALIGN(8)
    {
        *(.bss .bss.*)
        *(.sbss .sbss.*)
        *(.tbss .tbss.*)
        *(COMMON)
    }

    ASSERT(SIZEOF(.rodata) == 0,
        "RV64 code-only mode does not support .rodata; remove strings/tables/constants that require memory")
    ASSERT(SIZEOF(.data) == 0,
        "RV64 code-only mode does not support initialized globals/static data")
    ASSERT(SIZEOF(.bss) == 0,
        "RV64 code-only mode does not support globals/static zero-initialized data")

    PROVIDE(__global_pointer$ = 0);

    /DISCARD/ :
    {
        *(.comment)
        *(.note .note.*)
        *(.eh_frame .eh_frame.*)
        *(.riscv.attributes)
    }
}
