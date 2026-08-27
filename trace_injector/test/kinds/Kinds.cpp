#include "Kinds.h"

//
// The member-init list has braces of its own, and they come first. Anything
// taking the first { after the signature for the body's lands in here.
//
Kinds::Kinds(int count, int limit)
    : m_count(count)
    , m_limit{limit}
{
    m_count = count;
}

Kinds::~Kinds()
{
    m_count = 0;
}

template <typename T>
void Kinds::Emit(T value, int count)
{
    (void)count;
}

//
// So the template above is instantiated rather than dead.
//
void UseEmit(Kinds& kinds)
{
    kinds.Emit(1, 2);
}

//
// Declared and never defined; defined and never instantiated. libclang
// exposes no body for either, so telling them apart is left to the text.
//
template <typename T>
T Twice(T x);

template <typename T>
T Thrice(T x)
{
    return x + x + x;
}

Compact::Compact() { }

void Compact::Tick() { return; }
