#pragma once

class OrderMgr
{
public:

    void OnData(
        int id
    );

    void OnConnected();

    bool SubmitOrder(
        int order_id
    );
};