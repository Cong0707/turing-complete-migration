typedef unsigned long long u64;

static u64 mix(u64 value) {
    value ^= value >> 13;
    value += value << 7;
    value ^= value >> 17;
    return value;
}
int main(void) {
    volatile u64 value = 0x12345678ULL;

    for (unsigned int index = 0; index < 8; ++index) {
        value = mix(value + index);
    }

    return (int)value;
}
