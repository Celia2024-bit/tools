#ifndef EVENT_H
#define EVENT_H

#include <any>
enum class Event {
    ApplyRefund,
    AuditPass,
    AutoConfirmTimeout,
    ConfirmReceipt,
    CreateOrder,
    PaySuccess,
    PayTimeout,
    Ship
};

using EventData = std::any;
#endif // EVENT_H