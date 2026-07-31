ENTRY(_start)

SECTIONS
{
    /* ROM */
    . = 0x00000000;

    .text :
    {
        *(.text*)
    }

    .rodata :
    {
        *(.rodata*)
    }


    /* RAM */
    .data 0x80000000 :
    {
        *(.data*)
    }

    .bss :
    {
        *(.bss*)
        *(COMMON)
    }
}
