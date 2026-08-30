#include "OrderMgr.h"

void OrderMgr::OnData(
    int id
)
{
    id++;
}

void OrderMgr::OnConnected()
{
}

bool OrderMgr::SubmitOrder(
    int order_id
)
{
    return true;
}