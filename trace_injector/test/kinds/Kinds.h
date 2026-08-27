#pragma once

//
// One member per kind of definition the injector has to find a body in: a
// constructor, a destructor, and a member template. All three are declared
// here and defined in the .cpp, so nothing in this tree is header-inline.
//
class Kinds
{
public:
    Kinds(int count, int limit);
    ~Kinds();

    template <typename T>
    void Emit(T value, int count);

private:
    int m_count;
    int m_limit;
};

//
// Bodies written on one line. Nothing can go into one without moving the
// closing brace, so the injector says so and leaves them alone.
//
class Compact
{
public:
    Compact();
    void Tick();
};
