#pragma once

//
// The point of this fixture is the include below. <string> drags in cursors
// whose kind ids are newer than the table the clang python bindings carry, and
// reading .kind on one of those raises rather than returning a value. Every
// real .cpp in the world reaches one; none of the other fixtures do, which is
// how the tool shipped with a crash no test could see.
//
#include <string>
#include <vector>

class Stdlib
{
public:

    std::string Describe(const std::string& name) const;

    std::vector<std::string> Split(const std::string& text, char separator) const;
};

std::string Join(const std::vector<std::string>& parts);
