#pragma once

//
// Both methods are declared here and defined in the .cpp, so nothing in this
// tree is header-inline. The point of the tree is the shape of the trace
// already sitting in the .cpp, not where the definitions live.
//
class Legacy
{
public:
    void Old();
    void New();
};
