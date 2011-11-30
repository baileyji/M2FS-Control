#define disableRegBit(reg, regBit) reg&=~(1<<regBit)
#define enableRegBit(reg, regBit)  reg|=(1<<regBit)
#define ULONG_MAX 0xffffffff
