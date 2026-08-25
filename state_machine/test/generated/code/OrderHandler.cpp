#include "OrderHandler.h"
#include <iostream>

// --- Guards ---
bool OrderHandler::AmountGt100(Event event, const EventData& data) const {
    // TODO: 
    return true;
}
bool OrderHandler::AmountLte100(Event event, const EventData& data) const {
    // TODO: 
    return true;
}

// --- Actions ---
void OrderHandler::AutoConfirmReceipt(Event event, const EventData& data) {
    // TODO: 
    std::cout << "[Action] Executing AutoConfirmReceipt on event...\n";
}
void OrderHandler::AutoRefund(Event event, const EventData& data) {
    // TODO: 
    std::cout << "[Action] Executing AutoRefund on event...\n";
}
void OrderHandler::RefundToAccount(Event event, const EventData& data) {
    // TODO: 
    std::cout << "[Action] Executing RefundToAccount on event...\n";
}
void OrderHandler::SendPaymentNotification(Event event, const EventData& data) {
    // TODO: 
    std::cout << "[Action] Executing SendPaymentNotification on event...\n";
}
void OrderHandler::TransferToManualAudit(Event event, const EventData& data) {
    // TODO: 
    std::cout << "[Action] Executing TransferToManualAudit on event...\n";
}
