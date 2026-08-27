#include "Widget.h"

//
// The brace on line 11 below is deliberate: line 11 is where Widget::Run is
// defined over in Widget.h. Walking the whole translation unit but indexing
// into this file's lines drops Run's payload inside Later's if block.
//
void Widget::Later()
{
    int a = 1;
    if (a > 0) {
        a = 2;
    }
}
