#ifndef ORDER_HANDLER_H
#define ORDER_HANDLER_H

#include "event.h"
#include "OrderContext.h"

class OrderHandler {
public:
    OrderHandler() = default;

    // --- Guards ---
    bool AmountGt100(Event event, const EventData& data) const;
    bool AmountLte100(Event event, const EventData& data) const;

    // --- Actions ---
    void AutoConfirmReceipt(Event event, const EventData& data);
    void AutoRefund(Event event, const EventData& data);
    void RefundToAccount(Event event, const EventData& data);
    void SendPaymentNotification(Event event, const EventData& data);
    void TransferToManualAudit(Event event, const EventData& data);
};

#endif // ORDER_HANDLER_H