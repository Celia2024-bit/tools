# Order State Machine Definition

> Describing state machine via Markdown tables. Edit directly with Notepad / VSCode; `|` is the separator.

## Config
- **prefix**: Order

## Context Definition Table

| **context_name** | **field_type** | **field_name** | **description** |
| ---------------- | -------------- | -------------- | --------------- |
| OrderContext     | int            | orderId        | Order ID        |
| OrderContext     | double         | amount         | Transaction amt |
| OrderContext     | std::string    | reason         | Refund reason   |


## State Definition Table

| **id** | **name**       | **type** | **description**                                      |
| ------ | -------------- | -------- | ---------------------------------------------------- |
| S000   | Idle           | initial  | Order not created yet                                |
| S001   | PendingPayment | normal   |                                                      |
| S002   | Paid           | normal   |                                                      |
| S003   | Shipped        | normal   |                                                      |
| S004   | Completed      | final    |                                                      |
| S005   | Cancelled      | final    |                                                      |
| S006   | PendingAudit   | normal   | Refund amount is large, manual confirmation required |

## State Transition Table

| **id** | **from_state** | **event**          | **guard**    | **to_state**   | **action**              | **description**                              |
| ------ | -------------- | ------------------ | ------------ | -------------- | ----------------------- | -------------------------------------------- |
| T001   | Idle           | CreateOrder        |              | PendingPayment |                         |                                              |
| T002   | PendingPayment | PaySuccess         |              | Paid           | SendPaymentNotification |                                              |
| T003   | PendingPayment | PayTimeout         |              | Cancelled      |                         |                                              |
| T004   | Paid           | Ship               |              | Shipped        |                         |                                              |
| T005   | Shipped        | ConfirmReceipt     |              | Completed      |                         |                                              |
| T006   | Shipped        | AutoConfirmTimeout |              | Completed      | AutoConfirmReceipt      |                                              |
| T007   | Paid           | ApplyRefund        | AmountLte100 | Cancelled      | AutoRefund              | Small refund auto-approved, no manual action |
| T008   | Paid           | ApplyRefund        | AmountGt100  | PendingAudit   | TransferToManualAudit   |                                              |
| T009   | PendingAudit   | AuditPass          |              | Cancelled      | RefundToAccount         |                                              |
