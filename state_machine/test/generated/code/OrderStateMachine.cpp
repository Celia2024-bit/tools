#include "OrderStateMachine.h"

OrderStateMachine::OrderStateMachine() {
    m_transitions = {
        { State::Idle, Event::CreateOrder, nullptr, State::PendingPayment, nullptr },
        { State::PendingPayment, Event::PaySuccess, nullptr, State::Paid, &OrderHandler::SendPaymentNotification },
        { State::PendingPayment, Event::PayTimeout, nullptr, State::Cancelled, nullptr },
        { State::Paid, Event::Ship, nullptr, State::Shipped, nullptr },
        { State::Shipped, Event::ConfirmReceipt, nullptr, State::Completed, nullptr },
        { State::Shipped, Event::AutoConfirmTimeout, nullptr, State::Completed, &OrderHandler::AutoConfirmReceipt },
        { State::Paid, Event::ApplyRefund, &OrderHandler::AmountLte100, State::Cancelled, &OrderHandler::AutoRefund },
        { State::Paid, Event::ApplyRefund, &OrderHandler::AmountGt100, State::PendingAudit, &OrderHandler::TransferToManualAudit },
        { State::PendingAudit, Event::AuditPass, nullptr, State::Cancelled, &OrderHandler::RefundToAccount }
    };
}

bool OrderStateMachine::ProcessTransition(Event event, const EventData& data) {
    for (const auto& trans : m_transitions) {
        if (trans.fromState == m_currentState && trans.event == event) {
            
            if (trans.guard != nullptr) {
                if (!(m_handler.*(trans.guard))(event, data)) {
                    continue;
                }
            }

            m_currentState = trans.toState;

            if (trans.action != nullptr) {
                (m_handler.*(trans.action))(event, data);
            }

            return true;
        }
    }

    return false;
}