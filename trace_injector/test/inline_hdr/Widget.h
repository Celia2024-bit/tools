#pragma once

//
// Run is DEFINED here, inline, on line 11. Widget.cpp carries an opening
// brace on its own line 11, which is what makes the mistargeting visible: a
// payload placed by header line number lands inside Widget::Later's if block.
//
class Widget
{
public:
    void Run() { }
    void Later();
};
