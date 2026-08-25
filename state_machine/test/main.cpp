#include <iostream>
#include <string>
#include "event.h"
#include "OrderStateMachine.h"



// Helper function to convert State enum values to human-readable strings
std::string StateToString(State state) {
    switch (state) {
        case State::Idle:           return "Idle";
        case State::PendingPayment: return "PendingPayment";
        case State::Paid:           return "Paid";
        case State::Shipped:        return "Shipped";
        case State::Completed:      return "Completed";
        case State::Cancelled:      return "Cancelled";
        case State::PendingAudit:   return "PendingAudit";
    }
    return "Unknown";
}

int main() {
    std::cout << "=== State Machine Verification with Payload Start ===" << std::endl;

    OrderStateMachine sm;
    std::cout << "[Initial State] " << StateToString(sm.GetCurrentState()) << std::endl << std::endl;

    // ------------------------------------------------------------------------
    // Test Case 1: Standard Transition with Context Data
    // ------------------------------------------------------------------------
    std::cout << "--- Test 1: Standard Order Creation ---" << std::endl;

    OrderContext ctx1{ 1001, 50.0, "Normal Purchase" };
    bool ok = sm.ProcessTransition(Event::CreateOrder, ctx1);
    std::cout << "Trigger Event::CreateOrder -> Result: " << (ok ? "SUCCESS" : "FAILED") 
              << " | Current State: " << StateToString(sm.GetCurrentState()) << std::endl;

    ok = sm.ProcessTransition(Event::PaySuccess, ctx1);
    std::cout << "Trigger Event::PaySuccess  -> Result: " << (ok ? "SUCCESS" : "FAILED") 
              << " | Current State: " << StateToString(sm.GetCurrentState()) << std::endl << std::endl;

    // ------------------------------------------------------------------------
    // Test Case 2: Guard Evaluation and Action Execution with Event & Payload
    // ------------------------------------------------------------------------
    std::cout << "--- Test 2: Apply Refund (with OrderContext Payload) ---" << std::endl;

    // Construct refund context
    OrderContext refundCtx{ 1001, 80.0, "User requested refund" };

    // ProcessTransition passes (Event::ApplyRefund, refundCtx)
    // directly to OrderHandler::AmountLte100 and OrderHandler::AutoRefund
    ok = sm.ProcessTransition(Event::ApplyRefund, refundCtx);
    
    std::cout << "Trigger Event::ApplyRefund -> Result: " << (ok ? "SUCCESS" : "FAILED") 
              << " | Current State: " << StateToString(sm.GetCurrentState()) << std::endl;

    std::cout << "\n=== State Machine Verification End ===" << std::endl;
    return 0;
}