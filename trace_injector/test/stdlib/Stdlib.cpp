#include "Stdlib.h"

std::string Stdlib::Describe(const std::string& name) const
{
    return "Stdlib(" + name + ")";
}

std::vector<std::string> Stdlib::Split(const std::string& text, char separator) const
{
    std::vector<std::string> parts;

    std::string current;

    for (char c : text)
    {
        if (c == separator)
        {
            parts.push_back(current);
            current.clear();
        }
        else
        {
            current += c;
        }
    }

    parts.push_back(current);

    return parts;
}

std::string Join(const std::vector<std::string>& parts)
{
    std::string joined;

    for (const std::string& part : parts)
    {
        joined += part;
    }

    return joined;
}
