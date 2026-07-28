// rv64i bare metal assert test
// no header
// no macro
// no rodata dependency


typedef unsigned char uint8_t;
typedef unsigned int uint32_t;
typedef unsigned long long uint64_t;


// --------- bare metal assert ---------

void assert(int condition)
{
    if(!condition)
    {
        while(1)
        {
        }
    }
}


// --------- basic ---------

uint32_t rotr(uint32_t x, uint32_t n)
{
    return (x >> n) | (x << (32 - n));
}


// --------- SHA256 transform ---------

void sha256_transform(
    uint32_t state[8],
    uint8_t block[64],
    uint32_t K[64]
)
{
    uint32_t w[64];


    for(int i=0;i<16;i++)
    {
        w[i] =
            ((uint32_t)block[i*4] << 24) |
            ((uint32_t)block[i*4+1] << 16) |
            ((uint32_t)block[i*4+2] << 8) |
            ((uint32_t)block[i*4+3]);
    }


    for(int i=16;i<64;i++)
    {
        uint32_t s0 =
            rotr(w[i-15],7) ^
            rotr(w[i-15],18) ^
            (w[i-15]>>3);


        uint32_t s1 =
            rotr(w[i-2],17) ^
            rotr(w[i-2],19) ^
            (w[i-2]>>10);


        w[i] =
            w[i-16] +
            s0 +
            w[i-7] +
            s1;
    }


    uint32_t a=state[0];
    uint32_t b=state[1];
    uint32_t c=state[2];
    uint32_t d=state[3];

    uint32_t e=state[4];
    uint32_t f=state[5];
    uint32_t g=state[6];
    uint32_t h=state[7];


    for(int i=0;i<64;i++)
    {
        uint32_t S1 =
            rotr(e,6)^
            rotr(e,11)^
            rotr(e,25);


        uint32_t ch =
            (e & f) ^
            ((~e) & g);


        uint32_t temp1 =
            h +
            S1 +
            ch +
            K[i] +
            w[i];


        uint32_t S0 =
            rotr(a,2)^
            rotr(a,13)^
            rotr(a,22);


        uint32_t maj =
            (a & b) ^
            (a & c) ^
            (b & c);


        uint32_t temp2 =
            S0 + maj;


        h=g;
        g=f;
        f=e;
        e=d+temp1;

        d=c;
        c=b;
        b=a;
        a=temp1+temp2;
    }


    state[0]+=a;
    state[1]+=b;
    state[2]+=c;
    state[3]+=d;

    state[4]+=e;
    state[5]+=f;
    state[6]+=g;
    state[7]+=h;
}

