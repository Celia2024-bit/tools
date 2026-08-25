#ifndef ORDER_STATE_MACHINE_H
#define ORDER_STATE_MACHINE_H

#include "event.h"
#include "OrderHandler.h"
#include <vector>

enum class State {
    Idle,
    PendingPayment,
    Paid,
    Shipped,
    Completed,
    Cancelled,
    PendingAudit
};

class OrderStateMachine {
public:
    OrderStateMachine();

    bool ProcessTransition(Event event, const EventData& data = {});

    State GetCurrentState() const { return m_currentState; }
    OrderHandler& GetHandler() { return m_handler; }

private:
    using GuardFunc  = bool (OrderHandler::*)(Event, const EventData&) const;
    using ActionFunc = void (OrderHandler::*)(Event, const EventData&);

    struct Transition {
        State fromState;
        Event event;
        GuardFunc guard;
        State toState;
        ActionFunc action;
    };

    State m_currentState{State::Idle};
    OrderHandler m_handler;
    std::vector<Transition> m_transitions;
};

#endif // ORDER_STATE_MACHINE_H