int main()
{
    // -------------------------
    // basic ALU test
    // -------------------------

    assert((1 + 1) == 2);

    uint32_t shift_test = 0x12345678;

    assert((shift_test >> 24) == 0x12);
    assert(((shift_test >> 16) & 0xff) == 0x34);
    assert(((shift_test >> 8) & 0xff) == 0x56);
    assert((shift_test & 0xff) == 0x78);



    // -------------------------
    // stack memory test
    // -------------------------

    uint32_t mem_test[4];

    mem_test[0] = 0x11223344;
    mem_test[1] = 0x55667788;
    mem_test[2] = 0xaabbccdd;
    mem_test[3] = 0xeeff0011;


    assert(mem_test[0] == 0x11223344);
    assert(mem_test[1] == 0x55667788);
    assert(mem_test[2] == 0xaabbccdd);
    assert(mem_test[3] == 0xeeff0011);



    // -------------------------
    // byte store/load test
    // -------------------------

    uint8_t byte_test[4];


    byte_test[0] = 0xaa;
    byte_test[1] = 0xbb;
    byte_test[2] = 0xcc;
    byte_test[3] = 0xdd;


    assert(byte_test[0] == 0xaa);
    assert(byte_test[1] == 0xbb);
    assert(byte_test[2] == 0xcc);
    assert(byte_test[3] == 0xdd);



    // -------------------------
    // SHA constants
    // local stack array
    // -------------------------

    uint32_t K[64];


    K[0]=0x428a2f98;
    K[1]=0x71374491;
    K[2]=0xb5c0fbcf;
    K[3]=0xe9b5dba5;
    K[4]=0x3956c25b;
    K[5]=0x59f111f1;
    K[6]=0x923f82a4;
    K[7]=0xab1c5ed5;

    K[8]=0xd807aa98;
    K[9]=0x12835b01;
    K[10]=0x243185be;
    K[11]=0x550c7dc3;
    K[12]=0x72be5d74;
    K[13]=0x80deb1fe;
    K[14]=0x9bdc06a7;
    K[15]=0xc19bf174;

    K[16]=0xe49b69c1;
    K[17]=0xefbe4786;
    K[18]=0x0fc19dc6;
    K[19]=0x240ca1cc;
    K[20]=0x2de92c6f;
    K[21]=0x4a7484aa;
    K[22]=0x5cb0a9dc;
    K[23]=0x76f988da;

    K[24]=0x983e5152;
    K[25]=0xa831c66d;
    K[26]=0xb00327c8;
    K[27]=0xbf597fc7;
    K[28]=0xc6e00bf3;
    K[29]=0xd5a79147;
    K[30]=0x06ca6351;
    K[31]=0x14292967;

    K[32]=0x27b70a85;
    K[33]=0x2e1b2138;
    K[34]=0x4d2c6dfc;
    K[35]=0x53380d13;
    K[36]=0x650a7354;
    K[37]=0x766a0abb;
    K[38]=0x81c2c92e;
    K[39]=0x92722c85;

    K[40]=0x2bfe8a1;
    K[41]=0xa81a664b;
    K[42]=0xc24b8b70;
    K[43]=0xc76c51a3;
    K[44]=0xd192e819;
    K[45]=0xd6990624;
    K[46]=0xf40e3585;
    K[47]=0x106aa070;

    K[48]=0x19a4c116;
    K[49]=0x1e376c08;
    K[50]=0x2748774c;
    K[51]=0x34b0bcb5;
    K[52]=0x391c0cb3;
    K[53]=0x4ed8aa4a;
    K[54]=0x5b9cca4f;
    K[55]=0x682e6ff3;

    K[56]=0x748f82ee;
    K[57]=0x78a5636f;
    K[58]=0x84c87814;
    K[59]=0x8cc70208;
    K[60]=0x90befffa;
    K[61]=0xa4506ceb;
    K[62]=0xbef9a3f7;
    K[63]=0xc67178f2;


    assert(K[0] == 0x428a2f98);
    assert(K[63] == 0xc67178f2);



    // -------------------------
    // SHA state
    // -------------------------

    uint32_t state[8];


    state[0]=0x6a09e667;
    state[1]=0xbb67ae85;
    state[2]=0x3c6ef372;
    state[3]=0xa54ff53a;

    state[4]=0x510e527f;
    state[5]=0x9b05688c;
    state[6]=0x1f83d9ab;
    state[7]=0x5be0cd19;


    assert(state[0]==0x6a09e667);
    assert(state[7]==0x5be0cd19);



    // -------------------------
    // block
    // -------------------------

    uint8_t block[64];


    for(int i=0;i<64;i++)
    {
        block[i]=0;
    }


    for(int i=0;i<64;i++)
    {
        assert(block[i]==0);
    }



    // -------------------------
    // nonce test
    // -------------------------

    uint32_t nonce=0;


    assert(nonce==0);


    nonce++;

    assert(nonce==1);


    nonce++;

    assert(nonce==2);



    // reset

    nonce=0;



    // -------------------------
    // mining loop
    // -------------------------

    for(int ab=1;ab<10;ab++)
    {

        block[60]=(nonce>>24)&0xff;
        block[61]=(nonce>>16)&0xff;
        block[62]=(nonce>>8)&0xff;
        block[63]=nonce&0xff;


        assert(block[60]==((nonce>>24)&0xff));
        assert(block[61]==((nonce>>16)&0xff));
        assert(block[62]==((nonce>>8)&0xff));
        assert(block[63]==(nonce&0xff));


        uint32_t old=state[0];


        sha256_transform(
            state,
            block,
            K
        );


        assert(state[0]!=old);


        nonce++;


        assert(nonce==(uint32_t)ab);
    }



    assert(nonce==9);


    return 0;
}
